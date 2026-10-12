"""Credit provisioning (تامین اعتبار): reserve budget of a use account, funded from a resource account.

A use account can never be provisioned beyond its approved budget (cancelled provisions free their amount).
"""
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from main.accounting.ledger import _amount, _locked, _own, _own_or_invalid, _text, municipality_of
from main.models import Account, BudgetLine, CreditProvision, CreditProvisionLine, Municipality
from main.office.errors import Conflict, Invalid


def provisions_for(actor, year):
    muni = municipality_of(actor)
    _own(muni, year)
    return CreditProvision.objects.filter(municipality=muni, fiscal_year=year).annotate(total=Sum('lines__amount'))


def get_provision(actor, provision_id):
    muni = municipality_of(actor)
    return _own(muni, CreditProvision.objects.select_related('fiscal_year').filter(pk=provision_id).first())


def provisioned(year, account, exclude=None):
    """Rials already reserved on a use account in the year, not counting cancelled provisions."""
    qs = CreditProvisionLine.objects.filter(provision__fiscal_year=year, provision__canceled_at__isnull=True,
                                            use_account=account)
    if exclude is not None:
        qs = qs.exclude(provision=exclude)
    return qs.aggregate(s=Sum('amount'))['s'] or 0


def availability(actor, year):
    """Per use account with a budget: budget, reserved and what is still free to reserve."""
    muni = municipality_of(actor)
    _own(muni, year)
    rows = []
    for b in BudgetLine.objects.filter(fiscal_year=year, account__kind='budget_use').select_related('account'):
        used = provisioned(year, b.account)
        rows.append({'account': b.account, 'budget': b.amount, 'reserved': used, 'free': b.amount - used})
    return sorted(rows, key=lambda r: r['account'].code)


def _clean(muni, year, lines):
    if not lines:
        raise Invalid('حداقل یک ردیف اعتبار لازم است.')
    out, wanted = [], {}
    for n, item in enumerate(lines, start=1):
        use = _own_or_invalid(muni, item.get('use_account'), f'ردیف {n}: حساب مصرف')
        source = _own_or_invalid(muni, item.get('source_account'), f'ردیف {n}: حساب منبع')
        if use.kind != 'budget_use' or not use.is_postable:
            raise Invalid(f'ردیف {n}: حساب مصرف باید یکی از حساب‌های قابل ثبت مصارف بودجه باشد.')
        if source.kind != 'budget_resource' or not source.is_postable:
            raise Invalid(f'ردیف {n}: حساب منبع باید یکی از حساب‌های قابل ثبت منابع بودجه باشد.')
        amount = _amount(item.get('amount'))
        if amount <= 0:
            raise Invalid(f'ردیف {n}: مبلغ باید بیشتر از صفر باشد.')
        wanted[use.id] = wanted.get(use.id, 0) + amount
        out.append(dict(row=n, use_account=use, source_account=source, amount=amount,
                        project=_text(item.get('project'), 'عنوان پروژه', required=False)[:200],
                        description=_text(item.get('description'), 'شرح اعتبار', required=False)[:300]))
    budgets = {b.account_id: b.amount for b in BudgetLine.objects.filter(fiscal_year=year, account_id__in=wanted)}
    return out, wanted, budgets


def _check_dates(year, on, allocation_date, expires_on):
    if not (year.start_date <= on <= year.end_date):
        raise Invalid('تاریخ باید داخل سال مالی باشد.')
    if expires_on and expires_on < on:
        raise Invalid('تاریخ انقضا نباید قبل از تاریخ تامین اعتبار باشد.')
    if allocation_date and allocation_date > on:
        raise Invalid('تاریخ تخصیص نباید بعد از تاریخ تامین اعتبار باشد.')


def create_provision(actor, year, on, lines, *, allocation_no='', allocation_date=None, expires_on=None,
                     description=''):
    muni = municipality_of(actor)
    _own(muni, year)
    if year.is_closed:
        raise Conflict('سال مالی بسته شده است.')
    _check_dates(year, on, allocation_date, expires_on)
    cleaned, wanted, budgets = _clean(muni, year, lines)
    allocation_no = _text(allocation_no, 'شماره تخصیص', required=False)[:30]
    description = _text(description, 'توضیحات', required=False)
    with transaction.atomic():
        _locked(Municipality, muni.id)           # serialises numbering and the budget check
        for account_id, amount in wanted.items():
            account = Account.objects.get(pk=account_id)
            free = budgets.get(account_id, 0) - provisioned(year, account)
            if amount > free:
                raise Conflict(f'اعتبار حساب «{account.title}» کافی نیست؛ باقی‌مانده قابل تامین '
                               f'{max(free, 0):,} ریال است.')
        last = CreditProvision.objects.filter(municipality=muni, fiscal_year=year).order_by('-number').values_list(
            'number', flat=True).first() or 0
        prov = CreditProvision.objects.create(
            municipality=muni, fiscal_year=year, number=last + 1, date=on, allocation_no=allocation_no,
            allocation_date=allocation_date, expires_on=expires_on, description=description, created_by=actor)
        CreditProvisionLine.objects.bulk_create([CreditProvisionLine(provision=prov, **c) for c in cleaned])
    return prov


def cancel_provision(actor, provision):
    muni = municipality_of(actor)
    _own(muni, provision)
    with transaction.atomic():
        provision = _locked(CreditProvision, provision.pk)
        if provision.fiscal_year.is_closed:
            raise Conflict('سال مالی بسته شده است.')
        if provision.canceled_at is None:
            provision.canceled_at = timezone.now()
            provision.save(update_fields=['canceled_at'])
    return provision
