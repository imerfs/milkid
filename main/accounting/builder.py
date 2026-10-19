"""Report builder (گزارش‌ساز) and pivot analyser (تحلیل‌گر): pick a dataset, group it by one or two dimensions and sum a measure.

Everything is read-only and scoped to the actor's municipality and the chosen fiscal year. Grouping is done in Python over a
bounded set of rows so that Jalali months (which SQL cannot group by) work like any other dimension.
"""
from collections import defaultdict
from decimal import Decimal

import jdatetime

from main.accounting import ledger
from main.models import (Bill, BillPayment, Contract, ContractStatement, Installment, InstallmentPlan, PayableDocument,
                         PayrollSlip, TransportIncome, Voucher, VoucherLine)
from main.models_payroll import CALC_GROUPS
from main.office.errors import Invalid

MAX_ROWS = 100_000
MAX_COLUMNS = 40
JALALI_MONTHS = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند']


def jalali_month(value):
    if value is None:
        return '—'
    j = jdatetime.date.fromgregorian(date=value)
    return f'{j.year}/{j.month:02d} {JALALI_MONTHS[j.month - 1]}'


def _choice(choices):
    mapping = dict(choices)
    return lambda value: mapping.get(value, value or '—')


def _text(*fields):
    """Join the given row fields (e.g. account code and title) into one label."""
    return lambda row: ' - '.join(str(row[f]) for f in fields if row.get(f) not in (None, '')) or '—'


def _months_in_range(year_number, date_from, date_to):
    """Jalali months (1-12) of ``year_number`` that overlap the date range; the whole year when no range is given."""
    months = []
    for month in range(1, 13):
        first = jdatetime.date(year_number, month, 1).togregorian()
        after = (jdatetime.date(year_number + 1, 1, 1) if month == 12 else jdatetime.date(year_number, month + 1, 1)).togregorian()
        if (date_from is None or after > date_from) and (date_to is None or first <= date_to):
            months.append(month)
    return months


def _slip_month(row):
    return f"{row['run__year']}/{row['run__month']:02d} {JALALI_MONTHS[row['run__month'] - 1]}"


