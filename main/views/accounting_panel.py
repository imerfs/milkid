"""Single-page accounting workspace for the accountant dashboard (HTMX partials + modal forms).

Presentation only: every rule, permission and tenant check stays in main/accounting; these views call the same
services as the classic pages in accounting_views and answer with fragments the dashboard swaps in place.
"""
import json
from datetime import date

from django.core.paginator import Paginator
from django.db.models import F, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from main.accounting import bills, budget, ledger
from main.accounting.parse import jalali_str, parse_amount, parse_jalali
from main.models import Account, BillPayment, FiscalYear, Party, Voucher
from main.office.errors import Invalid, OfficeError
from main.views.accounting_views import (
    PAGE_SIZE, _bill_form_data, _filtered, _find, _form_context, _guard, _row_dicts, _service_lines)

TABS = ('vouchers', 'bills', 'budget')
PANEL = 'main/accounting/panel/'


def _trigger(response, **events):
    response['HX-Trigger'] = json.dumps(events)  # ASCII-escaped: header values cannot carry raw Persian
    return response


def _done(message):
    """Success of a modal or row action: nothing to swap, the page closes the dialog and reloads the panel."""
    return _trigger(HttpResponse(status=204), accDone={'message': message})


def _failed(exc):
    """Failure of a row action (no form to show it in): toast only."""
    return _trigger(HttpResponse(status=exc.status), accError={'message': str(exc)})


def years_for(user):
    return FiscalYear.objects.filter(municipality=ledger.municipality_of(user)).order_by('-year')


def _today_in(year):
    today = date.today()
    return jalali_str(today) if year.start_date <= today <= year.end_date else ''


def _open_bills(qs):
    return qs.filter(canceled_at__isnull=True).filter(Q(paid__isnull=True) | Q(paid__lt=F('amount')))


def _summary(user, year):
    _, totals = budget.report(user, year)
    open_bills = list(_open_bills(bills.bills_for(user, year)).values_list('amount', 'paid'))
    vouchers = ledger.vouchers_for(user, year)
    temporary = vouchers.filter(status='temporary')
    unbalanced = sum(1 for v in temporary.annotate(d=Sum('lines__debit'), c=Sum('lines__credit')) if v.d != v.c)

    def pct(part, whole):
        return min(round(part * 100 / whole), 100) if whole else 0

    return {
        'use': totals['use'], 'resource': totals['resource'],
        'use_pct': pct(totals['use']['actual'], totals['use']['budget']),
        'resource_pct': pct(totals['resource']['actual'], totals['resource']['budget']),
        'temporary_count': temporary.count(), 'unbalanced_count': unbalanced,
        'final_count': vouchers.filter(status='final').count(),
        'open_bill_count': len(open_bills), 'open_bill_remaining': sum(a - (p or 0) for a, p in open_bills)}


def _bills_filtered(request, qs):
    g = request.GET
    state = g.get('bill_status')
    if state == 'open':
        qs = _open_bills(qs)
    elif state == 'paid':
        qs = qs.filter(canceled_at__isnull=True, paid__gte=F('amount'))
    elif state == 'canceled':
        qs = qs.filter(canceled_at__isnull=False)
    if g.get('q', '').strip():
        q = g['q'].strip()
        qs = qs.filter(Q(description__icontains=q) | Q(party__name__icontains=q))
    return qs


def render_panel(request, year, status=200):
    user, g = request.user, request.GET
    tab = g.get('tab') if g.get('tab') in TABS else 'vouchers'
    ctx = {'year': year, 'years': years_for(user), 'tab': tab, 'g': g, 'kinds': Voucher.KINDS,
           'summary': _summary(user, year)}
    keep = g.copy()
    keep.pop('page', None)
    keep['year'], keep['tab'] = year.id, tab
    ctx['filtered'] = any(g.get(k) for k in ('q', 'status', 'kind', 'bill_status'))
    ctx['query'] = keep.urlencode()
    if tab == 'vouchers':
        qs = _filtered(request, ledger.vouchers_for(user, year)).annotate(
            total=Sum('lines__debit'), credit_total=Sum('lines__credit')).order_by('-number')
        ctx['page'] = Paginator(qs, PAGE_SIZE).get_page(g.get('page'))
    elif tab == 'bills':
        qs = _bills_filtered(request, bills.bills_for(user, year))
        page = Paginator(qs, PAGE_SIZE).get_page(g.get('page'))
        page.object_list = list(page.object_list)
        for b in page.object_list:
            b.paid = b.paid or 0
            b.state = 'canceled' if b.canceled_at else 'paid' if b.paid >= b.amount else 'partial' if b.paid else 'unpaid'
        ctx['page'] = page
    else:
        ctx['rows'], ctx['totals'] = budget.report(user, year, include_temporary=g.get('final') != '1')
        ctx['final_only'] = g.get('final') == '1'
    return render(request, PANEL + 'panel.html', ctx, status=status)


