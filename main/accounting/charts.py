"""Numbers behind the charts of the accountant workspace: monthly resources vs uses, the biggest accounts, budget vs actual
and cash collected per month. Whole rials; months are Jalali months of the fiscal year."""
from collections import defaultdict

import jdatetime
from django.db.models import Sum

from main.accounting import budget, ledger
from main.accounting.builder import JALALI_MONTHS
from main.models import BillPayment, VoucherLine

TOP = 8


def _month_index(day):
    return jdatetime.date.fromgregorian(date=day).month - 1


def data(actor, year, *, final_only=False):
    muni = ledger.municipality_of(actor)
    ledger._own(muni, year)
    lines = VoucherLine.objects.filter(voucher__municipality=muni, voucher__fiscal_year=year, voucher__deleted_at__isnull=True,
                                       account__kind__in=budget.BUDGET_KINDS).exclude(voucher__kind__in=('temp_closing', 'closing'))
    if final_only:
        lines = lines.filter(voucher__status='final')
    resources, uses = [0] * 12, [0] * 12
    for row in lines.values('voucher__date', 'account__kind').annotate(d=Sum('debit'), c=Sum('credit')):
        month = _month_index(row['voucher__date'])
        if row['account__kind'] == 'budget_resource':
            resources[month] += int((row['c'] or 0) - (row['d'] or 0))
        else:
            uses[month] += int((row['d'] or 0) - (row['c'] or 0))
    collected = defaultdict(int)
    for row in BillPayment.objects.filter(bill__municipality=muni, bill__fiscal_year=year).values('date').annotate(s=Sum('amount')):
        collected[_month_index(row['date'])] += int(row['s'])
    rows, totals = budget.report(actor, year, include_temporary=not final_only)

    def top(kind):
        picked = sorted((r for r in rows if r['kind'] == kind and r['actual'] > 0), key=lambda r: -r['actual'])[:TOP]
        return {'labels': [r['title'] for r in picked], 'actual': [int(r['actual']) for r in picked],
                'budget': [int(r['budget']) for r in picked]}

    return {'months': JALALI_MONTHS, 'resources': resources, 'uses': uses, 'collected': [collected[i] for i in range(12)],
            'top_uses': top('use'), 'top_resources': top('resource'),
            'budget_vs_actual': {'labels': ['منابع', 'مصارف'],
                                 'budget': [int(totals['resource']['budget']), int(totals['use']['budget'])],
                                 'actual': [int(totals['resource']['actual']), int(totals['use']['actual'])]}}
