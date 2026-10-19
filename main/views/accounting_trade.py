"""Trade screens of the accountant workspace: products, invoices, point of sale, stock, stock documents, production,
consignment and profit. Presentation only: every rule is in main/accounting/trade."""
from decimal import Decimal
from datetime import date

from django.http import Http404
from django.shortcuts import render
from django.views.decorators.http import require_POST

from main.accounting import formspec, ledger, tools as paper_tools
from main.accounting.formspec import Field
from main.accounting.parse import digits, jalali_str, parse_amount, parse_int_or_none, parse_jalali
from main.accounting.trade import inventory, invoices, posting
from main.models import Account, Invoice, InvoicePayment, Party, Product, Warehouse
from main.office.errors import Invalid, OfficeError
from main.views.accounting_finance import _act, _form_modal, _modal, _reg, _url
from main.views.accounting_panel import PANEL, _date_param, _done, _failed, _paged, _today_in
from main.views.accounting_views import _guard

INVOICE_KINDS = [k for k, _ in Invoice.KINDS]
STATUS_CHIPS = {'issued': ('صادر شده', 'ok'), 'converted': ('تبدیل‌شده', 'brand'), 'canceled': ('ابطال‌شده', 'bad')}
LOCK_NOTE = 'سندی که تاریخ آن در بازه قفل یا سال بسته باشد تغییر نمی‌کند.'


def _num(text):
    """Quantity or money text typed by a person -> plain ASCII digits and a dot."""
    return digits(text).replace('٫', '.').replace('٬', '').replace(',', '').replace(' ', '')


def _party_name(o):
    return o.name


def _post_lines(request, muni, names, *, money=()):
    """Rows of a line table: the posted columns ``names`` (the first is the product id), skipping blank rows."""
    post = request.POST
    products = {str(p.id): p for p in Product.objects.filter(municipality=muni)}
    columns = {n: post.getlist(n) for n in names}
    rows = []
    for i in range(max((len(v) for v in columns.values()), default=0)):
        raw = {n: (columns[n][i].strip() if i < len(columns[n]) else '') for n in names}
        if not any(raw.values()):
            continue
        if raw[names[0]] not in products:
            raise Invalid(f'ردیف {i + 1}: کالا را انتخاب کنید.')
        item = {names[0]: products[raw[names[0]]]}
        for n in names[1:]:
            item[n] = parse_amount(raw[n]) if n in money else _num(raw[n])
        rows.append(item)
    return rows


def _posted_rows(post, names):
    columns = {n: post.getlist(n) for n in names}
    return [{n: (columns[n][i] if i < len(columns[n]) else '') for n in names}
            for i in range(max((len(v) for v in columns.values()), default=0))]


def _trade_form(request, *, title, action, fields, columns, values=None, rows=None, error=None, status=200, submit='ذخیره',
                show_totals=False, hint='', subtitle='', price_kind='sell'):
    muni = ledger.municipality_of(request.user)
    products = [{'id': p.id, 'label': f'{p.code} - {p.name}', 'price': int(p.sell_price), 'buy': int(p.buy_price)}
                for p in Product.objects.filter(municipality=muni, is_active=True)]
    ctx = {'title': title, 'subtitle': subtitle, 'action': action, 'fields': [(f, f.options(muni)) for f in fields], 'columns': columns,
           'p': values or {}, 'rows': rows or [{}], 'error': error, 'submit': submit, 'products': products, 'show_totals': show_totals,
           'hint': hint, 'price_kind': price_kind}
    return render(request, PANEL + 'trade_form.html', ctx, status=status)


# =====================================================================================================================
# products and warehouses
# =====================================================================================================================

PRODUCT_FIELDS = [Field('code', 'کد کالا', 'text', size=1, maxlength=30), Field('name', 'نام کالا', 'text', size=2, maxlength=200),
                  Field('unit', 'واحد', 'text', size=1, maxlength=30), Field('category', 'دسته', 'text', required=False, size=2, maxlength=100),
                  Field('barcode', 'بارکد', 'text', required=False, size=2, maxlength=40),
                  Field('buy_price', 'قیمت خرید (ریال)', 'amount', required=False, size=2),
                  Field('sell_price', 'قیمت فروش (ریال)', 'amount', required=False, size=2),
                  Field('min_stock', 'حداقل موجودی', 'pct', required=False, size=2)]
