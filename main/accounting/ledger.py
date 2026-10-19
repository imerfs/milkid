"""Ledger rules: fiscal years, vouchers (draft -> final) and the two basic reports.

Every public function takes the acting user first, resolves their municipality and refuses anything outside it.
Amounts are whole rials. Money changes happen inside ``transaction.atomic`` so a failed voucher leaves nothing behind.
"""
from datetime import timedelta
from decimal import Decimal, InvalidOperation

import jdatetime
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from main.access import can, role_of
from main.models import Account, BillPayment, FiscalYear, Municipality, Voucher, VoucherLine
from main.office.errors import Conflict, Forbidden, Invalid, NotFound
from main.office.roles import is_admin, municipality_for

MAX_AMOUNT = Decimal(10) ** 16
MAX_TEXT = 500
KINDS = {k for k, _ in Voucher.KINDS}


def municipality_of(user):
    """The municipality the user works for. Staff must be allowed to do accounting; admins have no tenant."""
    if not can(user, 'staff.accountant'):
        raise Forbidden()
    muni = Municipality.objects.filter(admin_user=user).first()
    if muni is None and not is_admin(user):
        muni = municipality_for(user.profile)
    if muni is None:
        raise NotFound('دهیاری شما یافت نشد.')
    return muni


def _own(muni, obj):
    if obj is None or obj.municipality_id != muni.id:
        raise NotFound()
    return obj


def _amount(value):
    if value is None or isinstance(value, bool):
        raise Invalid('مبلغ نامعتبر است.')
    try:
        amount = Decimal(str(value).replace(',', '').strip()) if isinstance(value, str) else Decimal(value)
    except (InvalidOperation, ValueError, TypeError):
        raise Invalid('مبلغ نامعتبر است.')
    if not amount.is_finite() or amount != amount.to_integral_value():
        raise Invalid('مبلغ باید عدد صحیح (ریال) باشد.')
    if amount < 0 or amount >= MAX_AMOUNT:
        raise Invalid('مبلغ خارج از محدوده مجاز است.')
    return amount


def _text(value, label, required=True):
    value = (value or '').strip()
    if required and not value:
        raise Invalid(f'{label} را وارد کنید.')
    if len(value) > MAX_TEXT:
        raise Invalid(f'{label} حداکثر {MAX_TEXT} نویسه می‌تواند باشد.')
    return value


def _clean_lines(muni, lines):
    if not lines:
        raise Invalid('سند باید حداقل یک ردیف داشته باشد.')
    cleaned = []
    for row, item in enumerate(lines, start=1):
        account = _own_or_invalid(muni, item.get('account'), 'حساب')
        debit, credit = _amount(item.get('debit')), _amount(item.get('credit'))
        if (debit > 0) == (credit > 0):
            raise Invalid(f'ردیف {row}: فقط یکی از بدهکار یا بستانکار باید مبلغ داشته باشد.')
        if not account.is_postable:
            raise Invalid(f'ردیف {row}: روی حساب «{account.title}» سند ثبت نمی‌شود.')
        party = item.get('party')
        if party is not None:
            _own_or_invalid(muni, party, 'طرف حساب')
        elif account.requires_party:
            raise Invalid(f'ردیف {row}: برای حساب «{account.title}» طرف حساب لازم است.')
        center = item.get('cost_center')
        if center is not None:
            _own_or_invalid(muni, center, 'مرکز هزینه')
        cleaned.append(dict(row=row, account=account, party=party, cost_center=center,
                            description=_text(item.get('description'), 'شرح ردیف', required=False),
                            debit=debit, credit=credit))
    return cleaned


def _own_or_invalid(muni, obj, label):
    if obj is None or obj.municipality_id != muni.id:
        raise Invalid(f'{label} نامعتبر است.')
    return obj


def _check_header(year, on, kind):
    if kind not in KINDS:
        raise Invalid('نوع سند نامعتبر است.')
    if not (year.start_date <= on <= year.end_date):
        raise Invalid('تاریخ سند باید داخل سال مالی باشد.')


def open_year(actor, year):
    muni = municipality_of(actor)
    try:
        year = int(year)
    except (TypeError, ValueError):
        raise Invalid('سال مالی نامعتبر است.')
    if not 1300 <= year <= 1500:
        raise Invalid('سال مالی نامعتبر است.')
    if FiscalYear.objects.filter(municipality=muni, year=year).exists():
        raise Conflict('این سال مالی قبلاً باز شده است.')
    start = jdatetime.date(year, 1, 1).togregorian()
    end = jdatetime.date(year + 1, 1, 1).togregorian() - timedelta(days=1)
    return FiscalYear.objects.create(municipality=muni, year=year, start_date=start, end_date=end)


def get_year(actor, year_id):
    muni = municipality_of(actor)
    return _own(muni, FiscalYear.objects.filter(pk=year_id).first())


