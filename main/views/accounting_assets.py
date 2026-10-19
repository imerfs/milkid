"""Fixed assets screens of the accountant workspace. Rules live in main/accounting/assets."""
from datetime import date

from django.shortcuts import render
from django.views.decorators.http import require_POST

from main.accounting import assets, ledger
from main.accounting.parse import digits, jalali_str, parse_amount, parse_jalali, parse_int_or_none
from main.models import Account, Asset
from main.office.errors import OfficeError
from main.views.accounting_panel import PANEL, _done, _failed
from main.views.accounting_views import _find, _guard


def _account_choices(muni):
    postable = Account.objects.filter(municipality=muni, is_postable=True)
    return {'asset_accounts': postable.filter(kind='asset'), 'expense_accounts': postable.filter(kind='budget_use'),
            'result_accounts': postable.filter(kind__in=assets.RESULT_KINDS)}


def tab_assets(request, year, ctx):
    rows = []
    for asset in assets.assets_for(request.user):
        posted = assets.posted_total(asset)
        rows.append({'asset': asset, 'accumulated': posted, 'book': asset.cost - posted})
    preview, missing = assets.preview(request.user, year)
    defaults = assets.default_accounts(ctx['muni'])
    ctx.update(asset_rows=rows, dep_rows=preview, dep_missing=missing, dep_total=sum((r['amount'] for r in preview), 0),
               has_asset_accounts=all(defaults))


def _form(request, muni, posted=None, error=None, status=200):
    default_asset, default_acc, default_exp = assets.default_accounts(muni)
    p = posted or {'acquisition_date': jalali_str(date.today()), 'method': 'line', 'account': default_asset and default_asset.id,
                   'accumulated_account': default_acc and default_acc.id, 'expense_account': default_exp and default_exp.id}
    return render(request, PANEL + 'asset_form.html', {'p': p, 'error': error, 'methods': Asset.METHODS, **_account_choices(muni)},
                  status=status)


@_guard()
def acc_p_asset_new(request):
    muni = ledger.municipality_of(request.user)
    if request.method != 'POST':
        return _form(request, muni)
    p = request.POST
    try:
        asset = assets.create_asset(
            request.user, code=p.get('code', ''), title=p.get('title', ''), acquisition_date=parse_jalali(p.get('acquisition_date', '')),
            cost=parse_amount(p.get('cost')), salvage=parse_amount(p.get('salvage')), life_years=parse_int_or_none(p.get('life_years')),
            method=p.get('method', ''), account=_find(Account, muni, p.get('account')),
            accumulated_account=_find(Account, muni, p.get('accumulated_account')),
            expense_account=_find(Account, muni, p.get('expense_account')), description=p.get('description', ''))
    except OfficeError as exc:
        return _form(request, muni, p, str(exc), exc.status)
    return _done(f'دارایی «{asset.title}» ثبت شد.')


@_guard()
@require_POST
def acc_p_asset_accounts(request):
    assets.ensure_accounts(request.user)
    return _done('سرفصل‌های دارایی ثابت ساخته شد.')


@_guard()
@require_POST
def acc_p_asset_delete(request, asset_id):
    try:
        assets.delete_asset(request.user, assets.get_asset(request.user, asset_id))
    except OfficeError as exc:
        return _failed(exc)
    return _done('دارایی حذف شد.')


@_guard()
@require_POST
def acc_p_asset_depreciate(request, year_id):
    year = ledger.get_year(request.user, year_id)
    try:
        voucher = assets.post_year(request.user, year)
    except OfficeError as exc:
        return _failed(exc)
    return _done(f'سند استهلاک سال {year.year} (شماره {voucher.number}) به‌صورت موقت صادر شد.')


def _dispose_modal(request, asset, posted=None, error=None, status=200):
    muni = ledger.municipality_of(request.user)
    return render(request, PANEL + 'asset_dispose.html', {
        'asset': asset, 'p': posted or {'date': jalali_str(date.today()), 'proceeds': '0'},
        'book': assets.book_value(asset), 'error': error, **_account_choices(muni)}, status=status)


@_guard()
def acc_p_asset_dispose(request, asset_id):
    muni = ledger.municipality_of(request.user)
    asset = assets.get_asset(request.user, asset_id)
    if request.method != 'POST':
        return _dispose_modal(request, asset)
    p = request.POST
    try:
        on = parse_jalali(p.get('date', ''))
        proceeds_account = _find(Account, muni, p.get('proceeds_account')) if digits(p.get('proceeds_account')) else None
        result_account = _find(Account, muni, p.get('result_account')) if digits(p.get('result_account')) else None
        voucher = assets.dispose(request.user, asset, on, parse_amount(p.get('proceeds')), proceeds_account, result_account)
    except OfficeError as exc:
        return _dispose_modal(request, asset, p, str(exc), exc.status)
    return _done(f'دارایی خارج شد؛ سند شماره {voucher.number} به‌صورت موقت صادر شد.')


BUILDERS = {'assets': tab_assets}
