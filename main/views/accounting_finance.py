"""Accountant workspace pages for credit provisioning, contracts, guarantees, payable-document treasury, voucher
images and bulk status change. Presentation only: every rule is in main/accounting/{credit,contracts,treasury,images}.
"""
from datetime import date
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from main.accounting import contracts, credit, formspec, images, ledger, treasury
from main.accounting.formspec import Field
from main.accounting.parse import jalali_str, parse_amount, parse_int_or_none, parse_jalali
from main.models import (Account, Contract, ContractStatement, CostCenter, CreditProvision, DocumentImage, Guarantee, Party,
                         PayableDocument, Voucher)
from main.office.errors import Invalid, OfficeError
from main.views.accounting_panel import PANEL, _done, _failed, _paged, _today_in
from main.views.accounting_views import _guard

REG = PANEL + '_register.html'


def _act(label, url, kind='modal', icon='eye', cls='', confirm=''):
    return {'label': label, 'url': url, 'kind': kind, 'icon': icon, 'cls': cls, 'confirm': confirm}


def _cell(c):
    """Plain value -> text; ('money', n) -> amount; (text, 'ok'|'warn'|'bad'|'brand'|'') -> status chip."""
    if isinstance(c, tuple):
        return {'t': 'money', 'v': c[1]} if c[0] == 'money' else {'t': 'chip', 'v': c[0], 'cls': c[1]}
    return {'t': 'text', 'v': c}


def _reg(ctx, columns, rows, *, empty, new_url=None, new_label='', icon='file', intro=None, filters=None, buttons=None):
    for row in rows:
        row['cells'] = [_cell(c) for c in row['cells']]
    if intro:
        intro['rows'] = [[_cell(c) for c in r] for r in intro['rows']]
    ctx['reg'] = {'columns': columns, 'rows': rows, 'empty': empty, 'new_url': new_url, 'new_label': new_label,
                  'icon': icon, 'intro': intro, 'filters': filters, 'buttons': buttons or []}


def _url(name, *args):
    from django.urls import reverse
    return reverse(f'main:{name}', args=args)


def _modal(request, template, ctx, status=200):
    return render(request, PANEL + template, ctx, status=status)


# ---------- generic modal form ----------

def _form_modal(request, *, title, fields, action, values=None, error=None, status=200, subtitle='', submit='ذخیره',
                multipart=False, extra=None):
    muni = ledger.municipality_of(request.user)
    ctx = {'title': title, 'subtitle': subtitle, 'fields': [(f, f.options(muni)) for f in fields], 'action': action,
           'p': values or {}, 'error': error, 'submit': submit, 'multipart': multipart}
    ctx.update(extra or {})
    return _modal(request, 'form_generic.html', ctx, status)


# ---------- tab builders (called by accounting_panel.render_panel) ----------

def tab_credit(request, year, ctx):
    rows = []
    today = date.today()
    for p in credit.provisions_for(request.user, year).order_by('-number'):
        state = ('باطل', 'bad') if p.canceled_at else (('منقضی', 'warn') if p.expires_on and p.expires_on < today
                                                       else ('فعال', 'ok'))
        rows.append({'cells': [p.number, jalali_str(p.date), p.allocation_no or '—', jalali_str(p.expires_on) or '—',
                               ('money', p.total or 0), state], 'actions': [
            _act('مشاهده', _url('acc_p_credit_detail', p.id))]})
    availability = credit.availability(request.user, year)
    _reg(ctx, ['شماره', 'تاریخ', 'شماره تخصیص', 'انقضا', 'مبلغ (ریال)', 'وضعیت'], rows,
         empty='تامین اعتباری ثبت نشده است.', icon='hand-holding-dollar',
         new_url=None if year.is_closed else _url('acc_p_credit_new', year.id), new_label='تامین اعتبار جدید',
         intro={'title': 'اعتبار قابل تامین به تفکیک حساب مصرف', 'cols': ['حساب', 'بودجه', 'تامین‌شده', 'باقی‌مانده'],
                'rows': [[f'{r["account"].code} - {r["account"].title}', ('money', r['budget']), ('money', r['reserved']),
                          ('money', r['free'])] for r in availability],
                'empty': 'ابتدا بودجه حساب‌های مصارف را ثبت کنید.'})


