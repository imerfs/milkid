"""Cash bills (فیش نقدی) and their payments. Every payment posts a temporary income voucher in the same transaction."""
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from main.accounting import ledger
from main.accounting.ledger import _amount, _locked, _own, _own_or_invalid, _text, municipality_of
from main.models import Bill, BillPayment, Municipality
from main.office.errors import Conflict, Invalid


def _positive(value):
    amount = _amount(value)
    if amount <= 0:
        raise Invalid('مبلغ باید بیشتر از صفر باشد.')
    return amount


def get_bill(actor, bill_id):
    muni = municipality_of(actor)
    return _own(muni, Bill.objects.select_related('fiscal_year', 'party', 'income_account').filter(pk=bill_id).first())


def bills_for(actor, year):
    muni = municipality_of(actor)
    _own(muni, year)
    return Bill.objects.filter(municipality=muni, fiscal_year=year).select_related('party').annotate(
        paid=Sum('payments__amount')).order_by('-number')


def summary(bill):
    paid = bill.payments.aggregate(s=Sum('amount'))['s'] or Decimal(0)
    status = 'canceled' if bill.canceled_at else 'paid' if paid >= bill.amount else 'partial' if paid else 'unpaid'
    return {'paid': paid, 'remaining': bill.amount - paid, 'status': status}


def issue_bill(actor, year, on, party, income_account, amount, description):
    muni = municipality_of(actor)
    _own(muni, year)
    if year.is_closed:
        raise Conflict('سال مالی بسته شده است.')
    if not (year.start_date <= on <= year.end_date):
        raise Invalid('تاریخ فیش باید داخل سال مالی باشد.')
    party = _own_or_invalid(muni, party, 'طرف حساب')
    income_account = _own_or_invalid(muni, income_account, 'حساب درآمد')
    if income_account.kind != 'budget_resource' or not income_account.is_postable:
        raise Invalid('حساب درآمد باید یکی از حساب‌های قابل ثبت منابع باشد.')
    amount, description = _positive(amount), _text(description, 'شرح فیش')
    with transaction.atomic():
        _locked(Municipality, muni.id)
        last = Bill.objects.filter(municipality=muni, fiscal_year=year).order_by('-number').values_list(
            'number', flat=True).first() or 0
        return Bill.objects.create(municipality=muni, fiscal_year=year, number=last + 1, date=on, party=party,
                                   income_account=income_account, description=description, amount=amount,
                                   created_by=actor)


def record_payment(actor, bill, on, amount, bank_account, method, reference=''):
    muni = municipality_of(actor)
    _own(muni, bill)
    if method not in dict(BillPayment.METHODS):
        raise Invalid('روش پرداخت نامعتبر است.')
    bank_account = _own_or_invalid(muni, bank_account, 'حساب بانک/صندوق')
    if bank_account.kind != 'asset' or not bank_account.is_postable:
        raise Invalid('حساب بانک/صندوق باید یک حساب دارایی قابل ثبت باشد.')
    amount, reference = _positive(amount), _text(reference, 'شماره پیگیری', required=False)
    with transaction.atomic():
        bill = _locked(Bill, bill.pk)
        year = bill.fiscal_year
        if bill.canceled_at:
            raise Conflict('این فیش ابطال شده است.')
        if amount > summary(bill)['remaining']:
            raise Conflict('مبلغ پرداخت بیشتر از باقی‌مانده فیش است.')
        voucher = ledger.create_voucher(
            actor, year, on, 'income', f'دریافت فیش نقدی شماره {bill.number} - {bill.description}'[:500],
            [{'account': bank_account, 'debit': amount, 'credit': 0, 'party': bill.party},
             {'account': bill.income_account, 'debit': 0, 'credit': amount, 'party': bill.party}])
        return BillPayment.objects.create(bill=bill, date=on, method=method, amount=amount,
                                          bank_account=bank_account, reference=reference, voucher=voucher)


def cancel_bill(actor, bill):
    muni = municipality_of(actor)
    _own(muni, bill)
    with transaction.atomic():
        bill = _locked(Bill, bill.pk)
        if bill.payments.exists():
            raise Conflict('فیش دارای پرداخت قابل ابطال نیست.')
        if bill.canceled_at is None:
            bill.canceled_at = timezone.now()
            bill.save(update_fields=['canceled_at'])
    return bill
