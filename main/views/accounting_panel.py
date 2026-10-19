"""Single-page accounting workspace for the accountant dashboard (HTMX partials + modal forms).

Presentation only: every rule, permission and tenant check stays in main/accounting; these views call the same
services as the classic pages in accounting_views and answer with fragments the dashboard swaps in place.
"""
import json
from datetime import date

import jdatetime
from django.core.paginator import Paginator
from django.db.models import Count, F, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from main.accounting import access_levels, bills, budget, chart, ledger, statements
from main.accounting.parse import jalali_str, parse_amount, parse_jalali
from main.models import Account, BillPayment, FiscalYear, Party, Payment, Voucher
from main.office.errors import Invalid, OfficeError
from main.views.accounting_views import (
    PAGE_SIZE, _bill_form_data, _filtered, _find, _form_context, _guard, _row_dicts, _service_lines, new_account,
    new_party)

YEAR_TABS = ('overview', 'vouchers', 'bills', 'budget', 'trial', 'statements', 'yearend', 'recon', 'controls', 'access', 'audit', 'credit', 'contracts', 'payables', 'images',
             'statuschange', 'plans', 'received', 'transport', 'planimages', 'reports')
PAYROLL_TABS = ('pstaff', 'pcalc', 'pattendance', 'pmission', 'pspecialallow', 'pspecialdebt', 'pmisc', 'pworkers', 'peidi', 'prun',
                'psettings')