def tab_contracts(request, year, ctx):
    rows = []
    for c in contracts.contracts_for(request.user, year).order_by('-number'):
        st = {'active': 'ok', 'suspended': 'warn', 'finished': 'brand', 'terminated': 'bad'}[c.status]
        rows.append({'cells': [c.number, c.subject, c.contractor.name, ('money', c.amount), ('money', c.used or 0),
                               (c.get_status_display(), st)],
                     'actions': [_act('مشاهده', _url('acc_p_contract_detail', c.id))]})
    _reg(ctx, ['شماره', 'موضوع', 'پیمانکار', 'مبلغ (ریال)', 'کارکرد تاکنون', 'وضعیت'], rows,
         empty='قراردادی ثبت نشده است.', icon='file-signature',
         new_url=None if year.is_closed else _url('acc_p_contract_new', year.id), new_label='قرارداد جدید')


def tab_guarantees(request, year, ctx):
    today, rows = date.today(), []
    for g in contracts.guarantees_for(request.user).order_by('expires_on'):
        exp = contracts.expiry_state(g, today)
        state = ((g.get_status_display(), 'brand') if g.status != 'active' else
                 ('منقضی شده', 'bad') if exp == 'expired' else ('رو به انقضا', 'warn') if exp == 'soon' else ('معتبر', 'ok'))
        actions = [] if g.status != 'active' else [
            _act('استرداد', _url('acc_p_guarantee_action', g.id, 'returned'), 'post', 'rotate-left', '',
                 'این ضمانت‌نامه مسترد شده ثبت شود؟'),
            _act('ضبط', _url('acc_p_guarantee_action', g.id, 'seized'), 'post', 'ban', 'bad',
                 'این ضمانت‌نامه ضبط شده ثبت شود؟')]
        rows.append({'cells': [g.get_kind_display(), g.party.name, f'{g.get_doc_kind_display()} {g.serial}',
                               f'قرارداد {g.contract.number}' if g.contract else '—', jalali_str(g.expires_on),
                               ('money', g.amount), state], 'actions': actions})
    _reg(ctx, ['نوع', 'صاحب ضمانت‌نامه', 'مدرک', 'قرارداد', 'سررسید', 'مبلغ (ریال)', 'وضعیت'], rows,
         empty='ضمانت‌نامه‌ای ثبت نشده است.', icon='shield-halved',
         new_url=_url('acc_p_guarantee_new'), new_label='ضمانت‌نامه جدید')


def tab_payables(request, year, ctx):
    rows = []
    for d in treasury.documents_for(request.user, year).order_by('due_date'):
        st = {'issued': 'brand', 'passed': 'ok', 'returned': 'bad', 'canceled': ''}[d.status]
        rows.append({'cells': [d.get_kind_display(), d.serial, d.party.name, jalali_str(d.due_date), ('money', d.amount),
                               (d.get_status_display(), st)],
                     'actions': [_act('وضعیت', _url('acc_p_payable_detail', d.id), 'modal', 'arrows-rotate')]})
    _reg(ctx, ['نوع', 'سریال', 'در وجه', 'سررسید', 'مبلغ (ریال)', 'وضعیت'], rows,
         empty='سند پرداختی ثبت نشده است.', icon='money-check-dollar',
         new_url=None if year.is_closed else _url('acc_p_payable_new', year.id), new_label='ثبت سند پرداختی')


def tab_images(request, year, ctx):
    muni = ctx['muni']
    qs = DocumentImage.objects.filter(municipality=muni, voucher__fiscal_year=year).select_related('voucher')
    page = _paged(request, qs)
    rows = [{'cells': [i.voucher.number, i.title, f'{max(1, (i.size + 1023) // 1024)} کیلوبایت', jalali_str(i.created_at.date())],
             'actions': [_act('نمایش', _url('acc_p_image_file', i.id), 'link', 'eye'),
                         _act('حذف', _url('acc_p_image_delete', i.id), 'post', 'trash', 'bad', 'این تصویر حذف شود؟')]}
            for i in page]
    _reg(ctx, ['شماره سند', 'عنوان', 'حجم', 'تاریخ بارگذاری'], rows, empty='تصویری بارگذاری نشده است.',
         icon='images', new_url=None if year.is_closed else _url('acc_p_image_new', year.id), new_label='افزودن تصویر')
    ctx['page'] = page


