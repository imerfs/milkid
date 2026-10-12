"""Payable-document treasury (خزانه اسناد پرداختی): cheques and notes the municipality issued, until cleared."""
from django.db import transaction

from main.accounting.ledger import _amount, _locked, _own, _own_or_invalid, _text, municipality_of
from main.models import Municipality, PayableDocument, PayableEvent
from main.office.errors import Conflict, Invalid

# status -> statuses it may move to
TRANSITIONS = {'issued': ('passed', 'returned', 'canceled'), 'returned': ('issued', 'canceled'),
               'passed': (), 'canceled': ()}


def documents_for(actor, year):
    muni = municipality_of(actor)
    _own(muni, year)
    return PayableDocument.objects.filter(municipality=muni, fiscal_year=year).select_related('party', 'bank_account')


def get_document(actor, doc_id):
    muni = municipality_of(actor)
    return _own(muni, PayableDocument.objects.select_related('fiscal_year', 'party', 'bank_account')
                .filter(pk=doc_id).first())


def issue(actor, year, *, kind, serial, party, bank_account, issue_date, due_date, amount, description=''):
    muni = municipality_of(actor)
    _own(muni, year)
    if year.is_closed:
        raise Conflict('سال مالی بسته شده است.')
    if kind not in dict(PayableDocument.KINDS):
        raise Invalid('نوع سند نامعتبر است.')
    party = _own_or_invalid(muni, party, 'در وجه')
    bank_account = _own_or_invalid(muni, bank_account, 'حساب بانک')
    if bank_account.kind != 'asset' or not bank_account.is_postable:
        raise Invalid('حساب بانک باید یک حساب دارایی قابل ثبت باشد.')
    if not (year.start_date <= issue_date <= year.end_date):
        raise Invalid('تاریخ صدور باید داخل سال مالی باشد.')
    if due_date < issue_date:
        raise Invalid('تاریخ سررسید قبل از تاریخ صدور است.')
    amount = _amount(amount)
    if amount <= 0:
        raise Invalid('مبلغ باید بیشتر از صفر باشد.')
    serial = _text(serial, 'سریال')[:60]
    with transaction.atomic():
        _locked(Municipality, muni.id)
        if PayableDocument.objects.filter(municipality=muni, kind=kind, serial=serial).exists():
            raise Conflict('سندی با این سریال قبلاً ثبت شده است.')
        doc = PayableDocument.objects.create(
            municipality=muni, fiscal_year=year, kind=kind, serial=serial, party=party, bank_account=bank_account,
            issue_date=issue_date, due_date=due_date, amount=amount, status='issued', status_date=issue_date,
            description=_text(description, 'شرح', False)[:300], created_by=actor)
        PayableEvent.objects.create(document=doc, status='issued', date=issue_date, user=actor)
    return doc


def change_status(actor, doc, status, on, note=''):
    muni = municipality_of(actor)
    _own(muni, doc)
    if status not in dict(PayableDocument.STATUSES):
        raise Invalid('وضعیت نامعتبر است.')
    with transaction.atomic():
        doc = _locked(PayableDocument, doc.pk)
        if status not in TRANSITIONS[doc.status]:
            raise Conflict('تغییر از وضعیت «%s» به این وضعیت مجاز نیست.' % doc.get_status_display())
        if on < doc.issue_date:
            raise Invalid('تاریخ تغییر وضعیت قبل از تاریخ صدور است.')
        doc.status, doc.status_date = status, on
        doc.save(update_fields=['status', 'status_date'])
        PayableEvent.objects.create(document=doc, status=status, date=on, user=actor,
                                    note=_text(note, 'توضیح', False)[:300])
    return doc