TABS = YEAR_TABS + ('guarantees', 'parties', 'accounts', 'online', 'setup', 'settings') + PAYROLL_TABS
# Tabs drawn by the generic register template (see main/views/accounting_finance.py)
REGISTER_TABS = ('credit', 'contracts', 'guarantees', 'payables', 'images', 'plans', 'received', 'transport', 'planimages') + PAYROLL_TABS
PANEL = 'main/accounting/panel/'
# (key, label, icon, needs a fiscal year, page subtitle) in menu order
TAB_LIST = [('overview', 'نمای کلی', 'gauge-high', True, 'وضعیت مالی سال جاری و کارهای باز، یک‌جا.'),
            ('vouchers', 'اسناد حسابداری', 'file-invoice', True, 'ثبت، ویرایش و قطعی‌کردن اسناد.'),
            ('bills', 'فیش‌های نقدی', 'receipt', True, 'صدور فیش و ثبت پرداخت‌ها.'),
            ('budget', 'بودجه و عملکرد', 'chart-pie', True, 'بودجه مصوب در برابر عملکرد هر حساب.'),
            ('trial', 'تراز آزمایشی', 'scale-balanced', True, 'جمع بدهکار و بستانکار همه حساب‌ها.'),
            ('statements', 'صورت‌های مالی', 'file-invoice-dollar', True, 'صورت منابع و مصارف و ترازنامه تا تاریخ دلخواه.'),
            ('yearend', 'عملیات سال مالی', 'flag-checkered', True, 'سند بستن حساب‌های موقت، اختتامیه، افتتاحیه و بستن سال.'),
            ('recon', 'مغایرت‌گیری بانک', 'building-columns', True, 'تیک‌زدن گردش بانک و صندوق و مقایسه با صورت‌حساب بانک.'),
            ('controls', 'قفل تاریخ و کنترل داده', 'shield-heart', True, 'قفل اسناد تا یک تاریخ و بررسی سلامت دفتر.'),
            ('audit', 'لاگ ممیزی', 'clock-rotate-left', True, 'چه کسی چه چیزی را کی تغییر داده؛ ورود و خروج کاربران.'),
            ('access', 'سطوح دسترسی حسابدار', 'user-lock', True, 'تعیین کنید حسابدار هر بخش را ببیند یا ویرایش کند.'),
            ('credit', 'تامین اعتبار', 'hand-holding-dollar', True, 'رزرو اعتبار بودجه برای حساب‌های مصرف، بدون عبور از بودجه مصوب.'),
            ('contracts', 'قراردادها', 'file-signature', True, 'قراردادها، صورت‌وضعیت‌ها و کسورات پیمانکار.'),
            ('guarantees', 'ضمانت‌نامه‌ها', 'shield-halved', False, 'ضمانت‌نامه‌ها، چک و سفته‌های دریافتی و سررسید آن‌ها.'),
            ('payables', 'خزانه اسناد پرداختی', 'money-check-dollar', True, 'چک‌ها و سفته‌های صادرشده تا زمان پاس‌شدن.'),
            ('images', 'تصاویر اسناد', 'images', True, 'اسکن و تصویر مدارک پشتوانه اسناد.'),
            ('statuschange', 'تغییر وضعیت اسناد', 'check-double', True, 'قطعی یا موقت‌کردن گروهی اسناد بر اساس بازه شماره.'),
            ('plans', 'تقسیط', 'calendar-check', True, 'پرونده‌های تقسیط بدهی، اقساط و پرداخت‌ها.'),
            ('received', 'خزانه اسناد دریافتی', 'money-check', True, 'چک و سفته‌های دریافتی: ارسال به خزانه، وصول یا برگشت.'),
            ('transport', 'درآمد حمل و نقل', 'truck', True, 'عوارض و بهای خدمات حمل و نقل.'),
            ('planimages', 'تصاویر پرونده تقسیط', 'images', True, 'مدارک و نامه‌های پرونده‌های تقسیط.'),
            ('reports', 'گزارش‌گیری', 'file-lines', True, 'گزارش اسناد، دفاتر، فیش‌ها، تقسیط، ضمانت‌نامه‌ها و ... با خروجی اکسل.'),
            ('pstaff', 'اطلاعات پرسنل', 'users', False, 'پرسنل، مزایای ماهانه و بدهی‌های هر نفر.'),
            ('pattendance', 'کارکرد ماهانه', 'clock', False, 'کارکرد، غیبت، اضافه کار و شب کاری هر ماه.'),
            ('pmission', 'ماموریت', 'plane', False, 'ماموریت‌های پرسنل و هزینه‌های آن‌ها.'),
            ('pspecialallow', 'مزایای مخصوص', 'gift', False, 'مزایایی که به همه پرسنل یک گروه محاسباتی داده می‌شود.'),
            ('pspecialdebt', 'بدهی مخصوص', 'file-invoice-dollar', False, 'کسوراتی که از همه پرسنل یک گروه محاسباتی کم می‌شود.'),
            ('pmisc', 'پرداخت‌های متفرقه', 'wallet', False, 'واریزی‌های غیرحقوقی و علی‌الحساب هر ماه.'),
            ('pworkers', 'کارگران روزمزد', 'helmet-safe', False, 'کارگران روزمزد و کارکرد ماهانه آن‌ها.'),
            ('peidi', 'اطلاعات عیدی', 'gift', False, 'تنظیم و محاسبه عیدی سالانه پرسنل.'),
            ('pcalc', 'نحوه محاسبات فردی', 'sliders', False, 'نرخ‌ها و مبالغ اختصاصی هر فرد که جایگزین تنظیمات عمومی می‌شود.'),
            ('prun', 'محاسبه و فیش حقوق', 'money-bill-wave', False, 'محاسبه ماهانه حقوق، فیش هر فرد، قطعی‌کردن و خروجی اکسل.'),
            ('psettings', 'تنظیمات حقوق', 'gear', False, 'نرخ بیمه، ضریب اضافه کار و سایر پارامترهای محاسبه.'),
            ('settings', 'تنظیمات مالی', 'sliders', False, 'مراکز هزینه، شرح‌های استاندارد و امضاکنندگان.'),
            ('parties', 'طرف‌حساب‌ها', 'address-book', False, 'اشخاص و سازمان‌هایی که با دهیاری حساب دارند.'),
            ('accounts', 'سرفصل حساب‌ها', 'sitemap', False, 'درخت حساب‌های دهیاری.'),
            ('online', 'پرداخت‌های آنلاین', 'credit-card', False, 'پرداخت‌های شهروندان: تایید، رد و سابقه.'),
            ('setup', 'سال مالی و شروع کار', 'calendar-days', False, 'باز کردن سال مالی و ساخت سرفصل‌های پیش‌فرض.')]


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


def _paged(request, qs):
    return Paginator(qs, PAGE_SIZE).get_page(request.GET.get('page'))


def _tab_overview(request, year, ctx):
    """Landing page: where the year stands (budget vs actual), the latest vouchers, open bills, what needs attention."""
    summary = ctx['summary']
    rows, _ = budget.report(request.user, year)
    ctx['top_rows'] = sorted((r for r in rows if r['percent'] is not None), key=lambda r: -r['percent'])[:5]
    ctx['over_count'] = sum(1 for r in rows if r['over'])
    ctx['recent_vouchers'] = ledger.vouchers_for(request.user, year).annotate(
        total=Sum('lines__debit'), credit_total=Sum('lines__credit')).order_by('-number')[:5]
    ctx['open_bills'] = _open_bills(bills.bills_for(request.user, year)).select_related('party').order_by('-date')[:5]
    for b in ctx['open_bills']:
        b.left = b.amount - (b.paid or 0)
    circ = 2 * 3.14159 * 54  # donut circumference for r=54, matches the SVG in _overview.html
    ctx['donut_use'] = round(summary['use_pct'] * circ / 100, 1)
    ctx['donut_res'] = round(summary['resource_pct'] * circ / 100, 1)
    ctx['donut_len'] = round(circ, 1)
    ctx['attention'] = bool(summary['unbalanced_count'] or ctx['over_count'] or summary['temporary_count'])