def tab_statuschange(request, year, ctx):
    qs = ledger.vouchers_for(request.user, year)
    ctx['counts'] = qs.aggregate(total=Count('id'), final=Count('id', filter=Q(status='final')),
                                 temporary=Count('id', filter=Q(status='temporary')))
    ctx['first_no'] = qs.order_by('number').values_list('number', flat=True).first()
    ctx['last_no'] = qs.order_by('-number').values_list('number', flat=True).first()


# ---------- bulk status change ----------

@_guard()
@require_POST
def acc_p_status_change(request, year_id):
    year = ledger.get_year(request.user, year_id)
    p = request.POST
    try:
        changed, skipped = ledger.change_status_range(
            request.user, year, parse_int_or_none(p.get('number_from')), parse_int_or_none(p.get('number_to')),
            p.get('target'))
    except OfficeError as exc:
        return _failed(exc)
    word = 'قطعی' if p.get('target') == 'final' else 'موقت'
    text = f'{changed} سند {word} شد.'
    if skipped:
        text += f' {len(skipped)} سند تغییر نکرد (شماره‌ها: {"، ".join(str(n) for n, _ in skipped[:10])}): ' + skipped[0][1]
    return _done(text)


# ---------- credit provisioning ----------

CREDIT_HEAD = [Field('date', 'تاریخ', 'date', size=1, placeholder='۱۴۰۴/۰۲/۱۱'),
               Field('allocation_no', 'شماره تخصیص', 'text', required=False, size=1, maxlength=30),
               Field('allocation_date', 'تاریخ تخصیص', 'date', required=False, size=1),
               Field('expires_on', 'تاریخ انقضا', 'date', required=False, size=1),
               Field('description', 'توضیحات', 'text', required=False, size=4, maxlength=500)]
CREDIT_ROWS = 6


def _credit_modal(request, year, rows=None, values=None, error=None, status=200):
    muni = ledger.municipality_of(request.user)
    use = Account.objects.filter(municipality=muni, kind='budget_use', is_postable=True)
    source = Account.objects.filter(municipality=muni, kind='budget_resource', is_postable=True)
    return _modal(request, 'credit_form.html', {
        'year': year, 'error': error, 'p': values or {'date': _today_in(year)}, 'head': CREDIT_HEAD,
        'use': use, 'source': source, 'rows': rows or [{}] * CREDIT_ROWS}, status=status)


@_guard()
def acc_p_credit_new(request, year_id):
    year = ledger.get_year(request.user, year_id)
    if request.method != 'POST':
        return _credit_modal(request, year)
    muni, p = ledger.municipality_of(request.user), request.POST
    keys = ('use_account', 'source_account', 'project', 'description', 'amount')
    cols = {k: p.getlist(k) for k in keys}
    rows = [{k: cols[k][i] if i < len(cols[k]) else '' for k in keys} for i in range(len(cols['use_account']))]
    try:
        head = formspec.parse(muni, CREDIT_HEAD, p)
        lines = []
        for n, r in enumerate(rows, 1):
            if not any(str(v).strip() for v in r.values()):
                continue
            lines.append({
                'use_account': Account.objects.filter(municipality=muni, pk=parse_int_or_none(r['use_account'])).first(),
                'source_account': Account.objects.filter(municipality=muni, pk=parse_int_or_none(r['source_account'])).first(),
                'project': r['project'], 'description': r['description'], 'amount': parse_amount(r['amount'])})
        prov = credit.create_provision(request.user, year, head['date'], lines, allocation_no=head['allocation_no'],
                                       allocation_date=head['allocation_date'], expires_on=head['expires_on'],
                                       description=head['description'])
    except OfficeError as exc:
        return _credit_modal(request, year, rows, p, str(exc), exc.status)
    return _done(f'تامین اعتبار شماره {prov.number} ثبت شد.')