# dataset -> {label, queryset(muni, year, final_only), date field, dimensions, measures}
# dimension: (label, fields to fetch, row -> label); measure: (label, field or None for a count, is money)
DATASETS = {
    'lines': {
        'label': 'ردیف‌های اسناد',
        'queryset': lambda muni, year, final: VoucherLine.objects.filter(
            voucher__municipality=muni, voucher__fiscal_year=year, voucher__deleted_at__isnull=True,
            **({'voucher__status': 'final'} if final else {})),
        'date': 'voucher__date',
        'dimensions': {
            'account': ('حساب', ['account__code', 'account__title'], _text('account__code', 'account__title')),
            'party': ('طرف حساب', ['party__name'], _text('party__name')),
            'cost_center': ('مرکز هزینه', ['cost_center__title'], _text('cost_center__title')),
            'kind': ('نوع سند', ['voucher__kind'], lambda r: _choice(Voucher.KINDS)(r['voucher__kind'])),
            'status': ('وضعیت سند', ['voucher__status'], lambda r: _choice(Voucher.STATUSES)(r['voucher__status'])),
            'month': ('ماه', ['voucher__date'], lambda r: jalali_month(r['voucher__date'])),
            'account_kind': ('نوع حساب', ['account__kind'], lambda r: r['account__kind']),
        },
        'measures': {'debit': ('بدهکار', 'debit', True), 'credit': ('بستانکار', 'credit', True), 'count': ('تعداد ردیف', None, False)},
    },
    'bills': {
        'label': 'فیش‌های نقدی',
        'queryset': lambda muni, year, final: Bill.objects.filter(municipality=muni, fiscal_year=year, canceled_at__isnull=True),
        'date': 'date',
        'dimensions': {
            'party': ('پرداخت‌کننده', ['party__name'], _text('party__name')),
            'income_account': ('حساب درآمد', ['income_account__code', 'income_account__title'],
                               _text('income_account__code', 'income_account__title')),
            'month': ('ماه', ['date'], lambda r: jalali_month(r['date'])),
        },
        'measures': {'amount': ('مبلغ فیش', 'amount', True), 'count': ('تعداد فیش', None, False)},
    },
    'payments': {
        'label': 'پرداخت‌های فیش',
        'queryset': lambda muni, year, final: BillPayment.objects.filter(bill__municipality=muni, bill__fiscal_year=year),
        'date': 'date',
        'dimensions': {
            'method': ('روش پرداخت', ['method'], lambda r: _choice(BillPayment.METHODS)(r['method'])),
            'bank_account': ('حساب بانک/صندوق', ['bank_account__code', 'bank_account__title'], _text('bank_account__code', 'bank_account__title')),
            'party': ('پرداخت‌کننده', ['bill__party__name'], _text('bill__party__name')),
            'month': ('ماه', ['date'], lambda r: jalali_month(r['date'])),
        },
        'measures': {'amount': ('مبلغ پرداخت', 'amount', True), 'count': ('تعداد پرداخت', None, False)},
    },
    'plans': {
        'label': 'پرونده‌های تقسیط',
        'queryset': lambda muni, year, final: InstallmentPlan.objects.filter(municipality=muni, fiscal_year=year),
        'date': 'date',
        'dimensions': {
            'party': ('مودی', ['party__name'], _text('party__name')),
            'status': ('وضعیت', ['status'], lambda r: _choice(InstallmentPlan.STATUSES)(r['status'])),
            'month': ('ماه', ['date'], lambda r: jalali_month(r['date'])),
        },
        'measures': {'plan_amount': ('مبلغ تقسیط', 'plan_amount', True), 'total_debt': ('کل بدهی', 'total_debt', True),
                     'cash_paid': ('پرداخت نقدی', 'cash_paid', True), 'count': ('تعداد پرونده', None, False)},
    },
    'installments': {
        'label': 'اقساط',
        'queryset': lambda muni, year, final: Installment.objects.filter(plan__municipality=muni, plan__fiscal_year=year),
        'date': 'due_date',
        'dimensions': {
            'party': ('مودی', ['plan__party__name'], _text('plan__party__name')),
            'method': ('روش پرداخت', ['method'], lambda r: _choice(Installment.METHODS)(r['method'])),
            'position': ('موقعیت چک', ['position'], lambda r: _choice(Installment.POSITIONS)(r['position'])),
            'month': ('ماه سررسید', ['due_date'], lambda r: jalali_month(r['due_date'])),
        },
        'measures': {'amount': ('مبلغ قسط', 'amount', True), 'paid_amount': ('پرداخت‌شده', 'paid_amount', True),
                     'count': ('تعداد اقساط', None, False)},
    },
    'contracts': {
        'label': 'قراردادها',
        'queryset': lambda muni, year, final: Contract.objects.filter(municipality=muni, fiscal_year=year),
        'date': 'date',
        'dimensions': {
            'contractor': ('پیمانکار', ['contractor__name'], _text('contractor__name')),
            'status': ('وضعیت', ['status'], lambda r: _choice(Contract.STATUSES)(r['status'])),
            'cost_center': ('مرکز هزینه', ['cost_center__title'], _text('cost_center__title')),
            'month': ('ماه', ['date'], lambda r: jalali_month(r['date'])),
        },
        'measures': {'amount': ('مبلغ قرارداد', 'amount', True), 'ceiling': ('سقف مبلغ', 'ceiling', True),
                     'count': ('تعداد قرارداد', None, False)},
    },
    'statements': {
        'label': 'صورت‌وضعیت‌های قراردادها',
        'queryset': lambda muni, year, final: ContractStatement.objects.filter(
            contract__municipality=muni, contract__fiscal_year=year, canceled_at__isnull=True),
        'date': 'date',
        'dimensions': {
            'contractor': ('پیمانکار', ['contract__contractor__name'], _text('contract__contractor__name')),
            'contract': ('قرارداد', ['contract__number', 'contract__subject'], _text('contract__number', 'contract__subject')),
            'month': ('ماه', ['date'], lambda r: jalali_month(r['date'])),
        },
        'measures': {'gross': ('کارکرد ناخالص', 'gross', True), 'vat': ('ارزش افزوده', 'vat', True), 'tax': ('مالیات', 'tax', True),
                     'good_performance': ('حسن انجام کار', 'good_performance', True),
                     'contractor_insurance': ('بیمه پیمانکار', 'contractor_insurance', True),
                     'employer_insurance': ('بیمه کارفرما', 'employer_insurance', True), 'net': ('خالص پرداختنی', 'net', True),
                     'count': ('تعداد صورت‌وضعیت', None, False)},
    },
    'payables': {
        'label': 'اسناد پرداختی (چک و سفته)',
        'queryset': lambda muni, year, final: PayableDocument.objects.filter(municipality=muni, fiscal_year=year),
        'date': 'due_date',
        'dimensions': {
            'party': ('در وجه', ['party__name'], _text('party__name')),
            'kind': ('نوع', ['kind'], lambda r: _choice(PayableDocument.KINDS)(r['kind'])),
            'status': ('وضعیت', ['status'], lambda r: _choice(PayableDocument.STATUSES)(r['status'])),
            'month': ('ماه سررسید', ['due_date'], lambda r: jalali_month(r['due_date'])),
        },
        'measures': {'amount': ('مبلغ', 'amount', True), 'count': ('تعداد', None, False)},
    },
    'transport': {
        'label': 'درآمد حمل و نقل',
        'queryset': lambda muni, year, final: TransportIncome.objects.filter(municipality=muni, fiscal_year=year, status='received'),
        'date': 'date',
        'dimensions': {
            'service': ('نوع خدمت', ['service'], _text('service')),
            'party': ('پرداخت‌کننده', ['party__name'], _text('party__name')),
            'month': ('ماه', ['date'], lambda r: jalali_month(r['date'])),
        },
        'measures': {'amount': ('مبلغ', 'amount', True), 'count': ('تعداد', None, False)},
    },
    'payroll': {
        'label': 'فیش‌های حقوق',
        'queryset': lambda muni, year, final: PayrollSlip.objects.filter(
            run__municipality=muni, run__year=year.year, **({'run__status': 'final'} if final else {})),
        'date': None,
        'period': lambda qs, year, date_from, date_to: qs.filter(run__month__in=_months_in_range(year.year, date_from, date_to)),
        'dimensions': {
            'employee': ('پرسنل', ['employee__first_name', 'employee__last_name'],
                         lambda r: f"{r['employee__first_name']} {r['employee__last_name']}"),
            'group': ('گروه محاسباتی', ['employee__calc_group'], lambda r: _choice(CALC_GROUPS)(r['employee__calc_group'])),
            'list_title': ('عنوان لیست', ['employee__list_title'], _text('employee__list_title')),
            'month': ('ماه حقوق', ['run__year', 'run__month'], _slip_month),
        },
        'measures': {'net': ('خالص پرداختی', 'net', True), 'gross': ('ناخالص', 'gross', True), 'tax': ('مالیات', 'tax', True),
                     'insurance_employee': ('بیمه سهم کارمند', 'insurance_employee', True),
                     'insurance_org': ('بیمه سهم دهیاری', 'insurance_org', True), 'allowances': ('مزایا', 'allowances', True),
                     'overtime': ('اضافه کار', 'overtime', True), 'deductions': ('کسورات', 'deductions', True),
                     'count': ('تعداد فیش', None, False)},
    },
}


