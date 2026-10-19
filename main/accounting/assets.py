"""Fixed assets: register, yearly depreciation (a voucher per fiscal year) and disposal.

Depreciation is computed per Jalali year from the acquisition month (straight line, or declining balance at twice the
straight-line rate); the last year of life takes whatever is left so the book value ends at the salvage value. A year's
depreciation is posted as one temporary voucher (debit expense, credit accumulated depreciation) and can be re-issued while
that voucher is still temporary. Disposal posts its own voucher and carries the depreciation up to the disposal month.
"""
from decimal import ROUND_HALF_UP, Decimal

import jdatetime
from django.db import transaction
from django.db.models import Sum

from main.accounting import ledger
from main.accounting.ledger import _amount, _own, _own_or_invalid, _text, municipality_of
from main.models import Account, Asset, AssetDepreciation, FiscalYear, Voucher
from main.office.errors import Conflict, Invalid

ASSET_CODE, ACCUMULATED_CODE, EXPENSE_CODE = '211', '212', '6010401001'
RESULT_KINDS = ('budget_use', 'budget_resource', 'equity')


def _round(value):
    return Decimal(value).quantize(Decimal(1), rounding=ROUND_HALF_UP)


def _ym(day):
    j = jdatetime.date.fromgregorian(date=day)
    return j.year, j.month


def schedule(asset):
    """``{jalali_year: amount}``: depreciation of each year of the asset's life (up to the disposal month if disposed)."""
    start_year, start_month = _ym(asset.acquisition_date)
    gone = _ym(asset.disposed_on) if asset.disposed_on else None
    depreciable = asset.cost - asset.salvage
    out, accumulated = {}, Decimal(0)
    for year in range(start_year, start_year + asset.life_years + 1):
        if gone and year > gone[0]:
            break
        first_month = start_month if year == start_year else 1
        last_month = gone[1] if gone and year == gone[0] else 12
        months = last_month - first_month + 1
        remaining = depreciable - accumulated
        if months <= 0 or remaining <= 0:
            continue
        if asset.method == 'line':
            raw = depreciable / asset.life_years * months / 12
        else:
            book = asset.cost - accumulated
            raw = min(book * 2 / asset.life_years * months / 12, book - asset.salvage)
        amount = remaining if (year == start_year + asset.life_years and not gone) else min(_round(raw), remaining)
        if amount > 0:
            out[year] = amount
            accumulated += amount
    return out


def posted_total(asset):
    return asset.depreciations.aggregate(s=Sum('amount'))['s'] or Decimal(0)


def book_value(asset):
    return asset.cost - posted_total(asset)


def _account(muni, value, label, kinds, *, postable=True):
    account = _own_or_invalid(muni, value, label)
    if account.kind not in kinds or (postable and not account.is_postable):
        raise Invalid(f'{label} نامعتبر است.')
    return account


def ensure_accounts(actor):
    """Create the default fixed-asset accounts (idempotent) and return ``(asset, accumulated, expense)``."""
    muni = municipality_of(actor)
    parent = Account.objects.filter(municipality=muni, code='601').first()
    with transaction.atomic():
        asset, _ = Account.objects.get_or_create(municipality=muni, code=ASSET_CODE, defaults=dict(
            title='دارایی‌های ثابت', kind='asset', nature='debit'))
        accumulated, _ = Account.objects.get_or_create(municipality=muni, code=ACCUMULATED_CODE, defaults=dict(
            title='استهلاک انباشته', kind='asset', nature='credit'))
        expense, _ = Account.objects.get_or_create(municipality=muni, code=EXPENSE_CODE, defaults=dict(
            title='هزینه استهلاک', kind='budget_use', nature='debit', parent=parent))
    return asset, accumulated, expense


def default_accounts(muni):
    found = {a.code: a for a in Account.objects.filter(municipality=muni, code__in=(ASSET_CODE, ACCUMULATED_CODE, EXPENSE_CODE))}
    return found.get(ASSET_CODE), found.get(ACCUMULATED_CODE), found.get(EXPENSE_CODE)


def assets_for(actor):
    muni = municipality_of(actor)
    return Asset.objects.filter(municipality=muni).select_related('account', 'accumulated_account', 'expense_account')


def get_asset(actor, asset_id):
    muni = municipality_of(actor)
    return _own(muni, Asset.objects.filter(pk=asset_id).first())