@_guard()
def acc_p_credit_detail(request, provision_id):
    prov = credit.get_provision(request.user, provision_id)
    lines = prov.lines.select_related('use_account', 'source_account')
    return _modal(request, 'credit_detail.html', {'prov': prov, 'lines': lines,
                                                  'total': lines.aggregate(s=Sum('amount'))['s'] or 0})


@_guard()
@require_POST
def acc_p_credit_cancel(request, provision_id):
    prov = credit.get_provision(request.user, provision_id)
    try:
        credit.cancel_provision(request.user, prov)
    except OfficeError as exc:
        return _failed(exc)
    return _done('تامین اعتبار باطل شد.')


# ---------- contracts ----------

def _contract_fields():
    return [Field('subject', 'موضوع قرارداد', 'text', size=4, maxlength=300),
            Field('kind', 'نوع قرارداد', 'text', required=False, size=2, maxlength=100),
            Field('contractor', 'پیمانکار', 'fk', model=Party, size=2, label_of=lambda o: o.name),
            Field('date', 'تاریخ قرارداد', 'date', size=1), Field('start_date', 'تاریخ شروع', 'date', size=1),
            Field('end_date', 'تاریخ پایان', 'date', size=1),
            Field('amount', 'مبلغ قرارداد (ریال)', 'amount', size=2),
            Field('ceiling', 'سقف مبلغ (ریال) — خالی = مبلغ قرارداد', 'amount', required=False, size=2),
            Field('cost_center', 'مرکز هزینه', 'fk', model=CostCenter, required=False, size=2),
            Field('supervisor', 'ناظر', 'text', required=False, size=2, maxlength=150),
            Field('vat_pct', '٪ ارزش افزوده', 'pct', required=False, size=1),
            Field('good_performance_pct', '٪ حسن انجام کار', 'pct', required=False, size=1),
            Field('contractor_insurance_pct', '٪ بیمه پیمانکار', 'pct', required=False, size=1),
            Field('employer_insurance_pct', '٪ بیمه کارفرما', 'pct', required=False, size=1),
            Field('tax_pct', '٪ مالیات', 'pct', required=False, size=1),
            Field('adjustable', 'قرارداد تعدیل‌پذیر است', 'bool', size=2),
            Field('description', 'توضیحات', 'text', required=False, size=4, maxlength=500)]


@_guard()
def acc_p_contract_new(request, year_id):
    year = ledger.get_year(request.user, year_id)
    fields, action = _contract_fields(), _url('acc_p_contract_new', year.id)
    if request.method != 'POST':
        return _form_modal(request, title='قرارداد جدید', fields=fields, action=action,
                           values={'date': _today_in(year), 'vat_pct': '10'})
    muni = ledger.municipality_of(request.user)
    try:
        data = formspec.parse(muni, fields, request.POST)
        c = contracts.create_contract(request.user, year, **{k: (v if v != '' else None) if k == 'ceiling' else v
                                                              for k, v in data.items()})
    except OfficeError as exc:
        return _form_modal(request, title='قرارداد جدید', fields=fields, action=action, values=request.POST,
                           error=str(exc), status=exc.status)
    return _done(f'قرارداد شماره {c.number} ثبت شد.')


STATEMENT_FIELDS = [Field('date', 'تاریخ صورت وضعیت', 'date', size=1), Field('gross', 'کارکرد ناخالص (ریال)', 'amount', size=2),
                    Field('description', 'شرح', 'text', required=False, size=4, maxlength=300)]


def _contract_modal(request, contract, error=None, status=200, values=None):
    statements = list(contract.statements.order_by('number'))
    live = [s for s in statements if s.canceled_at is None]
    used = sum((s.gross for s in live), Decimal(0))
    ctx = {'c': contract, 'statements': statements, 'used': used, 'left': contract.ceiling - used,
           'totals': {k: sum((getattr(s, k) for s in live), Decimal(0)) for k in
                      ('gross', 'vat', 'good_performance', 'contractor_insurance', 'employer_insurance', 'tax', 'net')},
           'guarantees': contract.guarantees.all(), 'error': error, 'p': values or {'date': _today_in(contract.fiscal_year)},
           'fields': [(f, []) for f in STATEMENT_FIELDS], 'statuses': Contract.STATUSES, 'year': contract.fiscal_year}
    return _modal(request, 'contract_detail.html', ctx, status)


