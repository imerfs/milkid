"""Accounting pages (vouchers, chart of accounts, parties, trial balance, ledger). Rules live in main/accounting."""
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from openpyxl import Workbook

from main.access import policy_required
from main.accounting import bills, budget, chart, ledger
from main.accounting.parse import jalali_str, parse_amount, parse_int_or_none, parse_jalali
from main.models import Account, BillPayment, CostCenter, FiscalYear, Party, Voucher
from main.office.errors import Conflict, Invalid, NotFound, OfficeError

PAGE_SIZE = 25


def _404_on_not_found(view):
    """Rules raise NotFound for foreign or missing rows; the site answers its 404 page."""
    def wrapped(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except NotFound:
            raise Http404()
    wrapped.__name__ = view.__name__
    wrapped.__doc__ = view.__doc__
    return wrapped


def _guard(action='staff.accountant'):
    def decorator(view):
        return policy_required(action)(_404_on_not_found(view))
    return decorator


def _fail(request, exc):
    messages.error(request, str(exc))


# ---------- years ----------

@_guard()
def acc_home(request):
    muni = ledger.municipality_of(request.user)
    error, status = None, 200
    if request.method == 'POST':
        try:
            year = ledger.open_year(request.user, request.POST.get('year', '').translate(
                str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')))
            messages.success(request, 'سال مالی باز شد.')
            return redirect('main:acc_vouchers', year_id=year.id)
        except OfficeError as exc:
            error, status = str(exc), exc.status
    years = (FiscalYear.objects.filter(municipality=muni).annotate(
        count=Count('vouchers', filter=Q(vouchers__deleted_at__isnull=True))).order_by('-year'))
    return render(request, 'main/accounting/home.html', {
        'muni': muni, 'years': years, 'error': error,
        'has_accounts': Account.objects.filter(municipality=muni).exists()}, status=status)


@_guard()
@require_POST
def acc_seed(request):
    count = chart.seed_default_accounts(request.user)
    messages.success(request, f'سرفصل حساب‌های پیش‌فرض ({count} حساب) ثبت شد.')
    return redirect('main:acc_accounts')


# ---------- vouchers ----------

def _filtered(request, qs):
    g = request.GET
    if g.get('q', '').strip():
        qs = qs.filter(description__icontains=g['q'].strip())
    if g.get('status') in ('temporary', 'final'):
        qs = qs.filter(status=g['status'])
    if g.get('kind') in dict(Voucher.KINDS):
        qs = qs.filter(kind=g['kind'])
    lo, hi = parse_int_or_none(g.get('number_from')), parse_int_or_none(g.get('number_to'))
    if lo is not None:
        qs = qs.filter(number__gte=lo)
    if hi is not None:
        qs = qs.filter(number__lte=hi)
    for key, lookup in (('date_from', 'date__gte'), ('date_to', 'date__lte')):
        try:
            qs = qs.filter(**{lookup: parse_jalali(g.get(key, ''))})
        except Invalid:
            pass
    return qs


@_guard()
def acc_vouchers(request, year_id):
    year = ledger.get_year(request.user, year_id)
    qs = _filtered(request, ledger.vouchers_for(request.user, year)).annotate(
        total=Sum('lines__debit'), credit_total=Sum('lines__credit')).order_by('number')
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get('page'))
    query = request.GET.copy()
    query.pop('page', None)
    return render(request, 'main/accounting/voucher_list.html', {
        'year': year, 'page': page, 'kinds': Voucher.KINDS, 'g': request.GET, 'query': query.urlencode()})


def _row_dicts(post):
    keys = ('account', 'party', 'cost_center', 'line_description', 'debit', 'credit')
    cols = {k: post.getlist(k) for k in keys}
    return [{k: cols[k][i] if i < len(cols[k]) else '' for k in keys} for i in range(len(cols['account']))]


def _service_lines(muni, rows):
    def find(model, raw):
        pk = parse_int_or_none(raw)
        return model.objects.filter(municipality=muni, pk=pk).first() if pk else None

    lines = []
    for r in rows:
        if not any(str(r[k]).strip() for k in r):
            continue
        lines.append({'account': find(Account, r['account']), 'party': find(Party, r['party']),
                      'cost_center': find(CostCenter, r['cost_center']), 'description': r['line_description'],
                      'debit': parse_amount(r['debit']), 'credit': parse_amount(r['credit'])})
    return lines


def _form_context(request, muni, year, voucher, rows, error):
    return {
        'year': year, 'voucher': voucher, 'rows': rows or [{}, {}], 'error': error, 'kinds': Voucher.KINDS,
        'accounts': Account.objects.filter(municipality=muni, is_postable=True),
        'parties': Party.objects.filter(municipality=muni),
        'cost_centers': CostCenter.objects.filter(municipality=muni)}


def _voucher_form(request, year, voucher=None):
    muni = ledger.municipality_of(request.user)
    if request.method == 'POST':
        rows = _row_dicts(request.POST)
        try:
            on, kind = parse_jalali(request.POST.get('date', '')), request.POST.get('kind', '')
            description, lines = request.POST.get('description', ''), _service_lines(muni, rows)
            if voucher is None:
                saved = ledger.create_voucher(request.user, year, on, kind, description, lines)
            else:
                saved = ledger.update_voucher(request.user, voucher, description=description, lines=lines,
                                              on=on, kind=kind)
            messages.success(request, f'سند شماره {saved.number} ذخیره شد.')
            return redirect('main:acc_voucher_detail', voucher_id=saved.id)
        except OfficeError as exc:
            ctx = _form_context(request, muni, year, voucher, rows, str(exc))
            ctx.update(date=request.POST.get('date', ''), kind=request.POST.get('kind', ''),
                       description=request.POST.get('description', ''))
            return render(request, 'main/accounting/voucher_form.html', ctx, status=exc.status)
    rows = ([{'account': l.account_id, 'party': l.party_id or '', 'cost_center': l.cost_center_id or '',
              'line_description': l.description, 'debit': l.debit or '', 'credit': l.credit or ''}
             for l in voucher.lines.all()] if voucher else [])
    ctx = _form_context(request, muni, year, voucher, rows, None)
    ctx.update(date=jalali_str(voucher.date) if voucher else '', kind=voucher.kind if voucher else 'general',
               description=voucher.description if voucher else '')
    return render(request, 'main/accounting/voucher_form.html', ctx)


@_guard()
def acc_voucher_new(request, year_id):
    year = ledger.get_year(request.user, year_id)
    if year.is_closed:
        return render(request, 'main/accounting/voucher_form.html', {'year': year, 'error': 'سال مالی بسته شده است.'},
                      status=409)
    return _voucher_form(request, year)


@_guard()
def acc_voucher_edit(request, voucher_id):
    voucher = ledger.get_voucher(request.user, voucher_id)
    try:
        ledger.check_editable(request.user, voucher)
    except Conflict as exc:
        return render(request, 'main/accounting/voucher_form.html',
                      {'year': voucher.fiscal_year, 'voucher': voucher, 'error': str(exc)}, status=409)
    return _voucher_form(request, voucher.fiscal_year, voucher)


@_guard()
def acc_voucher_detail(request, voucher_id):
    voucher = ledger.get_voucher(request.user, voucher_id)
    lines = voucher.lines.select_related('account', 'party', 'cost_center')
    totals = lines.aggregate(d=Sum('debit'), c=Sum('credit'))
    return render(request, 'main/accounting/voucher_detail.html', {
        'voucher': voucher, 'year': voucher.fiscal_year, 'lines': lines, 'debit': totals['d'] or 0,
        'credit': totals['c'] or 0, 'balanced': ledger.is_balanced(voucher)})


def _act(request, voucher_id, action, done):
    voucher = ledger.get_voucher(request.user, voucher_id)
    try:
        action(request.user, voucher)
        messages.success(request, done)
    except OfficeError as exc:
        _fail(request, exc)
    return voucher


@_guard()
@require_POST
def acc_voucher_finalize(request, voucher_id):
    v = _act(request, voucher_id, ledger.finalize, 'سند قطعی شد.')
    return redirect('main:acc_voucher_detail', voucher_id=v.id)


@_guard()
@require_POST
def acc_voucher_revert(request, voucher_id):
    v = _act(request, voucher_id, ledger.revert_to_temporary, 'سند به حالت موقت برگشت.')
    return redirect('main:acc_voucher_detail', voucher_id=v.id)


@_guard()
@require_POST
def acc_voucher_delete(request, voucher_id):
    v = _act(request, voucher_id, ledger.delete_voucher, 'سند حذف شد.')
    return redirect('main:acc_vouchers', year_id=v.fiscal_year_id)


# ---------- chart of accounts and parties ----------

def new_account(muni, post):
    """Validate and create a chart-of-accounts row from form data; raises Invalid/Conflict."""
    code, title = post.get('code', '').strip(), post.get('title', '').strip()
    if not code.isascii() or not code.isalnum() or len(code) > 20 or not title or len(title) > 200:
        raise Invalid('کد (حروف و رقم انگلیسی، حداکثر ۲۰) و شرح حساب را درست وارد کنید.')
    kind, nature = post.get('kind'), post.get('nature')
    if kind not in dict(Account.KINDS) or nature not in dict(Account.NATURES):
        raise Invalid('نوع یا ماهیت حساب نامعتبر است.')
    parent = Account.objects.filter(municipality=muni, pk=parse_int_or_none(post.get('parent'))).first()
    try:
        with transaction.atomic():
            return Account.objects.create(
                municipality=muni, code=code, title=title, kind=kind, nature=nature, parent=parent,
                is_postable=bool(post.get('is_postable')), requires_party=bool(post.get('requires_party')))
    except IntegrityError:
        raise Conflict('این کد حساب قبلاً ثبت شده است.')


def new_party(muni, post):
    """Validate and create a party from form data; raises Invalid."""
    from main.accounting.parse import digits
    party = Party(municipality=muni, kind=post.get('kind', 'real'), name=post.get('name', '').strip(),
                  national_id=digits(post.get('national_id')), phone=digits(post.get('phone')),
                  mobile=digits(post.get('mobile')), address=post.get('address', '').strip())
    try:
        if party.kind not in dict(Party.KINDS) or not party.name:
            raise ValidationError('نوع و نام طرف حساب را درست وارد کنید.')
        party.full_clean()
        party.save()
    except ValidationError as exc:
        raise Invalid(' '.join(exc.messages))
    return party


@_guard()
def acc_accounts(request):
    muni = ledger.municipality_of(request.user)
    error, status, posted = None, 200, request.POST
    if request.method == 'POST':
        try:
            new_account(muni, request.POST)
            messages.success(request, 'حساب افزوده شد.')
            return redirect('main:acc_accounts')
        except OfficeError as exc:
            error, status = str(exc), exc.status
    return render(request, 'main/accounting/accounts.html', {
        'accounts': Account.objects.filter(municipality=muni), 'kinds': Account.KINDS, 'natures': Account.NATURES,
        'error': error, 'p': posted}, status=status)


@_guard()
def acc_parties(request):
    muni = ledger.municipality_of(request.user)
    error, status = None, 200
    if request.method == 'POST':
        try:
            new_party(muni, request.POST)
            messages.success(request, 'طرف حساب افزوده شد.')
            return redirect('main:acc_parties')
        except OfficeError as exc:
            error, status = str(exc), exc.status
    q = request.GET.get('q', '').strip()
    parties = Party.objects.filter(municipality=muni)
    if q:
        parties = parties.filter(name__icontains=q) | parties.filter(national_id__icontains=q)
    return render(request, 'main/accounting/parties.html', {
        'parties': parties[:200], 'q': q, 'error': error, 'p': request.POST}, status=status)


# ---------- reports ----------

@_guard()
def acc_trial(request, year_id):
    year = ledger.get_year(request.user, year_id)
    final_only = request.GET.get('final') == '1'
    rows, totals = ledger.trial_balance(request.user, year, include_temporary=not final_only)
    return render(request, 'main/accounting/trial_balance.html', {
        'year': year, 'rows': rows, 'totals': totals, 'final_only': final_only})


@_guard()
def acc_ledger(request, year_id, account_id):
    year = ledger.get_year(request.user, year_id)
    muni = ledger.municipality_of(request.user)
    account = get_object_or_404(Account, pk=account_id, municipality=muni)
    final_only = request.GET.get('final') == '1'
    return render(request, 'main/accounting/ledger.html', {
        'year': year, 'account': account, 'final_only': final_only,
        'rows': ledger.account_ledger(request.user, year, account, include_temporary=not final_only)})


# ---------- budget ----------

@_guard()
def acc_budget(request, year_id):
    year = ledger.get_year(request.user, year_id)
    muni = ledger.municipality_of(request.user)
    error, status = None, 200
    if request.method == 'POST':
        try:
            account = Account.objects.filter(municipality=muni, pk=parse_int_or_none(request.POST.get('account'))).first()
            if account is None:
                raise Invalid('حساب را انتخاب کنید.')
            budget.set_budget(request.user, year, account, parse_amount(request.POST.get('amount')))
            messages.success(request, 'بودجه ذخیره شد.')
            return redirect('main:acc_budget', year_id=year.id)
        except OfficeError as exc:
            error, status = str(exc), exc.status
    final_only = request.GET.get('final') == '1'
    rows, totals = budget.report(request.user, year, include_temporary=not final_only)
    choices = Account.objects.filter(municipality=muni, kind__in=budget.BUDGET_KINDS, is_postable=True)
    return render(request, 'main/accounting/budget.html', {
        'year': year, 'rows': rows, 'totals': totals, 'choices': choices, 'final_only': final_only,
        'error': error, 'p': request.POST}, status=status)


def _cell(text):
    """Excel runs cells starting with = + - @ as formulas; titles come from users, so keep them text."""
    text = str(text)
    return "'" + text if text[:1] in ('=', '+', '-', '@') else text


@_guard()
def acc_budget_export(request, year_id):
    year = ledger.get_year(request.user, year_id)
    rows, totals = budget.report(request.user, year, include_temporary=request.GET.get('final') != '1')
    wb = Workbook()
    ws = wb.active
    ws.title = f'بودجه {year.year}'
    ws.sheet_view.rightToLeft = True
    ws.append(['کد', 'شرح', 'نوع', 'بودجه مصوب', 'عملکرد', 'باقی‌مانده', 'درصد'])
    for r in rows:
        ws.append([r['code'], _cell(r['title']), 'منابع' if r['kind'] == 'resource' else 'مصارف',
                   int(r['budget']), int(r['actual']), int(r['remaining']), r['percent']])
    for key, label in (('resource', 'جمع منابع'), ('use', 'جمع مصارف')):
        t = totals[key]
        ws.append(['', label, '', int(t['budget']), int(t['actual']), int(t['budget'] - t['actual']), None])
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="budget-{year.year}.xlsx"'
    wb.save(response)
    return response


# ---------- cash bills ----------

def _bill_form_data(muni):
    return {'parties': Party.objects.filter(municipality=muni),
            'incomes': Account.objects.filter(municipality=muni, kind='budget_resource', is_postable=True),
            'banks': Account.objects.filter(municipality=muni, kind='asset', is_postable=True)}


def _find(model, muni, raw):
    pk = parse_int_or_none(raw)
    return model.objects.filter(municipality=muni, pk=pk).first() if pk else None


@_guard()
def acc_bills(request, year_id):
    year = ledger.get_year(request.user, year_id)
    muni = ledger.municipality_of(request.user)
    error, status = None, 200
    if request.method == 'POST':
        try:
            p = request.POST
            bill = bills.issue_bill(request.user, year, parse_jalali(p.get('date', '')), _find(Party, muni, p.get('party')),
                                    _find(Account, muni, p.get('income_account')), parse_amount(p.get('amount')),
                                    p.get('description', ''))
            messages.success(request, f'فیش شماره {bill.number} صادر شد.')
            return redirect('main:acc_bill_detail', bill_id=bill.id)
        except OfficeError as exc:
            error, status = str(exc), exc.status
    page = Paginator(bills.bills_for(request.user, year), PAGE_SIZE).get_page(request.GET.get('page'))
    return render(request, 'main/accounting/bills.html', {
        'year': year, 'page': page, 'error': error, 'p': request.POST, **_bill_form_data(muni)}, status=status)


def _bill_detail(request, bill, error=None, status=200):
    muni = ledger.municipality_of(request.user)
    return render(request, 'main/accounting/bill_detail.html', {
        'bill': bill, 'year': bill.fiscal_year, 's': bills.summary(bill), 'payments': bill.payments.select_related(
            'voucher', 'bank_account'), 'methods': BillPayment.METHODS, 'error': error, 'p': request.POST,
        **_bill_form_data(muni)}, status=status)


@_guard()
def acc_bill_detail(request, bill_id):
    return _bill_detail(request, bills.get_bill(request.user, bill_id))


@_guard()
@require_POST
def acc_bill_pay(request, bill_id):
    bill = bills.get_bill(request.user, bill_id)
    muni = ledger.municipality_of(request.user)
    p = request.POST
    try:
        bills.record_payment(request.user, bill, parse_jalali(p.get('date', '')), parse_amount(p.get('amount')),
                             _find(Account, muni, p.get('bank_account')), p.get('method', ''), p.get('reference', ''))
    except OfficeError as exc:
        return _bill_detail(request, bill, str(exc), exc.status)
    messages.success(request, 'پرداخت ثبت شد و سند درآمد (موقت) صادر شد.')
    return redirect('main:acc_bill_detail', bill_id=bill.id)


@_guard()
@require_POST
def acc_bill_cancel(request, bill_id):
    bill = bills.get_bill(request.user, bill_id)
    try:
        bills.cancel_bill(request.user, bill)
        messages.success(request, 'فیش ابطال شد.')
    except OfficeError as exc:
        messages.error(request, str(exc))
    return redirect('main:acc_bill_detail', bill_id=bill.id)


@_guard()
@require_POST
def acc_payment_cancel(request, payment_id):
    muni = ledger.municipality_of(request.user)
    payment = get_object_or_404(BillPayment, pk=payment_id, bill__municipality=muni)
    try:
        bills.cancel_payment(request.user, payment)
        messages.success(request, 'پرداخت ابطال شد و سند آن حذف شد.')
    except OfficeError as exc:
        messages.error(request, str(exc))
    return redirect('main:acc_bill_detail', bill_id=payment.bill_id)