def create_asset(actor, *, code, title, acquisition_date, cost, salvage, life_years, method, account, accumulated_account,
                 expense_account, description=''):
    muni = municipality_of(actor)
    code, title = _text(code, 'کد دارایی'), _text(title, 'عنوان')
    if len(code) > 30:
        raise Invalid('کد دارایی حداکثر ۳۰ نویسه است.')
    cost, salvage = _amount(cost), _amount(salvage)
    if cost <= 0:
        raise Invalid('بهای تمام‌شده باید بیشتر از صفر باشد.')
    if salvage >= cost:
        raise Invalid('ارزش اسقاط باید کمتر از بهای تمام‌شده باشد.')
    if not isinstance(life_years, int) or not 1 <= life_years <= 100:
        raise Invalid('عمر مفید باید بین ۱ تا ۱۰۰ سال باشد.')
    if method not in dict(Asset.METHODS):
        raise Invalid('روش استهلاک نامعتبر است.')
    account = _account(muni, account, 'حساب دارایی', ('asset',))
    accumulated_account = _account(muni, accumulated_account, 'حساب استهلاک انباشته', ('asset',))
    expense_account = _account(muni, expense_account, 'حساب هزینه استهلاک', ('budget_use',))
    if Asset.objects.filter(municipality=muni, code=code).exists():
        raise Conflict('دارایی دیگری با این کد ثبت شده است.')
    ledger.check_unlocked(muni, acquisition_date)
    return Asset.objects.create(
        municipality=muni, code=code, title=title, acquisition_date=acquisition_date, cost=cost, salvage=salvage,
        life_years=life_years, method=method, account=account, accumulated_account=accumulated_account,
        expense_account=expense_account, description=_text(description, 'توضیحات', required=False), created_by=actor)


def delete_asset(actor, asset):
    muni = municipality_of(actor)
    _own(muni, asset)
    if asset.depreciations.exists() or asset.status == 'disposed':
        raise Conflict('برای دارایی استهلاک ثبت شده یا خارج شده است؛ حذف ممکن نیست.')
    asset.delete()


def preview(actor, year):
    """Rows ``{'asset', 'amount', 'before', 'after'}`` for the assets that depreciate in ``year`` (re-issuing replaces it)."""
    muni = municipality_of(actor)
    _own(muni, year)
    rows, missing = [], []
    for asset in Asset.objects.filter(municipality=muni).select_related('account', 'accumulated_account', 'expense_account'):
        if asset.disposed_on and asset.disposed_on <= year.end_date:
            continue                                  # a disposed asset's last depreciation is in its disposal voucher
        plan = schedule(asset)
        amount = plan.get(year.year, Decimal(0))
        if amount <= 0:
            continue
        before = asset.depreciations.exclude(fiscal_year=year).aggregate(s=Sum('amount'))['s'] or Decimal(0)
        due_before = sum((v for y, v in plan.items() if y < year.year), Decimal(0))
        if before < due_before:
            missing.append(asset.code)
        rows.append({'asset': asset, 'amount': amount, 'before': before, 'after': before + amount})
    return rows, missing


def post_year(actor, year):
    """Issue (or re-issue) the year's depreciation voucher as a temporary voucher."""
    muni = municipality_of(actor)
    _own(muni, year)
    if year.is_closed:
        raise Conflict('سال مالی بسته شده است.')
    rows, _ = preview(actor, year)
    if not rows:
        raise Conflict('در این سال استهلاکی برای ثبت وجود ندارد.')
    old = AssetDepreciation.objects.filter(fiscal_year=year, asset__municipality=muni).exclude(asset__disposed_on__lte=year.end_date)
    with transaction.atomic():
        old_vouchers = {d.voucher for d in old.select_related('voucher')}
        for voucher in old_vouchers:
            if voucher.status == 'final':
                raise Conflict('سند استهلاک این سال قطعی شده است؛ برای صدور دوباره ابتدا آن را به موقت برگردانید.')
        old.delete()
        for voucher in old_vouchers:
            ledger.delete_voucher(actor, voucher)
        debits, credits = {}, {}
        for row in rows:
            asset = row['asset']
            debits[asset.expense_account_id] = debits.get(asset.expense_account_id, 0) + row['amount']
            credits[asset.accumulated_account_id] = credits.get(asset.accumulated_account_id, 0) + row['amount']
        accounts = {a.id: a for a in Account.objects.filter(pk__in=set(debits) | set(credits))}
        lines = ([{'account': accounts[i], 'debit': v, 'credit': 0, 'description': 'هزینه استهلاک'} for i, v in debits.items()]
                 + [{'account': accounts[i], 'debit': 0, 'credit': v, 'description': 'استهلاک انباشته'} for i, v in credits.items()])
        voucher = ledger.create_voucher(actor, year, year.end_date, 'general', f'سند استهلاک دارایی‌های ثابت سال {year.year}', lines)
        AssetDepreciation.objects.bulk_create([AssetDepreciation(asset=r['asset'], fiscal_year=year, amount=r['amount'], voucher=voucher)
                                               for r in rows])
    return voucher


