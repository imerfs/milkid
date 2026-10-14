"""Reports of the accountant workspace (گزارش‌گیری): one registry, each report returns a plain table.

``run(actor, year, key, params)`` -> ``{'columns': [...], 'rows': [[...]], 'money': {column index}, 'totals': [...]|None}``.
Dates in rows are Jalali strings, money is whole rials. Every query is scoped to the actor's municipality and year.
"""
from decimal import Decimal

from django.db.models import Q, Sum

from main.accounting import contracts as contract_rules
from main.accounting import ledger
from main.accounting.parse import jalali_str, parse_int_or_none, parse_jalali
from main.models import (Bill, Contract, CostCenter, Guarantee, InstallmentPlan, Party, PayableDocument, TransportIncome,
                         VoucherLine)
from main.office.errors import Invalid, NotFound

MAX_ROWS = 5000


def _range(qs, params, field, lo='date_from', hi='date_to'):
    for key, lookup in ((lo, f'{field}__gte'), (hi, f'{field}__lte')):
        raw = (params.get(key) or '').strip()
        if raw:
            qs = qs.filter(**{lookup: parse_jalali(raw)})
    return qs


def _own_pk(model, muni, params, key, label):
    pk = parse_int_or_none(params.get(key))
    obj = model.objects.filter(municipality=muni, pk=pk).first() if pk else None
    if obj is None:
        raise Invalid(f'{label} را انتخاب کنید.')
    return obj


def _vouchers(actor, year, muni, params):
    qs = ledger.vouchers_for(actor, year).annotate(d=Sum('lines__debit'), c=Sum('lines__credit'))
    qs = _range(qs, params, 'date')
    if params.get('status') in ('temporary', 'final'):
        qs = qs.filter(status=params['status'])
    if params.get('kind'):
        qs = qs.filter(kind=params['kind'])
    lo, hi = parse_int_or_none(params.get('number_from')), parse_int_or_none(params.get('number_to'))
    if lo is not None:
        qs = qs.filter(number__gte=lo)
    if hi is not None:
        qs = qs.filter(number__lte=hi)
    if (params.get('q') or '').strip():
        qs = qs.filter(description__icontains=params['q'].strip())
    rows = [[v.number, v.ref, jalali_str(v.date), v.get_kind_display(), v.description, v.get_status_display(),
             v.d or 0, v.c or 0] for v in qs.order_by('number')[:MAX_ROWS]]
    return ['شماره', 'شناسه', 'تاریخ', 'نوع', 'شرح', 'وضعیت', 'بدهکار', 'بستانکار'], rows, {6, 7}, [6, 7]


def _lines(muni, year, params):
    qs = VoucherLine.objects.filter(voucher__municipality=muni, voucher__fiscal_year=year,
                                    voucher__deleted_at__isnull=True)
    if params.get('final') == '1':
        qs = qs.filter(voucher__status='final')
    return _range(qs, params, 'voucher__date').select_related('voucher', 'account')


def _running(qs, ledger_cols):
    rows, balance = [], Decimal(0)
    for ln in qs.order_by('voucher__date', 'voucher__number', 'row')[:MAX_ROWS]:
        balance += ln.debit - ln.credit
        rows.append([jalali_str(ln.voucher.date), ln.voucher.number, ln.account.code, ln.description or ln.voucher.description,
                     ln.debit, ln.credit, balance])
    return ledger_cols, rows, {4, 5, 6}, [4, 5]


def _party_ledger(actor, year, muni, params):
    party = _own_pk(Party, muni, params, 'party', 'طرف حساب')
    return _running(_lines(muni, year, params).filter(party=party), ['تاریخ', 'سند', 'حساب', 'شرح', 'بدهکار', 'بستانکار', 'مانده'])


def _cost_center(actor, year, muni, params):
    center = _own_pk(CostCenter, muni, params, 'cost_center', 'مرکز هزینه')
    return _running(_lines(muni, year, params).filter(cost_center=center), ['تاریخ', 'سند', 'حساب', 'شرح', 'بدهکار', 'بستانکار', 'مانده'])


def _journal(actor, year, muni, params):
    rows = [[jalali_str(ln.voucher.date), ln.voucher.number, ln.account.code, ln.account.title,
             ln.description or ln.voucher.description, ln.debit, ln.credit]
            for ln in _lines(muni, year, params).order_by('voucher__date', 'voucher__number', 'row')[:MAX_ROWS]]
    return ['تاریخ', 'سند', 'کد حساب', 'عنوان حساب', 'شرح', 'بدهکار', 'بستانکار'], rows, {5, 6}, [5, 6]


def _bills(actor, year, muni, params):
    qs = _range(Bill.objects.filter(municipality=muni, fiscal_year=year).select_related('party').annotate(
        paid=Sum('payments__amount')), params, 'date')
    if (params.get('q') or '').strip():
        q = params['q'].strip()
        qs = qs.filter(Q(description__icontains=q) | Q(party__name__icontains=q))
    rows = []
    for b in qs.order_by('number')[:MAX_ROWS]:
        paid = b.paid or 0
        state = 'ابطال' if b.canceled_at else 'پرداخت‌شده' if paid >= b.amount else 'قسمتی' if paid else 'پرداخت‌نشده'
        if params.get('status') and params['status'] != state:
            continue
        rows.append([b.number, jalali_str(b.date), b.party.name, b.description, b.amount, paid, state])
    return ['شماره', 'تاریخ', 'پرداخت‌کننده', 'شرح', 'مبلغ', 'پرداخت‌شده', 'وضعیت'], rows, {4, 5}, [4, 5]