@_guard()
def acc_panel(request):
    """The workspace itself: summary cards, tabbed tables and filters for one fiscal year."""
    muni = ledger.municipality_of(request.user)
    years = years_for(request.user)
    wanted = request.GET.get('year', '')
    year = years.filter(pk=wanted).first() if wanted.isdigit() else years.first()
    if year is None:
        return render(request, PANEL + 'empty.html', {
            'has_accounts': Account.objects.filter(municipality=muni).exists(), 'bad_year': bool(wanted)})
    return render_panel(request, year)


# ---------- vouchers ----------

def _voucher_modal(request, year, voucher=None, rows=None, error=None, status=200, posted=None):
    muni = ledger.municipality_of(request.user)
    ctx = _form_context(request, muni, year, voucher, rows, error)
    if posted is not None:
        ctx.update(date=posted.get('date', ''), kind=posted.get('kind', ''), description=posted.get('description', ''))
    elif voucher:
        ctx.update(date=jalali_str(voucher.date), kind=voucher.kind, description=voucher.description,
                   rows=[{'account': l.account_id, 'party': l.party_id or '', 'cost_center': l.cost_center_id or '',
                          'line_description': l.description, 'debit': l.debit or '', 'credit': l.credit or ''}
                         for l in voucher.lines.all()])
    else:
        ctx.update(date=_today_in(year), kind='general', description='')
    return render(request, PANEL + 'voucher_form.html', ctx, status=status)


def _voucher_save(request, year, voucher=None):
    if request.method != 'POST':
        return _voucher_modal(request, year, voucher)
    muni = ledger.municipality_of(request.user)
    rows = _row_dicts(request.POST)
    try:
        on, kind = parse_jalali(request.POST.get('date', '')), request.POST.get('kind', '')
        description, lines = request.POST.get('description', ''), _service_lines(muni, rows)
        if voucher is None:
            saved = ledger.create_voucher(request.user, year, on, kind, description, lines)
        else:
            saved = ledger.update_voucher(request.user, voucher, description=description, lines=lines, on=on, kind=kind)
    except OfficeError as exc:
        return _voucher_modal(request, year, voucher, rows, str(exc), exc.status, request.POST)
    return _done(f'سند شماره {saved.number} ذخیره شد.')


@_guard()
def acc_p_voucher_new(request, year_id):
    year = ledger.get_year(request.user, year_id)
    if year.is_closed:
        return _voucher_modal(request, year, error='سال مالی بسته شده است.', status=409)
    return _voucher_save(request, year)


@_guard()
def acc_p_voucher_edit(request, voucher_id):
    voucher = ledger.get_voucher(request.user, voucher_id)
    try:
        ledger.check_editable(request.user, voucher)
    except OfficeError as exc:
        return _voucher_detail(request, voucher, str(exc), exc.status)
    return _voucher_save(request, voucher.fiscal_year, voucher)


def _voucher_detail(request, voucher, error=None, status=200):
    totals = voucher.lines.aggregate(d=Sum('debit'), c=Sum('credit'))
    return render(request, PANEL + 'voucher_detail.html', {
        'voucher': voucher, 'year': voucher.fiscal_year, 'error': error,
        'lines': voucher.lines.select_related('account', 'party', 'cost_center'),
        'debit': totals['d'] or 0, 'credit': totals['c'] or 0, 'balanced': ledger.is_balanced(voucher)}, status=status)


@_guard()
def acc_p_voucher_detail(request, voucher_id):
    return _voucher_detail(request, ledger.get_voucher(request.user, voucher_id))


VOUCHER_ACTIONS = {
    'finalize': (ledger.finalize, 'سند قطعی شد.'),
    'revert': (ledger.revert_to_temporary, 'سند به حالت موقت برگشت.'),
    'delete': (ledger.delete_voucher, 'سند حذف شد.'),
}