NEW_PRODUCT_FIELDS = PRODUCT_FIELDS + [Field('opening_qty', 'موجودی اول دوره', 'pct', required=False, size=2),
                                       Field('opening_cost', 'بهای هر واحد موجودی اول دوره (ریال)', 'amount', required=False, size=2)]
EDIT_PRODUCT_FIELDS = PRODUCT_FIELDS + [Field('is_active', 'فعال', 'bool', required=False, size=2)]


def _product_values(muni, fields, post):
    data = formspec.parse(muni, fields, post)
    for key in ('min_stock', 'opening_qty'):
        if key in data:
            data[key] = _num(data[key]) or 0
    return data


def tab_trade_products(request, year, ctx):
    q = request.GET.get('q', '').strip()
    stock = {r['product'].id: r for r in inventory.stock_report(request.user)}
    rows = []
    for p in inventory.products_for(request.user).order_by('code'):
        if q and q.lower() not in f'{p.code} {p.name} {p.barcode}'.lower():
            continue
        s = stock[p.id]
        state = ('کمبود', 'bad') if s['low'] else (('فعال', 'ok') if p.is_active else ('غیرفعال', ''))
        rows.append({'cells': [p.code, p.name, p.unit, ('money', p.buy_price), ('money', p.sell_price), f'{s["qty"].normalize():f}', state],
                     'actions': [_act('کاردکس', _url('acc_p_trade_kardex', p.id), 'modal', 'list-ol'),
                                 _act('ویرایش', _url('acc_p_trade_product_edit', p.id), 'modal', 'pen')]})
    _reg(ctx, ['کد', 'نام', 'واحد', 'قیمت خرید', 'قیمت فروش', 'موجودی', 'وضعیت'], rows, empty='کالایی ثبت نشده است.', icon='boxes-stacked',
         new_url=_url('acc_p_trade_product_new'), new_label='کالای جدید', filters={'q': 'نام، کد یا بارکد'},
         buttons=[_act('انبارها', _url('acc_p_trade_warehouses'), 'modal', 'warehouse')])


@_guard()
def acc_p_trade_product_new(request):
    muni = ledger.municipality_of(request.user)
    kw = dict(title='کالای جدید', fields=NEW_PRODUCT_FIELDS, action=_url('acc_p_trade_product_new'))
    if request.method != 'POST':
        return _form_modal(request, values={'unit': 'عدد'}, **kw)
    try:
        data = _product_values(muni, NEW_PRODUCT_FIELDS, request.POST)
        opening_date = None
        product = inventory.create_product(request.user, opening_date=opening_date, **data)
    except OfficeError as exc:
        return _form_modal(request, values=request.POST, error=str(exc), status=exc.status, **kw)
    return _done(f'کالای «{product.name}» ثبت شد.')


@_guard()
def acc_p_trade_product_edit(request, product_id):
    muni = ledger.municipality_of(request.user)
    product = inventory.get_product(request.user, product_id)
    kw = dict(title=f'ویرایش «{product.name}»', fields=EDIT_PRODUCT_FIELDS, action=_url('acc_p_trade_product_edit', product.id))
    if request.method != 'POST':
        values = formspec.initial(EDIT_PRODUCT_FIELDS, product)
        values['min_stock'] = f'{product.min_stock.normalize():f}'
        return _form_modal(request, values=values, **kw)
    try:
        data = _product_values(muni, EDIT_PRODUCT_FIELDS, request.POST)
        inventory.update_product(request.user, product, **data)
    except OfficeError as exc:
        return _form_modal(request, values=request.POST, error=str(exc), status=exc.status, **kw)
    return _done('کالا ذخیره شد.')


@_guard()
def acc_p_trade_kardex(request, product_id):
    product = inventory.get_product(request.user, product_id)
    date_from, err_from = _date_param(request, 'date_from')
    date_to, err_to = _date_param(request, 'date_to')
    rows = inventory.kardex(request.user, product, date_from=date_from, date_to=date_to)
    return _modal(request, 'trade_kardex.html', {'product': product, 'rows': rows, 'error': err_from or err_to,
                                                 'value': inventory.valuation(ledger.municipality_of(request.user), product)})