def get_voucher(actor, voucher_id):
    muni = municipality_of(actor)
    voucher = Voucher.objects.select_related('fiscal_year').filter(pk=voucher_id, deleted_at__isnull=True).first()
    return _own(muni, voucher)


def vouchers_for(actor, year):
    muni = municipality_of(actor)
    _own(muni, year)
    return Voucher.objects.filter(fiscal_year=year, deleted_at__isnull=True)


def is_balanced(voucher):
    totals = voucher.lines.aggregate(d=Sum('debit'), c=Sum('credit'))
    return (totals['d'] or 0) == (totals['c'] or 0) and voucher.lines.exists()


def _locked(model, pk):
    return model.objects.select_for_update().get(pk=pk)


def _editable(voucher):
    if voucher.status != 'temporary':
        raise Conflict('سند قطعی قابل ویرایش یا حذف نیست.')
    if voucher.fiscal_year.is_closed:
        raise Conflict('سال مالی بسته شده است.')


def _not_from_bill(voucher):
    """A bill payment's voucher is changed only by cancelling the payment, or bill and ledger would drift apart."""
    if BillPayment.objects.filter(voucher=voucher).exists():
        raise Conflict('این سند از پرداخت فیش ساخته شده است؛ برای اصلاح، پرداخت را از صفحه‌ی فیش ابطال کنید.')


def check_editable(actor, voucher):
    """Raise Conflict if the voucher may not be edited (final, in a closed year or created by a bill payment)."""
    _own(municipality_of(actor), voucher)
    _editable(voucher)
    _not_from_bill(voucher)


def create_voucher(actor, year, on, kind, description, lines, *, number_hint=None):
    muni = municipality_of(actor)
    _own(muni, year)
    if year.is_closed:
        raise Conflict('سال مالی بسته شده است.')
    _check_header(year, on, kind)
    description = _text(description, 'شرح سند')
    cleaned = _clean_lines(muni, lines)
    with transaction.atomic():
        _locked(Municipality, muni.id)        # serialises numbering per municipality
        mine = Voucher.objects.filter(municipality=muni)
        last_ref = mine.order_by('-ref').values_list('ref', flat=True).first() or 0
        last_no = mine.filter(fiscal_year=year).order_by('-number').values_list('number', flat=True).first() or 0
        voucher = Voucher.objects.create(
            municipality=muni, fiscal_year=year, number=last_no + 1, ref=last_ref + 1, date=on, kind=kind,
            description=description, created_by=actor)
        VoucherLine.objects.bulk_create([VoucherLine(voucher=voucher, **c) for c in cleaned])
    return voucher


def update_voucher(actor, voucher, *, description, lines, on=None, kind=None):
    muni = municipality_of(actor)
    _own(muni, voucher)
    with transaction.atomic():
        voucher = _locked(Voucher, voucher.pk)
        voucher.fiscal_year = FiscalYear.objects.get(pk=voucher.fiscal_year_id)
        _editable(voucher)
        _not_from_bill(voucher)
        on, kind = on or voucher.date, kind or voucher.kind
        _check_header(voucher.fiscal_year, on, kind)
        voucher.description, voucher.date, voucher.kind = _text(description, 'شرح سند'), on, kind
        cleaned = _clean_lines(muni, lines)
        voucher.save(update_fields=['description', 'date', 'kind'])
        voucher.lines.all().delete()
        VoucherLine.objects.bulk_create([VoucherLine(voucher=voucher, **c) for c in cleaned])
    return voucher


def finalize(actor, voucher):
    muni = municipality_of(actor)
    _own(muni, voucher)
    with transaction.atomic():
        voucher = _locked(Voucher, voucher.pk)
        voucher.fiscal_year = FiscalYear.objects.get(pk=voucher.fiscal_year_id)
        _editable(voucher)
        if voucher.lines.count() < 2 or not is_balanced(voucher):
            raise Conflict('سند بی‌حساب است؛ جمع بدهکار و بستانکار باید برابر و حداقل دو ردیف باشد.')
        voucher.status, voucher.finalized_by, voucher.finalized_at = 'final', actor, timezone.now()
        voucher.save(update_fields=['status', 'finalized_by', 'finalized_at'])
    return voucher


def revert_to_temporary(actor, voucher):
    muni = municipality_of(actor)
    if role_of(actor) != 'dehyari' and not is_admin(actor):
        raise Forbidden('فقط دهیار می‌تواند سند قطعی را به موقت برگرداند.')
    _own(muni, voucher)
    with transaction.atomic():
        voucher = _locked(Voucher, voucher.pk)
        year = FiscalYear.objects.get(pk=voucher.fiscal_year_id)
        if voucher.status != 'final':
            raise Conflict('این سند قطعی نیست.')
        if year.is_closed:
            raise Conflict('سال مالی بسته شده است.')
        voucher.status, voucher.finalized_by, voucher.finalized_at = 'temporary', None, None
        voucher.save(update_fields=['status', 'finalized_by', 'finalized_at'])
    return voucher


