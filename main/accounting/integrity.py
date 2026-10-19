"""Data integrity check (کنترل صحت داده): looks for rows that break the ledger's own rules.

Nothing is changed; the result lists each check with the offending rows so the accountant can fix them.
Every query is scoped to the actor's municipality.
"""
from decimal import Decimal

from django.db.models import Count, F, Q, Sum

from main.accounting import ledger
from main.models import Account, Bill, BillPayment, Voucher, VoucherLine

SHOWN = 15


def _describe(voucher):
    return f'سند {voucher.number} (سال {voucher.fiscal_year.year})'


def run(actor, year=None):
    """List of ``{'key', 'title', 'count', 'items'}``; ``count == 0`` means the check passed."""
    muni = ledger.municipality_of(actor)
    if year is not None:
        ledger._own(muni, year)
    vouchers = Voucher.objects.filter(municipality=muni, deleted_at__isnull=True).select_related('fiscal_year')
    lines = VoucherLine.objects.filter(voucher__municipality=muni, voucher__deleted_at__isnull=True)
    if year is not None:
        vouchers, lines = vouchers.filter(fiscal_year=year), lines.filter(voucher__fiscal_year=year)
    results = []

    def add(key, title, rows):
        rows = list(rows)
        results.append({'key': key, 'title': title, 'count': len(rows), 'items': rows[:SHOWN], 'more': max(len(rows) - SHOWN, 0)})

    annotated = vouchers.annotate(d=Sum('lines__debit'), c=Sum('lines__credit'), n=Count('lines'))
    add('unbalanced', 'اسناد بی‌حساب (جمع بدهکار و بستانکار برابر نیست)',
        (f'{_describe(v)}: بدهکار {v.d or 0:,} / بستانکار {v.c or 0:,}' + (' - قطعی' if v.status == 'final' else '')
         for v in annotated.filter(~Q(d=F('c')) | Q(d__isnull=True) | Q(c__isnull=True))))
    add('few_lines', 'اسناد قطعی با کمتر از دو ردیف', (_describe(v) for v in annotated.filter(status='final', n__lt=2)))
    add('not_postable', 'ردیف‌هایی که روی حساب غیرقابل‌ثبت (گروه) خورده‌اند',
        (f'{_describe(ln.voucher)}، ردیف {ln.row}: {ln.account.code}' for ln in
         lines.filter(account__is_postable=False).select_related('voucher__fiscal_year', 'account')))
    add('no_party', 'ردیف‌های حساب نیازمند طرف حساب که طرف حساب ندارند',
        (f'{_describe(ln.voucher)}، ردیف {ln.row}: {ln.account.code}' for ln in
         lines.filter(account__requires_party=True, party__isnull=True).select_related('voucher__fiscal_year', 'account')))
    add('foreign_rows', 'ردیف‌هایی که به حساب، طرف حساب یا مرکز هزینه‌ی دهیاری دیگری وصل‌اند',
        (f'{_describe(ln.voucher)}، ردیف {ln.row}' for ln in
         lines.filter(~Q(account__municipality=muni) | (Q(party__isnull=False) & ~Q(party__municipality=muni))
                      | (Q(cost_center__isnull=False) & ~Q(cost_center__municipality=muni))).select_related('voucher__fiscal_year')))
    add('out_of_year', 'اسناد با تاریخ بیرون از سال مالی خودشان',
        (_describe(v) for v in vouchers.filter(Q(date__lt=F('fiscal_year__start_date')) | Q(date__gt=F('fiscal_year__end_date')))))
    duplicates = []
    for kind, label in (('opening', 'افتتاحیه'), ('temp_closing', 'بستن حساب‌های موقت'), ('closing', 'اختتامیه')):
        for row in vouchers.filter(kind=kind).values('fiscal_year__year').annotate(n=Count('id')).filter(n__gt=1):
            duplicates.append(f'سال {row["fiscal_year__year"]}: {row["n"]} سند {label}')
    add('duplicate_year_end', 'بیش از یک سند افتتاحیه / اختتامیه / بستن موقت در یک سال', duplicates)
    bills = Bill.objects.filter(municipality=muni)
    if year is not None:
        bills = bills.filter(fiscal_year=year)
    add('overpaid_bill', 'فیش‌هایی که پرداخت‌شده‌شان از مبلغ فیش بیشتر است',
        (f'فیش {b.number} (سال {b.fiscal_year.year})' for b in bills.select_related('fiscal_year').annotate(p=Sum('payments__amount'))
         .filter(p__gt=F('amount'))))
    payments = BillPayment.objects.filter(bill__in=bills).select_related('bill__fiscal_year', 'voucher').annotate(
        v=Sum('voucher__lines__debit'))
    broken = []
    for pay in payments:
        problems = []
        if pay.voucher.deleted_at is not None:
            problems.append('سند پرداخت حذف شده است')
        elif (pay.v or Decimal(0)) != pay.amount:
            problems.append('مبلغ سند با مبلغ پرداخت یکی نیست')
        if pay.bill.canceled_at:
            problems.append('فیش ابطال‌شده پرداخت دارد')
        if problems:
            broken.append(f'فیش {pay.bill.number} (سال {pay.bill.fiscal_year.year}): ' + '، '.join(problems))
    add('payment_voucher', 'پرداخت‌های فیش با سند ناسازگار', broken)
    totals = lines.aggregate(d=Sum('debit'), c=Sum('credit'))
    gap = (totals['d'] or 0) - (totals['c'] or 0)
    add('trial_gap', 'جمع کل بدهکار و بستانکار دفتر برابر نیست', [f'اختلاف {gap:,} ریال'] if gap else [])
    accounts = Account.objects.filter(municipality=muni)
    add('orphan_parent', 'حساب‌هایی که والدشان در دهیاری دیگری است',
        (f'{a.code} - {a.title}' for a in accounts.filter(parent__isnull=False).exclude(parent__municipality=muni)))
    return results


def summary(results):
    return {'checks': len(results), 'failed': sum(1 for r in results if r['count']), 'problems': sum(r['count'] for r in results)}