@_guard()
def acc_p_trade_warehouses(request):
    muni = ledger.municipality_of(request.user)
    fields = [Field('code', 'کد', 'text', size=1, maxlength=20), Field('name', 'نام انبار', 'text', size=2, maxlength=100),
              Field('is_default', 'انبار پیش‌فرض', 'bool', required=False, size=1)]
    ctx = {'warehouses': inventory.warehouses_for(request.user), 'fields': [(f, []) for f in fields], 'p': {}, 'error': None}
    if request.method == 'POST':
        try:
            data = formspec.parse(muni, fields, request.POST)
            inventory.create_warehouse(request.user, code=data['code'], name=data['name'], is_default=bool(data.get('is_default')))
        except OfficeError as exc:
            return _modal(request, 'trade_warehouses.html', {**ctx, 'p': request.POST, 'error': str(exc)}, exc.status)
        ctx['warehouses'] = inventory.warehouses_for(request.user)
        ctx['notice'] = 'انبار ثبت شد.'
    return _modal(request, 'trade_warehouses.html', ctx)


# =====================================================================================================================
# invoices
# =====================================================================================================================

INVOICE_COLUMNS = [('product', 'کالا', 'product'), ('qty', 'تعداد', 'qty'), ('unit_price', 'قیمت واحد (ریال)', 'money'),
                   ('discount', 'تخفیف (ریال)', 'money')]
INVOICE_NAMES = [c[0] for c in INVOICE_COLUMNS]


def _invoice_fields(kind):
    return [Field('on', 'تاریخ', 'date', size=1),
            Field('party', 'مشتری' if kind in ('sale', 'proforma', 'order', 'sale_return') else 'تامین‌کننده', 'fk', model=Party,
                  size=2, label_of=_party_name),
            Field('warehouse', 'انبار', 'fk', model=Warehouse, size=1, label_of=str, required=False),
            Field('visitor', 'ویزیتور', 'text', required=False, size=1, maxlength=100),
            Field('discount', 'تخفیف کل فاکتور (ریال)', 'amount', required=False, size=1),
            Field('tax', 'مالیات (ریال؛ خالی = از درصد تنظیمات)', 'amount', required=False, size=2),
            Field('note', 'توضیحات', 'text', required=False, size=4, maxlength=300)] + (
        [Field('allow_shortage', 'ثبت با وجود کمبود موجودی', 'bool', required=False, size=2)] if kind in
        ('sale', 'purchase_return', 'order', 'proforma') else []) + (
        [Field('paid', 'پرداخت نقدی هنگام صدور (ریال)', 'amount', required=False, size=2)] if kind in ('sale', 'purchase') else [])


def tab_trade_invoices(request, year, ctx):
    g = request.GET
    kind = g.get('kind') if g.get('kind') in INVOICE_KINDS else None
    qs = invoices.invoices_for(request.user, year, kind=kind).order_by('-date', '-id')
    q = g.get('q', '').strip()
    if q:
        qs = qs.filter(party__name__icontains=q) | qs.filter(number__in=[int(digits(q))] if digits(q).isdigit() else [])
    page = _paged(request, qs)
    rows = []
    for inv in page:
        paid = invoices.paid_of(inv)
        state = STATUS_CHIPS[inv.status]
        if inv.status == 'issued' and inv.kind in ('sale', 'purchase'):
            state = ('تسویه‌شده', 'ok') if paid >= inv.total else (('قسمتی', 'warn') if paid else ('پرداخت‌نشده', 'brand'))
        rows.append({'cells': [inv.get_kind_display(), inv.number, jalali_str(inv.date), inv.party.name, ('money', inv.total),
                               ('ثبت‌شده در دفتر', 'ok') if inv.voucher_id else '—', state],
                     'actions': [_act('مشاهده', _url('acc_p_trade_invoice', inv.id))]})
    new = [] if year.is_closed else [_act(label, _url('acc_p_trade_invoice_new', year.id, k), 'modal', 'plus', 'ac-btn-brand' if k == 'sale' else '')
                                     for k, label in Invoice.KINDS]
    _reg(ctx, ['نوع', 'شماره', 'تاریخ', 'طرف حساب', 'مبلغ (ریال)', 'دفتر', 'وضعیت'], rows, empty='فاکتوری ثبت نشده است.', icon='file-invoice',
         filters={'q': 'نام طرف حساب یا شماره', 'select': ('kind', 'همه انواع', list(Invoice.KINDS))}, buttons=new + [
             _act('تنظیمات', _url('acc_p_trade_settings'), 'modal', 'gear')])
    ctx['page'] = page