@_guard()
def acc_p_contract_detail(request, contract_id):
    return _contract_modal(request, contracts.get_contract(request.user, contract_id))


@_guard()
@require_POST
def acc_p_statement_new(request, contract_id):
    contract = contracts.get_contract(request.user, contract_id)
    try:
        data = formspec.parse(ledger.municipality_of(request.user), STATEMENT_FIELDS, request.POST)
        s = contracts.add_statement(request.user, contract, data['date'], data['gross'], data['description'])
    except OfficeError as exc:
        return _contract_modal(request, contract, str(exc), exc.status, request.POST)
    return _done(f'صورت وضعیت شماره {s.number} ثبت شد.')


@_guard()
@require_POST
def acc_p_statement_cancel(request, statement_id):
    muni = ledger.municipality_of(request.user)
    statement = ContractStatement.objects.filter(pk=statement_id, contract__municipality=muni).first()
    if statement is None:
        raise Http404()
    try:
        contracts.cancel_statement(request.user, statement)
    except OfficeError as exc:
        return _failed(exc)
    return _done('صورت وضعیت باطل شد.')


@_guard()
@require_POST
def acc_p_contract_status(request, contract_id):
    contract = contracts.get_contract(request.user, contract_id)
    try:
        contracts.set_status(request.user, contract, request.POST.get('status', ''))
    except OfficeError as exc:
        return _failed(exc)
    return _done('وضعیت قرارداد تغییر کرد.')


# ---------- guarantees ----------

def _guarantee_fields():
    return [Field('kind', 'نوع ضمانت‌نامه', 'select', choices=Guarantee.KINDS, size=2),
            Field('doc_kind', 'نوع مدرک', 'select', choices=Guarantee.DOC_KINDS, size=2),
            Field('party', 'صاحب ضمانت‌نامه', 'fk', model=Party, size=2, label_of=lambda o: o.name),
            Field('contract', 'قرارداد', 'fk', model=Contract, required=False, size=2,
                  label_of=lambda o: f'{o.number} - {o.subject[:30]}'),
            Field('serial', 'شماره / سریال', 'text', size=2, maxlength=60),
            Field('bank', 'بانک صادرکننده', 'text', required=False, size=2, maxlength=100),
            Field('date', 'تاریخ صدور', 'date', size=1), Field('expires_on', 'تاریخ سررسید', 'date', size=1),
            Field('amount', 'مبلغ (ریال)', 'amount', size=2),
            Field('description', 'توضیحات', 'text', required=False, size=4, maxlength=300)]


@_guard()
def acc_p_guarantee_new(request):
    fields, action = _guarantee_fields(), _url('acc_p_guarantee_new')
    if request.method != 'POST':
        return _form_modal(request, title='ضمانت‌نامه جدید', fields=fields, action=action)
    try:
        data = formspec.parse(ledger.municipality_of(request.user), fields, request.POST)
        contracts.create_guarantee(request.user, **data)
    except OfficeError as exc:
        return _form_modal(request, title='ضمانت‌نامه جدید', fields=fields, action=action, values=request.POST,
                           error=str(exc), status=exc.status)
    return _done('ضمانت‌نامه ثبت شد.')


@_guard()
@require_POST
def acc_p_guarantee_action(request, guarantee_id, action):
    if action not in ('returned', 'seized'):
        return HttpResponse(status=404)
    guarantee = contracts.get_guarantee(request.user, guarantee_id)
    try:
        contracts.set_guarantee_status(request.user, guarantee, action, date.today())
    except OfficeError as exc:
        return _failed(exc)
    return _done('وضعیت ضمانت‌نامه ثبت شد.')


# ---------- payable documents ----------

def _payable_fields():
    return [Field('kind', 'نوع سند', 'select', choices=PayableDocument.KINDS, size=1),
            Field('serial', 'سریال / شماره', 'text', size=1, maxlength=60),
            Field('party', 'در وجه', 'fk', model=Party, size=2, label_of=lambda o: o.name),
            Field('bank_account', 'حساب بانک', 'fk', model=Account, where={'kind': 'asset', 'is_postable': True}, size=2,
                  label_of=lambda o: f'{o.code} - {o.title}'),
            Field('issue_date', 'تاریخ صدور', 'date', size=1), Field('due_date', 'تاریخ سررسید', 'date', size=1),
            Field('amount', 'مبلغ (ریال)', 'amount', size=2),
            Field('description', 'شرح', 'text', required=False, size=4, maxlength=300)]