def _year_containing(muni, on):
    year = FiscalYear.objects.filter(municipality=muni, start_date__lte=on, end_date__gte=on).first()
    if year is None:
        raise Invalid('برای تاریخ خروج سال مالی باز نشده است.')
    return year


def dispose(actor, asset, on, proceeds, proceeds_account=None, result_account=None):
    """Take the asset out of service on ``on``: one voucher removes cost and accumulated depreciation, books the proceeds and
    the gain or loss. Depreciation up to the disposal month is included."""
    muni = municipality_of(actor)
    _own(muni, asset)
    proceeds = _amount(proceeds)
    if asset.status != 'active':
        raise Conflict('این دارایی قبلاً خارج شده است.')
    if on < asset.acquisition_date:
        raise Invalid('تاریخ خروج نمی‌تواند پیش از تاریخ تحصیل باشد.')
    year = _year_containing(muni, on)
    if year.is_closed:
        raise Conflict('سال مالی بسته شده است.')
    if proceeds > 0:
        proceeds_account = _account(muni, proceeds_account, 'حساب دریافت وجه', ('asset',))
    asset.disposed_on = on                                                   # so schedule() stops at the disposal month
    plan = schedule(asset)
    posted = {d.fiscal_year.year: d.amount for d in asset.depreciations.select_related('fiscal_year')}
    owed_before = [y for y in plan if y < year.year and posted.get(y) != plan[y]]
    if owed_before:
        asset.disposed_on = None
        raise Conflict('استهلاک سال‌های ' + '، '.join(str(y) for y in sorted(owed_before)) + ' هنوز ثبت نشده است؛ ابتدا آن را صادر کنید.')
    extra = plan.get(year.year, Decimal(0)) - posted.get(year.year, Decimal(0))
    if extra < 0:
        asset.disposed_on = None
        raise Conflict('استهلاک کامل سال خروج قبلاً ثبت شده است؛ سند استهلاک آن سال را حذف و دوباره صادر کنید.')
    total_accumulated = posted_total(asset) + extra
    book = asset.cost - total_accumulated
    difference = proceeds - book
    if difference:
        result_account = _account(muni, result_account, 'حساب سود/زیان فروش', RESULT_KINDS)
    lines = []
    if extra > 0:
        lines += [{'account': asset.expense_account, 'debit': extra, 'credit': 0, 'description': 'استهلاک تا ماه خروج'},
                  {'account': asset.accumulated_account, 'debit': 0, 'credit': extra, 'description': 'استهلاک تا ماه خروج'}]
    if total_accumulated > 0:
        lines.append({'account': asset.accumulated_account, 'debit': total_accumulated, 'credit': 0, 'description': 'حذف استهلاک انباشته'})
    if proceeds > 0:
        lines.append({'account': proceeds_account, 'debit': proceeds, 'credit': 0, 'description': 'دریافت وجه فروش'})
    if difference < 0:
        lines.append({'account': result_account, 'debit': -difference, 'credit': 0, 'description': 'زیان خروج دارایی'})
    lines.append({'account': asset.account, 'debit': 0, 'credit': asset.cost, 'description': 'حذف بهای دارایی'})
    if difference > 0:
        lines.append({'account': result_account, 'debit': 0, 'credit': difference, 'description': 'سود خروج دارایی'})
    try:
        with transaction.atomic():
            voucher = ledger.create_voucher(actor, year, on, 'general', f'خروج دارایی {asset.code} - {asset.title}'[:500], lines)
            if extra > 0:
                AssetDepreciation.objects.create(asset=asset, fiscal_year=year, amount=extra, voucher=voucher)
            asset.status, asset.disposal_amount, asset.disposal_voucher = 'disposed', proceeds, voucher
            asset.save(update_fields=['status', 'disposed_on', 'disposal_amount', 'disposal_voucher'])
    except Exception:
        asset.disposed_on, asset.status = None, 'active'
        raise
    return voucher