@_guard()
def acc_p_trade_invoice_new(request, year_id, kind):
    if kind not in INVOICE_KINDS:
        raise Http404()
    year = ledger.get_year(request.user, year_id)
    muni = ledger.municipality_of(request.user)
    fields = _invoice_fields(kind)
    title = f'{dict(Invoice.KINDS)[kind]} جدید'
    action = _url('acc_p_trade_invoice_new', year.id, kind)
    if request.method != 'POST':
        return _trade_form(request, title=title, action=action, fields=fields, columns=INVOICE_COLUMNS, show_totals=True,
                           values={'on': _today_in(year), 'warehouse': inventory.default_warehouse(muni).id}, hint=LOCK_NOTE,
                           price_kind='buy' if kind in ('purchase', 'purchase_return') else 'sell')
    rows = _posted_rows(request.POST, INVOICE_NAMES)
    try:
        data = formspec.parse(muni, fields, request.POST)
        lines = _post_lines(request, muni, INVOICE_NAMES, money=('unit_price', 'discount'))
        invoice = invoices.create_invoice(
            request.user, year, kind, data['on'], data['party'], lines, warehouse=data.get('warehouse'), discount=data.get('discount') or 0,
            tax=data.get('tax') or None, visitor=data.get('visitor') or '', note=data.get('note') or '',
            allow_shortage=bool(data.get('allow_shortage')), paid=data.get('paid') or 0)
    except OfficeError as exc:
        return _trade_form(request, title=title, action=action, fields=fields, columns=INVOICE_COLUMNS, values=request.POST, rows=rows,
                           error=str(exc), status=exc.status, show_totals=True, hint=LOCK_NOTE,
                           price_kind='buy' if kind in ('purchase', 'purchase_return') else 'sell')
    return _done(f'{invoice.get_kind_display()} شماره {invoice.number} ثبت شد.')


def _invoice_modal(request, invoice, error=None, status=200, posted=None, notice=None):
    muni = ledger.municipality_of(request.user)
    paid = invoices.paid_of(invoice)
    return _modal(request, 'trade_invoice.html', {
        'inv': invoice, 'title': f'{invoice.get_kind_display()} شماره {invoice.number}', 'lines': invoice.lines.select_related('product'), 'payments': invoice.payments.select_related('bank_account'),
        'paid': paid, 'left': invoice.total - paid, 'error': error, 'notice': notice,
        'p': posted or {'date': _today_in(invoice.fiscal_year), 'amount': ''}, 'methods': InvoicePayment.METHODS,
        'bank_accounts': Account.objects.filter(municipality=muni, kind='asset', is_postable=True),
        'can_pay': invoice.kind in invoices.PAYABLE_KINDS and invoice.status == 'issued' and not invoice.fiscal_year.is_closed,
        'can_convert': invoice.kind in ('proforma', 'order') and invoice.status == 'issued',
        'can_post': invoice.kind not in ('proforma', 'order') and invoice.status == 'issued'}, status)


@_guard()
def acc_p_trade_invoice(request, invoice_id):
    return _invoice_modal(request, invoices.get_invoice(request.user, invoice_id))


@_guard()
@require_POST
def acc_p_trade_invoice_pay(request, invoice_id):
    invoice = invoices.get_invoice(request.user, invoice_id)
    muni = ledger.municipality_of(request.user)
    p = request.POST
    try:
        bank = Account.objects.filter(municipality=muni, pk=parse_int_or_none(p.get('bank_account'))).first() if p.get('bank_account') else None
        invoices.add_payment(request.user, invoice, parse_jalali(p.get('date', '')), parse_amount(p.get('amount')), p.get('method', ''), bank,
                             p.get('note', ''))
    except OfficeError as exc:
        return _invoice_modal(request, invoice, str(exc), exc.status, p)
    return _invoice_modal(request, invoice, notice='پرداخت ثبت شد.')


@_guard()
@require_POST
def acc_p_trade_payment_delete(request, payment_id):
    muni = ledger.municipality_of(request.user)
    payment = InvoicePayment.objects.select_related('invoice__fiscal_year').filter(pk=payment_id, invoice__municipality=muni).first()
    if payment is None:
        raise Http404()
    invoice = payment.invoice
    try:
        invoices.delete_payment(request.user, payment)
    except OfficeError as exc:
        return _invoice_modal(request, invoice, str(exc), exc.status)
    return _invoice_modal(request, invoice, notice='پرداخت حذف شد.')