def _plans(actor, year, muni, params):
    qs = _range(InstallmentPlan.objects.filter(municipality=muni, fiscal_year=year).select_related('party'), params, 'date')
    if params.get('status') in dict(InstallmentPlan.STATUSES):
        qs = qs.filter(status=params['status'])
    rows = [[p.number, jalali_str(p.date), p.party.name, p.total_debt, p.cash_paid, p.plan_amount, p.count,
             p.get_status_display()] for p in qs.order_by('number')[:MAX_ROWS]]
    return ['شماره', 'تاریخ', 'مودی', 'کل بدهی', 'پرداخت نقدی', 'مبلغ تقسیط', 'تعداد اقساط', 'وضعیت'], rows, {3, 4, 5}, [3, 4, 5]


def _guarantees(actor, year, muni, params):
    qs = Guarantee.objects.filter(municipality=muni).select_related('party', 'contract', 'plan')
    if params.get('status') in dict(Guarantee.STATUSES):
        qs = qs.filter(status=params['status'])
    qs = _range(qs, params, 'expires_on')
    rows = [[g.get_kind_display(), g.party.name, f'{g.get_doc_kind_display()} {g.serial}',
             f'قرارداد {g.contract.number}' if g.contract else f'تقسیط {g.plan.number}' if g.plan else '', jalali_str(g.expires_on),
             g.amount, g.get_status_display()] for g in qs.order_by('expires_on')[:MAX_ROWS]]
    return ['نوع', 'صاحب ضمانت‌نامه', 'مدرک', 'مربوط به', 'سررسید', 'مبلغ', 'وضعیت'], rows, {5}, [5]


def _payables(actor, year, muni, params):
    qs = _range(PayableDocument.objects.filter(municipality=muni, fiscal_year=year).select_related('party'), params,
                'due_date')
    if params.get('status') in dict(PayableDocument.STATUSES):
        qs = qs.filter(status=params['status'])
    rows = [[d.get_kind_display(), d.serial, d.party.name, jalali_str(d.due_date), d.amount, d.get_status_display()]
            for d in qs.order_by('due_date')[:MAX_ROWS]]
    return ['نوع', 'سریال', 'در وجه', 'سررسید', 'مبلغ', 'وضعیت'], rows, {4}, [4]


def _contracts(actor, year, muni, params):
    qs = Contract.objects.filter(municipality=muni, fiscal_year=year).select_related('contractor')
    if params.get('status') in dict(Contract.STATUSES):
        qs = qs.filter(status=params['status'])
    rows = [[c.number, c.subject, c.contractor.name, c.amount, contract_rules.used(c), c.get_status_display()]
            for c in qs.order_by('number')[:MAX_ROWS]]
    return ['شماره', 'موضوع', 'پیمانکار', 'مبلغ', 'کارکرد تاکنون', 'وضعیت'], rows, {3, 4}, [3, 4]


def _transport(actor, year, muni, params):
    qs = _range(TransportIncome.objects.filter(municipality=muni, fiscal_year=year, status='received'), params, 'date')
    rows = [[t.number, jalali_str(t.date), t.plate, t.service, t.amount] for t in qs.order_by('number')[:MAX_ROWS]]
    return ['شماره', 'تاریخ', 'پلاک', 'نوع خدمت', 'مبلغ'], rows, {4}, [4]


# key -> (label, builder, filters it understands)
REPORTS = {
    'vouchers': ('فهرست اسناد', _vouchers, ('date', 'number', 'status_voucher', 'kind', 'q')),
    'journal': ('دفتر روزنامه', _journal, ('date', 'final')),
    'party_ledger': ('گردش طرف‌حساب', _party_ledger, ('party', 'date', 'final')),
    'cost_center': ('گردش مرکز هزینه', _cost_center, ('cost_center', 'date', 'final')),
    'bills': ('فیش‌های نقدی', _bills, ('date', 'status_bill', 'q')),
    'plans': ('پرونده‌های تقسیط', _plans, ('date', 'status_plan')),
    'guarantees': ('ضمانت‌نامه‌ها', _guarantees, ('date', 'status_guarantee')),
    'payables': ('اسناد پرداختی', _payables, ('date', 'status_payable')),
    'contracts': ('قراردادها', _contracts, ('status_contract',)),
    'transport': ('درآمد حمل و نقل', _transport, ('date',)),
}


def run(actor, year, key, params):
    if key not in REPORTS:
        raise NotFound()
    muni = ledger.municipality_of(actor)
    ledger._own(muni, year)
    columns, rows, money, total_cols = REPORTS[key][1](actor, year, muni, params)
    totals = None
    if rows and total_cols:
        totals = ['' for _ in columns]
        totals[0] = 'جمع'
        for i in total_cols:
            totals[i] = sum((r[i] for r in rows), Decimal(0))
    return {'label': REPORTS[key][0], 'columns': columns, 'rows': rows, 'money': money, 'totals': totals,
            'truncated': len(rows) >= MAX_ROWS}