@_guard()
def acc_p_payable_new(request, year_id):
    year = ledger.get_year(request.user, year_id)
    fields, action = _payable_fields(), _url('acc_p_payable_new', year.id)
    if request.method != 'POST':
        return _form_modal(request, title='ثبت سند پرداختی', fields=fields, action=action,
                           values={'issue_date': _today_in(year)})
    try:
        data = formspec.parse(ledger.municipality_of(request.user), fields, request.POST)
        treasury.issue(request.user, year, **data)
    except OfficeError as exc:
        return _form_modal(request, title='ثبت سند پرداختی', fields=fields, action=action, values=request.POST,
                           error=str(exc), status=exc.status)
    return _done('سند پرداختی ثبت شد.')


def _payable_modal(request, doc, error=None, status=200, values=None):
    return _modal(request, 'payable_detail.html', {
        'd': doc, 'events': doc.events.select_related('user'), 'error': error, 'allowed': treasury.TRANSITIONS[doc.status],
        'statuses': [(k, v) for k, v in PayableDocument.STATUSES if k in treasury.TRANSITIONS[doc.status]],
        'p': values or {'date': jalali_str(date.today())}}, status)


@_guard()
def acc_p_payable_detail(request, doc_id):
    return _payable_modal(request, treasury.get_document(request.user, doc_id))


@_guard()
@require_POST
def acc_p_payable_status(request, doc_id):
    doc = treasury.get_document(request.user, doc_id)
    try:
        treasury.change_status(request.user, doc, request.POST.get('status', ''), parse_jalali(request.POST.get('date', '')),
                               request.POST.get('note', ''))
    except OfficeError as exc:
        return _payable_modal(request, doc, str(exc), exc.status, request.POST)
    return _done('وضعیت سند پرداختی تغییر کرد.')


# ---------- voucher images ----------

IMAGE_FIELDS = [Field('number', 'شماره سند', 'text', size=1, maxlength=10), Field('title', 'عنوان تصویر', 'text', size=3, maxlength=150)]


@_guard()
def acc_p_image_new(request, year_id):
    year = ledger.get_year(request.user, year_id)
    action = _url('acc_p_image_new', year.id)
    kw = dict(title='افزودن تصویر سند', fields=IMAGE_FIELDS, action=action, multipart=True,
              subtitle='فایل PDF یا تصویر (JPG، PNG) تا ۵ مگابایت.', extra={'file_field': True})
    if request.method != 'POST':
        return _form_modal(request, **kw)
    muni = ledger.municipality_of(request.user)
    try:
        number = parse_int_or_none(request.POST.get('number'))
        voucher = ledger.vouchers_for(request.user, year).filter(number=number).first() if number else None
        if voucher is None:
            raise Invalid('سندی با این شماره در این سال مالی نیست.')
        images.upload(request.user, voucher, request.FILES.get('file'), request.POST.get('title', ''))
    except OfficeError as exc:
        return _form_modal(request, values=request.POST, error=str(exc), status=exc.status, **kw)
    return _done('تصویر بارگذاری شد.')


@_guard()
def acc_p_image_file(request, image_id):
    image = images.get_image(request.user, image_id)
    try:
        handle = image.file.open('rb')
    except FileNotFoundError:
        raise Http404()
    response = FileResponse(handle, content_type=image.content_type or 'application/octet-stream')
    response['Content-Disposition'] = 'inline'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@_guard()
@require_POST
def acc_p_image_delete(request, image_id):
    image = images.get_image(request.user, image_id)
    try:
        images.delete(request.user, image)
    except OfficeError as exc:
        return _failed(exc)
    return _done('تصویر حذف شد.')


BUILDERS = {'credit': tab_credit, 'contracts': tab_contracts, 'guarantees': tab_guarantees, 'payables': tab_payables,
            'images': tab_images, 'statuschange': tab_statuschange}
