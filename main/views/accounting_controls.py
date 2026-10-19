"""Controls of the accountant workspace: date lock, data integrity check and bank reconciliation.
Rules live in main/accounting/controls and main/accounting/integrity."""
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from main.accounting import controls, integrity, ledger
from main.accounting.parse import jalali_str, parse_amount, parse_jalali
from main.models import Account
from main.office.errors import OfficeError
from main.views.accounting_panel import _date_param, _done, _failed
from main.views.accounting_views import _guard


def tab_controls(request, year, ctx):
    lock = controls.get_lock(request.user)
    results = integrity.run(request.user, year)
    ctx.update(lock=lock, lock_text=jalali_str(lock.lock_date) if lock.lock_date else '', checks=results,
               check_summary=integrity.summary(results),
               can_lock=ledger.role_of(request.user) == 'dehyari' or request.user.is_superuser or ledger.is_admin(request.user))


def tab_recon(request, year, ctx):
    g = request.GET
    accounts = controls.bank_accounts(request.user)
    account = accounts.filter(pk=g.get('account')).first() if g.get('account', '').isdigit() else None
    date_from, err_from = _date_param(request, 'date_from')
    date_to, err_to = _date_param(request, 'date_to')
    ctx.update(bank_accounts=accounts, recon_account=account, recon_error=err_from or err_to)
    statement = None
    if g.get('statement', '').strip():
        try:
            statement = parse_amount(g['statement'])
        except OfficeError as exc:
            ctx['recon_error'] = ctx['recon_error'] or str(exc)
    if account is not None and not ctx['recon_error']:
        ctx['recon'] = controls.reconciliation(request.user, year, account, date_from=date_from, date_to=date_to,
                                               statement_balance=statement)
        ctx['shown_ids'] = ','.join(str(r['line'].id) for r in ctx['recon']['rows'])


@_guard()
@require_POST
def acc_p_lock_set(request):
    text = request.POST.get('lock_date', '').strip()
    try:
        controls.set_lock(request.user, parse_jalali(text) if text else None)
    except OfficeError as exc:
        return _failed(exc)
    return _done('قفل تاریخ ثبت شد.' if text else 'قفل تاریخ برداشته شد.')


@_guard()
@require_POST
def acc_p_recon_save(request, year_id):
    year = ledger.get_year(request.user, year_id)
    account = get_object_or_404(Account, pk=request.POST.get('account') or 0, municipality=ledger.municipality_of(request.user))
    try:
        shown = [int(i) for i in request.POST.get('shown', '').split(',') if i.strip().isdigit()]
        checked = [int(i) for i in request.POST.getlist('line') if i.isdigit()]
        count = controls.save_marks(request.user, year, account, shown, checked)
    except OfficeError as exc:
        return _failed(exc)
    return _done(f'مغایرت‌گیری ذخیره شد؛ {count} ردیف تیک خورده است.')


BUILDERS = {'controls': tab_controls, 'recon': tab_recon}
