"""Contracts (قرارداد), their progress statements (صورت وضعیت) and guarantees (ضمانت‌نامه).

A statement's deductions are fixed from the contract's percentages when it is recorded:
  net = gross + VAT - good-performance retention - contractor insurance - tax
Employer insurance is the municipality's own cost: it is recorded but not deducted from the contractor.
The sum of live statements can never exceed the contract's ceiling.
"""
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from main.accounting.ledger import check_unlocked, _amount, _locked, _own, _own_or_invalid, _text, municipality_of
from main.models import Contract, ContractStatement, Guarantee, Municipality
from main.office.errors import Conflict, Invalid

PCT_FIELDS = ('vat_pct', 'good_performance_pct', 'contractor_insurance_pct', 'employer_insurance_pct', 'tax_pct')
PCT_LABELS = {'vat_pct': 'درصد ارزش افزوده', 'good_performance_pct': 'درصد حسن انجام کار',
              'contractor_insurance_pct': 'درصد بیمه پیمانکار', 'employer_insurance_pct': 'درصد بیمه کارفرما',
              'tax_pct': 'درصد مالیات'}
EXPIRY_WARNING_DAYS = 30


def _pct(value, label):
    try:
        pct = Decimal(str(value if value not in (None, '') else 0).replace('٫', '.').strip())
    except (InvalidOperation, ValueError):
        raise Invalid(f'{label} نامعتبر است.')
    if not pct.is_finite() or pct < 0 or pct > 100:
        raise Invalid(f'{label} باید بین ۰ و ۱۰۰ باشد.')
    return pct.quantize(Decimal('0.01'))


def _round(value):
    return Decimal(value).quantize(Decimal(1), rounding=ROUND_HALF_UP)


def contracts_for(actor, year):
    muni = municipality_of(actor)
    _own(muni, year)
    return Contract.objects.filter(municipality=muni, fiscal_year=year).select_related('contractor').annotate(
        used=Sum('statements__gross', filter=Q(statements__canceled_at__isnull=True)))


def get_contract(actor, contract_id):
    muni = municipality_of(actor)
    return _own(muni, Contract.objects.select_related('fiscal_year', 'contractor').filter(pk=contract_id).first())


def used(contract):
    return contract.statements.filter(canceled_at__isnull=True).aggregate(s=Sum('gross'))['s'] or Decimal(0)


def create_contract(actor, year, *, subject, contractor, date, start_date, end_date, amount, ceiling=None, kind='',
                    supervisor='', cost_center=None, adjustable=False, description='', **pcts):
    muni = municipality_of(actor)
    _own(muni, year)
    if year.is_closed:
        raise Conflict('سال مالی بسته شده است.')
    check_unlocked(muni, date)
    contractor = _own_or_invalid(muni, contractor, 'پیمانکار')
    if cost_center is not None:
        _own_or_invalid(muni, cost_center, 'مرکز هزینه')
    amount = _amount(amount)
    if amount <= 0:
        raise Invalid('مبلغ قرارداد باید بیشتر از صفر باشد.')
    ceiling = _amount(ceiling) if ceiling not in (None, '', 0) else amount
    if ceiling < amount:
        raise Invalid('سقف مبلغ نمی‌تواند کمتر از مبلغ قرارداد باشد.')
    if end_date < start_date:
        raise Invalid('تاریخ پایان قبل از تاریخ شروع است.')
    percents = {f: _pct(pcts.get(f), PCT_LABELS[f]) for f in PCT_FIELDS}
    with transaction.atomic():
        _locked(Municipality, muni.id)
        last = Contract.objects.filter(municipality=muni, fiscal_year=year).order_by('-number').values_list(
            'number', flat=True).first() or 0
        return Contract.objects.create(
            municipality=muni, fiscal_year=year, number=last + 1, kind=_text(kind, 'نوع قرارداد', False)[:100],
            subject=_text(subject, 'موضوع قرارداد')[:300], contractor=contractor, date=date, start_date=start_date,
            end_date=end_date, amount=amount, ceiling=ceiling, supervisor=_text(supervisor, 'ناظر', False)[:150],
            cost_center=cost_center, adjustable=bool(adjustable), description=_text(description, 'توضیحات', False),
            created_by=actor, **percents)


def set_status(actor, contract, status):
    muni = municipality_of(actor)
    _own(muni, contract)
    check_unlocked(muni, contract.date)
    if status not in dict(Contract.STATUSES):
        raise Invalid('وضعیت نامعتبر است.')
    with transaction.atomic():
        contract = _locked(Contract, contract.pk)
        if contract.status in ('terminated', 'finished') and status != contract.status:
            raise Conflict('قرارداد خاتمه‌یافته یا فسخ‌شده دوباره باز نمی‌شود.')
        contract.status = status
        contract.save(update_fields=['status'])
    return contract


def compute_deductions(contract, gross):
    gross = Decimal(gross)
    pct = lambda p: _round(gross * getattr(contract, p) / 100)   # noqa: E731
    vat, retention, insurance = pct('vat_pct'), pct('good_performance_pct'), pct('contractor_insurance_pct')
    employer, tax = pct('employer_insurance_pct'), pct('tax_pct')
    return {'vat': vat, 'good_performance': retention, 'contractor_insurance': insurance, 'employer_insurance': employer,
            'tax': tax, 'net': gross + vat - retention - insurance - tax}