def _tab_vouchers(request, year, ctx):
    qs = _filtered(request, ledger.vouchers_for(request.user, year)).annotate(
        total=Sum('lines__debit'), credit_total=Sum('lines__credit')).order_by('-number')
    ctx['page'] = _paged(request, qs)


def _tab_bills(request, year, ctx):
    page = _paged(request, _bills_filtered(request, bills.bills_for(request.user, year)))
    page.object_list = list(page.object_list)
    for b in page.object_list:
        b.paid = b.paid or 0
        b.state = 'canceled' if b.canceled_at else 'paid' if b.paid >= b.amount else 'partial' if b.paid else 'unpaid'
    ctx['page'] = page


def _tab_budget(request, year, ctx):
    ctx['final_only'] = request.GET.get('final') == '1'
    ctx['rows'], ctx['totals'] = budget.report(request.user, year, include_temporary=not ctx['final_only'])


def _date_param(request, name):
    """(date or None, error) from a Jalali ?name= parameter."""
    text = request.GET.get(name, '').strip()
    if not text:
        return None, None
    try:
        return parse_jalali(text), None
    except OfficeError as exc:
        return None, str(exc)


def _tab_trial(request, year, ctx):
    """Trial balance with opening / turnover / ending columns, rolled up to a level of the chart."""
    g = request.GET
    level = g.get('level') if g.get('level') in statements.LEVELS else 'all'
    date_from, err_from = _date_param(request, 'date_from')
    date_to, err_to = _date_param(request, 'date_to')
    ctx.update(final_only=g.get('final') == '1', level=level, levels=statements.LEVELS, with_closing=g.get('closing') == '1',
               trial_error=err_from or err_to)
    if ctx['trial_error']:
        ctx['rows'], ctx['totals'] = [], {key: 0 for key in ('debit', 'credit', 'open_d', 'open_c', 'turn_d', 'turn_c', 'end_d', 'end_c')}
        return
    ctx['rows'], ctx['totals'] = statements.trial_by_level(
        request.user, year, level=level, date_from=date_from, date_to=date_to, final_only=ctx['final_only'],
        with_closing=ctx['with_closing'])


def _tab_parties(request, year, ctx):
    q = request.GET.get('q', '').strip()
    qs = Party.objects.filter(municipality=ctx['muni'])
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(national_id__icontains=q))
    ctx['page'] = _paged(request, qs)


def _tab_accounts(request, year, ctx):
    q = request.GET.get('q', '').strip()
    qs = Account.objects.filter(municipality=ctx['muni'])
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(code__startswith=q))
    ctx['page'] = _paged(request, qs)


def _tab_online(request, year, ctx):
    """Citizens' online payments: the pending ones to approve, then the history. Same rules as the old dashboard."""
    g = request.GET
    qs = Payment.objects.select_related('user')
    ctx['pending'] = qs.filter(status='pending').order_by('-created_at')[:10]
    ctx['pending_count'] = qs.filter(status='pending').count()
    if g.get('pay_status') in ('pending', 'completed', 'rejected'):
        qs = qs.filter(status=g['pay_status'])
    if g.get('q', '').strip():
        q = g['q'].strip()
        qs = qs.filter(Q(description__icontains=q) | Q(receipt_number__icontains=q) | Q(user__first_name__icontains=q)
                       | Q(user__last_name__icontains=q) | Q(user__username__icontains=q))
    ctx['page'] = _paged(request, qs.order_by('-created_at'))
    ctx['income_types'] = ('property_tax', 'permit_fee')


def _tab_setup(request, year, ctx):
    ctx['has_accounts'] = Account.objects.filter(municipality=ctx['muni']).exists()
    ctx['years_counted'] = ctx['years'].annotate(
        count=Count('vouchers', filter=Q(vouchers__deleted_at__isnull=True)))
    ctx['this_year'] = jdatetime.date.today().year


TAB_BUILDERS = {'overview': _tab_overview, 'vouchers': _tab_vouchers, 'bills': _tab_bills, 'budget': _tab_budget, 'trial': _tab_trial,
                'parties': _tab_parties, 'accounts': _tab_accounts, 'online': _tab_online, 'setup': _tab_setup}