@_guard()
@require_POST
def acc_p_voucher_action(request, voucher_id, action):
    if action not in VOUCHER_ACTIONS:
        return HttpResponse(status=404)
    run, done = VOUCHER_ACTIONS[action]
    voucher = ledger.get_voucher(request.user, voucher_id)
    try:
        run(request.user, voucher)
    except OfficeError as exc:
        return _failed(exc)
    return _done(done)


# ---------- bills ----------

def _bill_issue_modal(request, year, error=None, status=200, posted=None):
    muni = ledger.municipality_of(request.user)
    return render(request, PANEL + 'bill_form.html', {
        'year': year, 'error': error, 'p': posted or {'date': _today_in(year)}, **_bill_form_data(muni)}, status=status)


@_guard()
def acc_p_bill_new(request, year_id):
    year = ledger.get_year(request.user, year_id)
    if request.method != 'POST':
        return _bill_issue_modal(request, year)
    muni, p = ledger.municipality_of(request.user), request.POST
    try:
        bill = bills.issue_bill(request.user, year, parse_jalali(p.get('date', '')), _find(Party, muni, p.get('party')),
                                _find(Account, muni, p.get('income_account')), parse_amount(p.get('amount')),
                                p.get('description', ''))
    except OfficeError as exc:
        return _bill_issue_modal(request, year, str(exc), exc.status, p)
    return _done(f'فیش شماره {bill.number} صادر شد.')


def _bill_modal(request, bill, error=None, status=200, posted=None):
    muni, s = ledger.municipality_of(request.user), bills.summary(bill)
    return render(request, PANEL + 'bill_detail.html', {
        'bill': bill, 'year': bill.fiscal_year, 's': s, 'error': error, 'methods': BillPayment.METHODS,
        'payments': bill.payments.select_related('voucher', 'bank_account'),
        'p': posted or {'date': _today_in(bill.fiscal_year), 'amount': int(s['remaining'])},
        **_bill_form_data(muni)}, status=status)


@_guard()
def acc_p_bill_detail(request, bill_id):
    return _bill_modal(request, bills.get_bill(request.user, bill_id))


@_guard()
@require_POST
def acc_p_bill_pay(request, bill_id):
    bill = bills.get_bill(request.user, bill_id)
    muni, p = ledger.municipality_of(request.user), request.POST
    try:
        bills.record_payment(request.user, bill, parse_jalali(p.get('date', '')), parse_amount(p.get('amount')),
                             _find(Account, muni, p.get('bank_account')), p.get('method', ''), p.get('reference', ''))
    except OfficeError as exc:
        return _bill_modal(request, bill, str(exc), exc.status, p)
    return _done('پرداخت ثبت شد و سند درآمد (موقت) صادر شد.')


@_guard()
@require_POST
def acc_p_bill_cancel(request, bill_id):
    bill = bills.get_bill(request.user, bill_id)
    try:
        bills.cancel_bill(request.user, bill)
    except OfficeError as exc:
        return _failed(exc)
    return _done('فیش ابطال شد.')


@_guard()
@require_POST
def acc_p_payment_cancel(request, payment_id):
    muni = ledger.municipality_of(request.user)
    payment = get_object_or_404(BillPayment, pk=payment_id, bill__municipality=muni)
    try:
        bills.cancel_payment(request.user, payment)
    except OfficeError as exc:
        return _failed(exc)
    return _done('پرداخت ابطال شد و سند آن حذف شد.')


# ---------- budget ----------

def _budget_modal(request, year, error=None, status=200, posted=None):
    muni = ledger.municipality_of(request.user)
    return render(request, PANEL + 'budget_form.html', {
        'year': year, 'error': error, 'p': posted or request.GET,
        'choices': Account.objects.filter(municipality=muni, kind__in=budget.BUDGET_KINDS, is_postable=True)},
        status=status)


@_guard()
def acc_p_budget(request, year_id):
    year = ledger.get_year(request.user, year_id)
    if request.method != 'POST':
        return _budget_modal(request, year)
    muni, p = ledger.municipality_of(request.user), request.POST
    try:
        account = _find(Account, muni, p.get('account'))
        if account is None:
            raise Invalid('حساب را انتخاب کنید.')
        budget.set_budget(request.user, year, account, parse_amount(p.get('amount')))
    except OfficeError as exc:
        return _budget_modal(request, year, str(exc), exc.status, p)
    return _done('بودجه ذخیره شد.')