@_guard()
@require_POST
def acc_p_trade_invoice_action(request, invoice_id, action):
    invoice = invoices.get_invoice(request.user, invoice_id)
    done = {'post': 'فاکتور در دفتر ثبت شد (سند موقت).', 'unpost': 'ثبت دفتری فاکتور برداشته شد.', 'cancel': 'فاکتور ابطال شد.',
            'convert': 'پیش‌فاکتور به فاکتور فروش تبدیل شد.'}
    try:
        if action == 'post':
            posting.post_invoice(request.user, invoice)
        elif action == 'unpost':
            posting.unpost_invoice(request.user, invoice)
        elif action == 'cancel':
            invoices.cancel_invoice(request.user, invoice)
        elif action == 'convert':
            invoices.convert(request.user, invoice, date.today() if invoice.fiscal_year.start_date <= date.today() <= invoice.fiscal_year.end_date
                             else invoice.date, allow_shortage=request.POST.get('allow_shortage') == 'on')
        else:
            raise Http404()
    except OfficeError as exc:
        return _failed(exc)
    return _done(done[action])


INVOICE_SETTINGS_FIELDS = [
    Field('receivable_account', 'حساب دریافتنی (مشتریان)', 'fk', model=Account, where={'is_postable': True}, required=False, size=2, label_of=str),
    Field('payable_account', 'حساب پرداختنی (تامین‌کنندگان)', 'fk', model=Account, where={'is_postable': True}, required=False, size=2,
          label_of=str),
    Field('sales_account', 'حساب درآمد فروش', 'fk', model=Account, where={'is_postable': True}, required=False, size=2, label_of=str),
    Field('inventory_account', 'حساب موجودی کالا', 'fk', model=Account, where={'is_postable': True}, required=False, size=2, label_of=str),
    Field('cogs_account', 'حساب بهای تمام‌شده فروش', 'fk', model=Account, where={'is_postable': True}, required=False, size=2, label_of=str),
    Field('tax_account', 'حساب مالیات بر ارزش افزوده', 'fk', model=Account, where={'is_postable': True}, required=False, size=2, label_of=str),
    Field('vat_percent', 'درصد مالیات بر ارزش افزوده', 'pct', required=False, size=2),
    Field('allow_shortage', 'فروش با کمبود موجودی مجاز باشد', 'bool', required=False, size=2)]


@_guard()
def acc_p_trade_settings(request):
    muni = ledger.municipality_of(request.user)
    config = invoices.settings_of(request.user)
    kw = dict(title='تنظیمات بازرگانی', fields=INVOICE_SETTINGS_FIELDS, action=_url('acc_p_trade_settings'),
              subtitle='حساب‌هایی که فاکتور هنگام «ثبت در دفتر» از آن‌ها استفاده می‌کند. خالی بگذارید تا فاکتورها فقط در همین بخش بمانند.')
    if request.method != 'POST':
        values = formspec.initial(INVOICE_SETTINGS_FIELDS, config)
        values['vat_percent'] = f'{Decimal(config.vat_percent).normalize():f}'
        return _form_modal(request, values=values, **kw)
    try:
        data = formspec.parse(muni, INVOICE_SETTINGS_FIELDS, request.POST)
        data['vat_percent'] = _num(data['vat_percent']) or 0
        invoices.update_settings(request.user, **data)
    except OfficeError as exc:
        return _form_modal(request, values=request.POST, error=str(exc), status=exc.status, **kw)
    return _done('تنظیمات بازرگانی ذخیره شد.')


@_guard()
def acc_p_trade_print(request, invoice_id):
    invoice = invoices.get_invoice(request.user, invoice_id)
    key = request.GET.get('paper') if request.GET.get('paper') in paper_tools.PAPERS else 'a4'
    return render(request, 'main/accounting/print_invoice.html', {
        'inv': invoice, 'lines': invoice.lines.select_related('product'), 'muni': ledger.municipality_of(request.user), 'paper': key,
        'paper_size': paper_tools.PAPERS[key][1], 'papers': [(k, v[0]) for k, v in paper_tools.PAPERS.items()],
        'paid': invoices.paid_of(invoice)})


BUILDERS = {'trade_products': tab_trade_products, 'trade_invoices': tab_trade_invoices}
