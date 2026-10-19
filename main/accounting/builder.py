"""Report builder (گزارش‌ساز) and pivot analyser (تحلیل‌گر): pick a dataset, group it by one or two dimensions and sum a measure.

Everything is read-only and scoped to the actor's municipality and the chosen fiscal year. Grouping is done in Python over a
bounded set of rows so that Jalali months (which SQL cannot group by) work like any other dimension.
"""
from collections import defaultdict
from decimal import Decimal

import jdatetime

from main.accounting import ledger
from main.models import Bill, BillPayment, Installment, InstallmentPlan, Voucher, VoucherLine
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