def render_panel(request, year, status=200):
    """Tab bar plus one tab; `year` is None until a fiscal year exists (only the year-free tabs then work)."""
    user, g = request.user, request.GET
    tab = g.get('tab') if g.get('tab') in TABS else 'overview'
    if year is None and tab in YEAR_TABS:
        tab = 'setup'
    denied = access_levels.tab_level(user, tab) == 'none'
    ctx = {'year': year, 'years': years_for(user), 'tab': tab, 'g': g, 'kinds': Voucher.KINDS,
           'muni': ledger.municipality_of(user), 'tab_list': TAB_LIST,
           'tab_meta': next(t for t in TAB_LIST if t[0] == tab), 'tab_template': (f'{PANEL}_denied.html' if denied else f'{PANEL}_register.html' if tab in REGISTER_TABS else f'{PANEL}_{tab}.html'),
           'hidden_tabs': ','.join(access_levels.hidden_tabs(user)), 'read_only': access_levels.tab_level(user, tab) == 'view',
           'filtered': any(g.get(k) for k in ('q', 'status', 'kind', 'bill_status', 'pay_status'))}
    keep = g.copy()
    keep.pop('page', None)
    keep['tab'] = tab
    if year is not None:
        keep['year'] = year.id
        ctx['summary'] = _summary(user, year)
    ctx['query'] = keep.urlencode()
    if denied:
        pass
    elif tab in TAB_BUILDERS:
        TAB_BUILDERS[tab](request, year, ctx)
    else:
        from main.views import (accounting_finance, accounting_income, accounting_payroll, accounting_reports, accounting_settings,
                                accounting_statements, accounting_controls, accounting_audit)   # late: they import this module
        {**accounting_finance.BUILDERS, **accounting_income.BUILDERS, **accounting_reports.BUILDERS,
         **accounting_settings.BUILDERS, **accounting_payroll.BUILDERS, **accounting_statements.BUILDERS,
         **accounting_controls.BUILDERS, **accounting_audit.BUILDERS}[tab](request, year, ctx)
    return render(request, PANEL + 'panel.html', ctx, status=status)


@_guard()
def acc_panel(request):
    """The workspace itself: summary cards, tabs and filters for one fiscal year (the latest unless ?year=)."""
    years = years_for(request.user)
    wanted = request.GET.get('year', '')
    year = years.filter(pk=wanted).first() if wanted.isdigit() else years.first()
    return render_panel(request, year)


# ---------- setup: fiscal years and the default chart of accounts ----------

@_guard()
@require_POST
def acc_p_seed(request):
    return _done(f'سرفصل حساب‌های پیش‌فرض ({chart.seed_default_accounts(request.user)} حساب) ثبت شد.')


@_guard()
@require_POST
def acc_p_year_open(request):
    try:
        year = ledger.open_year(request.user, request.POST.get('year', '').translate(
            str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')))
    except OfficeError as exc:
        return _failed(exc)
    return _done(f'سال مالی {year.year} باز شد.')


# ---------- parties and chart of accounts ----------

@_guard()
def acc_p_party_new(request):
    muni = ledger.municipality_of(request.user)
    if request.method == 'POST':
        try:
            new_party(muni, request.POST)
        except OfficeError as exc:
            return render(request, PANEL + 'party_form.html', {'error': str(exc), 'p': request.POST}, status=exc.status)
        return _done('طرف حساب افزوده شد.')
    return render(request, PANEL + 'party_form.html', {'p': {}})


@_guard()
def acc_p_account_new(request):
    muni = ledger.municipality_of(request.user)
    ctx = {'accounts': Account.objects.filter(municipality=muni, is_postable=False), 'kinds': Account.KINDS,
           'natures': Account.NATURES, 'p': request.POST if request.method == 'POST' else {'is_postable': 'on'}}
    if request.method == 'POST':
        try:
            new_account(muni, request.POST)
        except OfficeError as exc:
            return render(request, PANEL + 'account_form.html', {**ctx, 'error': str(exc)}, status=exc.status)
        return _done('حساب افزوده شد.')
    return render(request, PANEL + 'account_form.html', ctx)


@_guard()
def acc_p_ledger(request, year_id, account_id):
    year = ledger.get_year(request.user, year_id)
    account = get_object_or_404(Account, pk=account_id, municipality=ledger.municipality_of(request.user))
    final_only = request.GET.get('final') == '1'
    date_from, err_from = _date_param(request, 'date_from')
    date_to, err_to = _date_param(request, 'date_to')
    return render(request, PANEL + 'ledger.html', {
        'year': year, 'account': account, 'error': err_from or err_to,
        'rows': ledger.account_ledger(request.user, year, account, include_temporary=not final_only,
                                      date_from=date_from, date_to=date_to)})


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
