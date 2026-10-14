"""Transport income (درآمد حمل و نقل): fees collected for vehicles or transport services, numbered per fiscal year."""
from django.db import transaction

from main.accounting.ledger import _amount, _locked, _own, _own_or_invalid, _text, municipality_of
from main.models import Municipality, TransportIncome
from main.office.errors import Conflict, Invalid


def incomes_for(actor, year):
    muni = municipality_of(actor)
    _own(muni, year)
    return TransportIncome.objects.filter(municipality=muni, fiscal_year=year).select_related('party')


def get_income(actor, income_id):
    muni = municipality_of(actor)
    return _own(muni, TransportIncome.objects.select_related('fiscal_year').filter(pk=income_id).first())


def record(actor, year, *, on, plate, service, amount, party=None, receipt_no='', description=''):
    muni = municipality_of(actor)
    _own(muni, year)
    if year.is_closed:
        raise Conflict('سال مالی بسته شده است.')
    if not (year.start_date <= on <= year.end_date):
        raise Invalid('تاریخ باید داخل سال مالی باشد.')
    if party is not None:
        _own_or_invalid(muni, party, 'پرداخت‌کننده')
    amount = _amount(amount)
    if amount <= 0:
        raise Invalid('مبلغ باید بیشتر از صفر باشد.')
    plate, service = _text(plate, 'پلاک خودرو')[:20], _text(service, 'نوع خدمت')[:100]
    with transaction.atomic():
        _locked(Municipality, muni.id)
        last = TransportIncome.objects.filter(municipality=muni, fiscal_year=year).order_by('-number').values_list(
            'number', flat=True).first() or 0
        return TransportIncome.objects.create(
            municipality=muni, fiscal_year=year, number=last + 1, date=on, plate=plate, service=service, party=party,
            amount=amount, receipt_no=_text(receipt_no, 'شماره رسید', False)[:40],
            description=_text(description, 'توضیحات', False)[:300], created_by=actor)


def cancel(actor, income):
    muni = municipality_of(actor)
    _own(muni, income)
    with transaction.atomic():
        income = _locked(TransportIncome, income.pk)
        if income.fiscal_year.is_closed:
            raise Conflict('سال مالی بسته شده است.')
        income.status = 'canceled'
        income.save(update_fields=['status'])
    return income


def total(actor, year):
    from django.db.models import Sum
    return incomes_for(actor, year).filter(status='received').aggregate(s=Sum('amount'))['s'] or 0