def catalogue():
    """What the screen offers: ``{dataset: {'label', 'dimensions': [(key, label)], 'measures': [(key, label)]}}``."""
    return {key: {'label': spec['label'], 'dimensions': [(k, v[0]) for k, v in spec['dimensions'].items()],
                  'measures': [(k, v[0]) for k, v in spec['measures'].items()]} for key, spec in DATASETS.items()}


def build(actor, year, dataset, group, *, measure=None, column=None, date_from=None, date_to=None, final_only=False):
    """Grouped table; with ``column`` a pivot of ``group`` (rows) by ``column`` (columns).

    Returns ``{'label', 'columns', 'rows', 'totals', 'money': set(column indexes), 'truncated': False}`` in the same shape
    as main/accounting/reports so the screen and the Excel export are shared.
    """
    if dataset not in DATASETS:
        raise Invalid('مجموعه داده نامعتبر است.')
    spec = DATASETS[dataset]
    if group not in spec['dimensions']:
        raise Invalid('ردیف‌های گزارش (گروه‌بندی) نامعتبر است.')
    if column and column not in spec['dimensions']:
        raise Invalid('ستون‌های گزارش نامعتبر است.')
    measure = measure or next(iter(spec['measures']))
    if measure not in spec['measures']:
        raise Invalid('مقدار گزارش نامعتبر است.')
    muni = ledger.municipality_of(actor)
    ledger._own(muni, year)
    qs = spec['queryset'](muni, year, final_only)
    if spec['date'] is None:                                  # payroll rows belong to a Jalali month, not to a day
        if date_from or date_to:
            qs = spec['period'](qs, year, date_from, date_to)
    else:
        if date_from:
            qs = qs.filter(**{f"{spec['date']}__gte": date_from})
        if date_to:
            qs = qs.filter(**{f"{spec['date']}__lte": date_to})
    if qs.count() > MAX_ROWS:
        raise Invalid('تعداد ردیف‌ها بیش از حد است؛ بازه تاریخ را کوچک‌تر کنید.')
    dim_group, dim_col = spec['dimensions'][group], spec['dimensions'].get(column) if column else None
    m_label, m_field, m_money = spec['measures'][measure]
    fields = set(dim_group[1]) | set(dim_col[1] if dim_col else []) | ({m_field} if m_field else set())
    cells = defaultdict(lambda: defaultdict(Decimal))
    columns_seen = set()
    for row in qs.values(*fields):
        label = dim_group[2](row)
        col_label = dim_col[2](row) if dim_col else None
        value = row[m_field] if m_field else 1
        cells[label][col_label] += Decimal(value or 0)
        columns_seen.add(col_label)
    if dim_col and len(columns_seen) > MAX_COLUMNS:
        raise Invalid(f'ستون‌ها بیش از {MAX_COLUMNS} مقدار متفاوت دارند؛ ستون دیگری انتخاب کنید.')
    names = sorted(columns_seen, key=str) if dim_col else [None]
    heads = [dim_group[0]] + ([str(n) for n in names] + ['جمع'] if dim_col else [m_label])
    rows, totals = [], [Decimal(0)] * (len(names) + (1 if dim_col else 0))
    for label in sorted(cells, key=str):
        values = [cells[label].get(n, Decimal(0)) for n in names]
        values = values + [sum(values, Decimal(0))] if dim_col else values
        rows.append([label] + values)
        totals = [t + v for t, v in zip(totals, values)]
    money = set(range(1, len(heads))) if m_money else set()
    return {'label': f"{spec['label']} بر حسب {dim_group[0]}" + (f' و {dim_col[0]}' if dim_col else ''), 'columns': heads,
            'rows': rows, 'totals': (['جمع'] + totals) if rows else [], 'money': money, 'truncated': False,
            'measure_label': m_label}