def delete_voucher(actor, voucher):
    """Soft delete of a draft; its number is never reused."""
    muni = municipality_of(actor)
    _own(muni, voucher)
    with transaction.atomic():
        voucher = _locked(Voucher, voucher.pk)
        voucher.fiscal_year = FiscalYear.objects.get(pk=voucher.fiscal_year_id)
        _editable(voucher)
        _not_from_bill(voucher)
        voucher.deleted_at = timezone.now()
        voucher.save(update_fields=['deleted_at'])


def _lines(muni, year, include_temporary):
    qs = VoucherLine.objects.filter(voucher__municipality=muni, voucher__fiscal_year=year,
                                    voucher__deleted_at__isnull=True)
    return qs if include_temporary else qs.filter(voucher__status='final')


def trial_balance(actor, year, include_temporary=True):
    muni = municipality_of(actor)
    _own(muni, year)
    rows = [
        {'account_id': r['account_id'], 'code': r['account__code'], 'title': r['account__title'], 'debit': r['d'], 'credit': r['c'],
         'balance': r['d'] - r['c']}
        for r in _lines(muni, year, include_temporary).values('account_id', 'account__code', 'account__title')
        .annotate(d=Sum('debit'), c=Sum('credit')).order_by('account__code')]
    totals = {'debit': sum(r['debit'] for r in rows), 'credit': sum(r['credit'] for r in rows)}
    return rows, totals


def account_ledger(actor, year, account, include_temporary=True, date_from=None, date_to=None):
    """Turnover of one account; a group account (one that cannot be posted to) shows its descendants' lines.

    With ``date_from`` the first row is the balance carried in from before that date (it has no voucher).
    """
    muni = municipality_of(actor)
    _own(muni, year)
    _own(muni, account)
    ids = {account.id}
    if not account.is_postable:
        children = list(Account.objects.filter(municipality=muni, parent_id__in=ids))
        while children:
            ids |= {c.id for c in children}
            children = list(Account.objects.filter(municipality=muni, parent_id__in=[c.id for c in children]).exclude(pk__in=ids))
    base = _lines(muni, year, include_temporary).filter(account_id__in=ids)
    rows, balance = [], Decimal(0)
    if date_from:
        carried = base.filter(voucher__date__lt=date_from).aggregate(d=Sum('debit'), c=Sum('credit'))
        balance = (carried['d'] or 0) - (carried['c'] or 0)
        rows.append({'voucher': None, 'row': 0, 'description': 'مانده از قبل', 'debit': 0, 'credit': 0, 'balance': balance,
                     'account': None})
        base = base.filter(voucher__date__gte=date_from)
    if date_to:
        base = base.filter(voucher__date__lte=date_to)
    for ln in base.select_related('voucher', 'account').order_by('voucher__date', 'voucher__number', 'row'):
        balance += ln.debit - ln.credit
        rows.append({'voucher': ln.voucher, 'row': ln.row, 'description': ln.description or ln.voucher.description,
                     'debit': ln.debit, 'credit': ln.credit, 'balance': balance,
                     'account': ln.account if len(ids) > 1 else None})
    return rows


def change_status_range(actor, year, number_from, number_to, target):
    """Bulk status change (تغییر وضعیت اسناد) for vouchers numbered number_from..number_to of the year.

    Each voucher goes through finalize / revert_to_temporary, so every single-voucher rule applies (balance,
    closed year, only the mayor may revert). Returns ``(changed, skipped)``; skipped is ``[(number, reason)]``.
    """
    muni = municipality_of(actor)
    _own(muni, year)
    if target not in ('final', 'temporary'):
        raise Invalid('وضعیت مقصد نامعتبر است.')
    if number_from is None or number_to is None or number_from < 1 or number_to < number_from:
        raise Invalid('بازه شماره سند نامعتبر است.')
    if number_to - number_from > 5000:
        raise Invalid('بازه انتخابی بیش از حد بزرگ است.')
    wanted, other = ('temporary', 'final') if target == 'final' else ('final', 'temporary')
    vouchers = Voucher.objects.filter(fiscal_year=year, municipality=muni, deleted_at__isnull=True,
                                      number__gte=number_from, number__lte=number_to, status=wanted).order_by('number')
    changed, skipped = 0, []
    for voucher in vouchers:
        try:
            (finalize if target == 'final' else revert_to_temporary)(actor, voucher)
            changed += 1
        except (Conflict, Forbidden) as exc:
            if isinstance(exc, Forbidden):
                raise
            skipped.append((voucher.number, str(exc)))
    return changed, skipped