def add_statement(actor, contract, on, gross, description=''):
    muni = municipality_of(actor)
    _own(muni, contract)
    check_unlocked(muni, on)
    gross = _amount(gross)
    if gross <= 0:
        raise Invalid('مبلغ کارکرد باید بیشتر از صفر باشد.')
    with transaction.atomic():
        contract = _locked(Contract, contract.pk)
        if contract.fiscal_year.is_closed:
            raise Conflict('سال مالی بسته شده است.')
        if contract.status != 'active':
            raise Conflict('برای قرارداد غیرفعال صورت وضعیت ثبت نمی‌شود.')
        if on < contract.start_date or on > contract.end_date:
            raise Invalid('تاریخ صورت وضعیت باید بین شروع و پایان قرارداد باشد.')
        left = contract.ceiling - used(contract)
        if gross > left:
            raise Conflict(f'مبلغ از سقف قرارداد بیشتر است؛ حداکثر {max(left, 0):,} ریال باقی مانده است.')
        last = contract.statements.order_by('-number').values_list('number', flat=True).first() or 0
        return ContractStatement.objects.create(
            contract=contract, number=last + 1, date=on, gross=gross, created_by=actor,
            description=_text(description, 'شرح', False)[:300], **compute_deductions(contract, gross))


def cancel_statement(actor, statement):
    muni = municipality_of(actor)
    _own(muni, statement.contract)
    check_unlocked(muni, statement.date)
    with transaction.atomic():
        statement = ContractStatement.objects.select_related('contract__fiscal_year').get(pk=statement.pk)
        _locked(Contract, statement.contract_id)
        if statement.contract.fiscal_year.is_closed:
            raise Conflict('سال مالی بسته شده است.')
        if statement.canceled_at is None:
            statement.canceled_at = timezone.now()
            statement.save(update_fields=['canceled_at'])
    return statement


# ---------- guarantees ----------

def guarantees_for(actor):
    return Guarantee.objects.filter(municipality=municipality_of(actor)).select_related('party', 'contract')


def get_guarantee(actor, guarantee_id):
    muni = municipality_of(actor)
    return _own(muni, Guarantee.objects.select_related('party', 'contract').filter(pk=guarantee_id).first())


def expiry_state(guarantee, today):
    """'ok', 'soon' (within the warning window) or 'expired'; only active guarantees can be soon/expired."""
    if guarantee.status != 'active':
        return 'ok'
    if guarantee.expires_on < today:
        return 'expired'
    return 'soon' if guarantee.expires_on <= today + timedelta(days=EXPIRY_WARNING_DAYS) else 'ok'


def create_guarantee(actor, *, party, kind, doc_kind, serial, date, expires_on, amount, contract=None, plan=None,
                     bank='', description=''):
    muni = municipality_of(actor)
    check_unlocked(muni, date)
    party = _own_or_invalid(muni, party, 'صاحب ضمانت‌نامه')
    if contract is not None:
        _own_or_invalid(muni, contract, 'قرارداد')
    if plan is not None:
        _own_or_invalid(muni, plan, 'پرونده تقسیط')
    if kind not in dict(Guarantee.KINDS):
        raise Invalid('نوع ضمانت‌نامه نامعتبر است.')
    if doc_kind not in dict(Guarantee.DOC_KINDS):
        raise Invalid('نوع مدرک نامعتبر است.')
    amount = _amount(amount)
    if amount <= 0:
        raise Invalid('مبلغ باید بیشتر از صفر باشد.')
    if expires_on < date:
        raise Invalid('تاریخ سررسید قبل از تاریخ صدور است.')
    serial = _text(serial, 'شماره / سریال')[:60]
    with transaction.atomic():
        _locked(Municipality, muni.id)
        if Guarantee.objects.filter(municipality=muni, doc_kind=doc_kind, serial=serial).exists():
            raise Conflict('این مدرک با همین شماره قبلاً ثبت شده است.')
        return Guarantee.objects.create(
            municipality=muni, contract=contract, plan=plan, party=party, kind=kind, doc_kind=doc_kind, serial=serial,
            bank=_text(bank, 'بانک', False)[:100], date=date, expires_on=expires_on, amount=amount,
            description=_text(description, 'توضیحات', False)[:300], created_by=actor)


def set_guarantee_status(actor, guarantee, status, on):
    muni = municipality_of(actor)
    _own(muni, guarantee)
    check_unlocked(muni, on)
    if status not in ('returned', 'seized'):
        raise Invalid('وضعیت نامعتبر است.')
    with transaction.atomic():
        guarantee = _locked(Guarantee, guarantee.pk)
        if guarantee.status != 'active':
            raise Conflict('این ضمانت‌نامه قبلاً مسترد یا ضبط شده است.')
        guarantee.status, guarantee.status_changed_on = status, on
        guarantee.save(update_fields=['status', 'status_changed_on'])
    return guarantee
