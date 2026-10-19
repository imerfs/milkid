"""Trade screens, part two: point of sale, stock report, stock documents, production, consignment and profit.
Presentation only: every rule is in main/accounting/trade."""
from datetime import date

from django.http import Http404, HttpResponse, JsonResponse
from django.views.decorators.http import require_POST
from openpyxl import Workbook

from main.accounting import formspec, ledger
from main.accounting.formspec import Field
from main.accounting.parse import jalali_str, parse_int_or_none, parse_jalali
from main.accounting.trade import consignment, inventory, invoices, production, stockdocs
from main.models import Account, Consignment, Invoice, InvoicePayment, Party, Product, StockDoc, Warehouse
from main.office.errors import Invalid, OfficeError
from main.views.accounting_finance import _act, _modal, _reg, _url
from main.views.accounting_panel import _date_param, _done, _failed, _paged, _today_in
from main.views.accounting_trade import (LOCK_NOTE, _num, _party_name, _post_lines, _posted_rows, _trade_form)
from main.views.accounting_views import _cell, _guard


# =====================================================================================================================
# point of sale
# =====================================================================================================================

def tab_trade_pos(request, year, ctx):
    muni = ctx['muni']
    stock = {r['product'].id: r['qty'] for r in inventory.stock_report(request.user)}
    products = [{'id': p.id, 'code': p.code, 'name': p.name, 'barcode': p.barcode, 'price': int(p.sell_price), 'stock': float(stock.get(p.id, 0)),
                 'unit': p.unit} for p in inventory.products_for(request.user, active=True)]
    config = invoices.settings_of(request.user)
    last = Invoice.objects.filter(municipality=muni, fiscal_year=year, kind='sale', created_by=request.user).order_by('-id').first()
    ctx.update(pos_products=products, vat_percent=float(config.vat_percent), last_sale=last,
               bank_accounts=Account.objects.filter(municipality=muni, kind='asset', is_postable=True),
               methods=InvoicePayment.METHODS, today=_today_in(year))


@_guard()
@require_POST
def acc_p_trade_pos_sale(request, year_id):
    year = ledger.get_year(request.user, year_id)
    muni = ledger.municipality_of(request.user)
    p = request.POST
    try:
        lines = _post_lines(request, muni, ['product', 'qty', 'unit_price'], money=('unit_price',))
        if not lines:
            raise Invalid('سبد فروش خالی است.')
        on = parse_jalali(p.get('date')) if p.get('date') else date.today()
        bank = (Account.objects.filter(municipality=muni, pk=parse_int_or_none(p.get('bank_account'))).first()
                if p.get('bank_account') else None)
        items = [{'product': l['product'], 'qty': l['qty'], 'unit_price': l['unit_price']} for l in lines]
        invoice = invoices.quick_sale(request.user, year, items, on=on, method=p.get('method') or 'cash', bank_account=bank,
                                      visitor=p.get('visitor', ''), allow_shortage=p.get('allow_shortage') == 'on')
    except OfficeError as exc:
        return _failed(exc)
    return _done(f'فروش سریع ثبت شد: فاکتور شماره {invoice.number}، مبلغ {int(invoice.total):,} ریال.')


@_guard()
def acc_p_trade_find(request):
    """Product lookup for the point of sale (barcode scanner or typed text)."""
    product = inventory.find_product(request.user, request.GET.get('q', ''))
    if product is None:
        return JsonResponse({'found': False})
    muni = ledger.municipality_of(request.user)
    return JsonResponse({'found': True, 'id': product.id, 'code': product.code, 'name': product.name, 'price': int(product.sell_price),
                         'unit': product.unit, 'stock': float(inventory.valuation(muni, product)['qty'])})


# =====================================================================================================================
# stock report and stock documents
# =====================================================================================================================

def tab_trade_stock(request, year, ctx):
    g = request.GET
    warehouses = inventory.warehouses_for(request.user)
    warehouse = warehouses.filter(pk=g.get('warehouse')).first() if g.get('warehouse', '').isdigit() else None
    upto, error = _date_param(request, 'upto')
    low = g.get('low') == '1'
    rows = inventory.stock_report(request.user, warehouse=warehouse, upto=upto, low_only=low) if not error else []
    ctx.update(stock_rows=rows, warehouses=warehouses, warehouse=warehouse, stock_error=error, low_only=low,
               stock_total=sum(r['value'] for r in rows), export_query=g.urlencode())


@_guard()
def acc_p_trade_stock_export(request, year_id):
    ledger.get_year(request.user, year_id)
    muni = ledger.municipality_of(request.user)
    g = request.GET
    warehouse = Warehouse.objects.filter(municipality=muni, pk=g.get('warehouse')).first() if g.get('warehouse', '').isdigit() else None
    upto, error = _date_param(request, 'upto')
    if error:
        return HttpResponse(error, status=400, content_type='text/plain; charset=utf-8')
    rows = inventory.stock_report(request.user, warehouse=warehouse, upto=upto, low_only=g.get('low') == '1')
    wb = Workbook()
    ws = wb.active
    ws.title = 'موجودی'
    ws.sheet_view.rightToLeft = True
    ws.append(['کد', 'کالا', 'واحد', 'موجودی', 'میانگین بها', 'ارزش', 'حداقل'])
    for r in rows:
        ws.append([r['product'].code, _cell(r['product'].name), r['product'].unit, float(r['qty']), inventory.rial(r['avg']), r['value'],
                   float(r['min_stock'])])
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="stock.xlsx"'
    wb.save(response)
    return response


DOC_COLUMNS = {
    'receipt': [('product', 'کالا', 'product'), ('qty', 'تعداد', 'qty'), ('unit_cost', 'بهای هر واحد (ریال)', 'money')],
    'issue': [('product', 'کالا', 'product'), ('qty', 'تعداد', 'qty')],
    'transfer': [('product', 'کالا', 'product'), ('qty', 'تعداد', 'qty')],
    'adjust': [('product', 'کالا', 'product'), ('qty', 'تعداد (منفی = کسر)', 'qty'), ('unit_cost', 'بهای هر واحد برای افزایش (ریال)', 'money')],
    'stocktake': [('product', 'کالا', 'product'), ('counted', 'مقدار شمارش‌شده', 'qty')],
}


def _doc_fields(kind):
    fields = [Field('on', 'تاریخ', 'date', size=1),
              Field('warehouse', 'انبار مبدأ' if kind == 'transfer' else 'انبار', 'fk', model=Warehouse, size=2, label_of=str)]
    if kind == 'transfer':
        fields.append(Field('to_warehouse', 'انبار مقصد', 'fk', model=Warehouse, size=2, label_of=str))
    fields.append(Field('note', 'توضیحات', 'text', required=False, size=4, maxlength=300))
    return fields


def tab_trade_docs(request, year, ctx):
    g = request.GET
    kind = g.get('kind') if g.get('kind') in dict(StockDoc.KINDS) else None
    page = _paged(request, stockdocs.docs_for(request.user, year, kind=kind).order_by('-date', '-id'))
    rows = []
    for d in page:
        place = d.warehouse.name + (f' ← {d.to_warehouse.name}' if d.to_warehouse else '')
        rows.append({'cells': [d.get_kind_display(), d.number, jalali_str(d.date), place, d.note or '—',
                               ('ابطال‌شده', 'bad') if d.canceled_at else ('ثبت‌شده', 'ok')],
                     'actions': [_act('مشاهده', _url('acc_p_trade_doc', d.id))]})
    new = [] if year.is_closed else [_act(label, _url('acc_p_trade_doc_new', year.id, k), 'modal', 'plus', 'ac-btn-brand' if k == 'receipt' else '')
                                     for k, label in StockDoc.KINDS]
    _reg(ctx, ['نوع', 'شماره', 'تاریخ', 'انبار', 'توضیحات', 'وضعیت'], rows, empty='سند انباری ثبت نشده است.', icon='dolly', buttons=new,
         filters={'select': ('kind', 'همه انواع', list(StockDoc.KINDS))})
    ctx['page'] = page


@_guard()
def acc_p_trade_doc_new(request, year_id, kind):
    if kind not in DOC_COLUMNS:
        raise Http404()
    year = ledger.get_year(request.user, year_id)
    muni = ledger.municipality_of(request.user)
    fields, columns = _doc_fields(kind), DOC_COLUMNS[kind]
    names = [c[0] for c in columns]
    title, action = f'{dict(StockDoc.KINDS)[kind]} جدید', _url('acc_p_trade_doc_new', year.id, kind)
    hint = 'مقدار شمارش‌شده با موجودی دفتری مقایسه می‌شود و فقط تفاوت ثبت می‌شود.' if kind == 'stocktake' else LOCK_NOTE
    if request.method != 'POST':
        return _trade_form(request, title=title, action=action, fields=fields, columns=columns, hint=hint,
                           values={'on': _today_in(year), 'warehouse': inventory.default_warehouse(muni).id})
    rows = _posted_rows(request.POST, names)
    try:
        data = formspec.parse(muni, fields, request.POST)
        lines = _post_lines(request, muni, names, money=('unit_cost',))
        doc = stockdocs.create_doc(request.user, year, kind, data['on'], data['warehouse'], lines, to_warehouse=data.get('to_warehouse'),
                                   note=data.get('note') or '')
    except OfficeError as exc:
        return _trade_form(request, title=title, action=action, fields=fields, columns=columns, values=request.POST, rows=rows,
                           error=str(exc), status=exc.status, hint=hint)
    return _done(f'{doc.get_kind_display()} شماره {doc.number} ثبت شد.')


@_guard()
def acc_p_trade_doc(request, doc_id):
    doc = stockdocs.get_doc(request.user, doc_id)
    return _modal(request, 'trade_doc.html', {'doc': doc, 'lines': doc.lines.select_related('product')})


@_guard()
@require_POST
def acc_p_trade_doc_cancel(request, doc_id):
    try:
        stockdocs.cancel_doc(request.user, stockdocs.get_doc(request.user, doc_id))
    except OfficeError as exc:
        return _failed(exc)
    return _done('سند انبار ابطال شد.')


# =====================================================================================================================
# production
# =====================================================================================================================

FORMULA_COLUMNS = [('product', 'ماده اولیه', 'product'), ('qty', 'مقدار برای یک نوبت', 'qty')]


def tab_trade_production(request, year, ctx):
    ctx['formulas'] = production.formulas_for(request.user).order_by('product__code')
    ctx['runs'] = production.runs_for(request.user, year).order_by('-date', '-id')[:100]


@_guard()
def acc_p_trade_formula_new(request):
    muni = ledger.municipality_of(request.user)
    fields = [Field('product', 'محصول', 'fk', model=Product, size=2, label_of=str), Field('output_qty', 'مقدار تولید در هر نوبت', 'pct', size=2),
              Field('note', 'توضیحات', 'text', required=False, size=4, maxlength=300)]
    names = [c[0] for c in FORMULA_COLUMNS]
    kw = dict(title='فرمول ساخت جدید', action=_url('acc_p_trade_formula_new'), fields=fields, columns=FORMULA_COLUMNS,
              hint='مواد اولیه‌ای که برای یک نوبت تولید لازم است.')
    if request.method != 'POST':
        return _trade_form(request, values={'output_qty': '1'}, **kw)
    rows = _posted_rows(request.POST, names)
    try:
        data = formspec.parse(muni, fields, request.POST)
        components = _post_lines(request, muni, names)
        production.create_formula(request.user, data['product'], _num(data['output_qty']), components, data.get('note') or '')
    except OfficeError as exc:
        return _trade_form(request, values=request.POST, rows=rows, error=str(exc), status=exc.status, **kw)
    return _done('فرمول ساخت ثبت شد.')


@_guard()
@require_POST
def acc_p_trade_formula_action(request, formula_id, action):
    formula = production.get_formula(request.user, formula_id)
    try:
        if action == 'delete':
            production.delete_formula(request.user, formula)
        elif action in ('on', 'off'):
            production.set_formula_active(request.user, formula, action == 'on')
        else:
            raise Http404()
    except OfficeError as exc:
        return _failed(exc)
    return _done('انجام شد.')


def _run_modal(request, year, formula, posted=None, error=None, status=200):
    muni = ledger.municipality_of(request.user)
    p = posted or {'batches': '1', 'date': ''}
    estimate = None
    try:
        estimate = production.estimate(request.user, formula, _num(p.get('batches')) or 1,
                                       Warehouse.objects.filter(municipality=muni, pk=parse_int_or_none(p.get('warehouse')) or 0).first())
    except OfficeError:
        pass
    return _modal(request, 'trade_run.html', {'year': year, 'formula': formula, 'p': p, 'error': error, 'estimate': estimate,
                                              'warehouses': inventory.warehouses_for(request.user)}, status)


@_guard()
def acc_p_trade_run_new(request, year_id, formula_id):
    year = ledger.get_year(request.user, year_id)
    formula = production.get_formula(request.user, formula_id)
    muni = ledger.municipality_of(request.user)
    if request.method != 'POST':
        return _run_modal(request, year, formula, {'batches': '1', 'date': _today_in(year), 'warehouse': inventory.default_warehouse(muni).id})
    p = request.POST
    if p.get('preview') == '1':
        return _run_modal(request, year, formula, p)
    try:
        warehouse = Warehouse.objects.filter(municipality=muni, pk=parse_int_or_none(p.get('warehouse'))).first()
        run = production.run_production(request.user, year, formula, _num(p.get('batches')), parse_jalali(p.get('date', '')),
                                        warehouse=warehouse, note=p.get('note', ''))
    except OfficeError as exc:
        return _run_modal(request, year, formula, p, str(exc), exc.status)
    return _done(f'تولید شماره {run.number} ثبت شد.')


@_guard()
@require_POST
def acc_p_trade_run_cancel(request, run_id):
    try:
        production.cancel_run(request.user, production.get_run(request.user, run_id))
    except OfficeError as exc:
        return _failed(exc)
    return _done('تولید ابطال شد.')


# =====================================================================================================================
# consignment
# =====================================================================================================================

CONSIGN_COLUMNS = [('product', 'کالا', 'product'), ('qty', 'تعداد', 'qty')]


def tab_trade_consign(request, year, ctx):
    g = request.GET
    status = g.get('status') if g.get('status') in dict(Consignment.STATUSES) else None
    rows = []
    for c in consignment.consignments_for(request.user, status=status)[:200]:
        outstanding = sum((consignment.open_quantity(l) for l in c.lines.all()), 0)
        chip = {'open': ('باز', 'warn'), 'closed': ('تسویه‌شده', 'ok'), 'canceled': ('ابطال‌شده', 'bad')}[c.status]
        rows.append({'cells': [c.get_kind_display(), c.party.name, jalali_str(c.date), c.warehouse.name, f'{outstanding:f}'.rstrip('0').rstrip('.') or '0',
                               chip],
                     'actions': [_act('مشاهده', _url('acc_p_trade_consign', c.id))]})
    new = [] if year.is_closed else [_act('امانی داده‌شده', _url('acc_p_trade_consign_new', 'given'), 'modal', 'arrow-up-from-bracket', 'ac-btn-brand'),
                                     _act('امانی گرفته‌شده', _url('acc_p_trade_consign_new', 'taken'), 'modal', 'arrow-down-to-bracket')]
    _reg(ctx, ['نوع', 'طرف حساب', 'تاریخ', 'انبار', 'باقی‌مانده نزد طرف', 'وضعیت'], rows, empty='امانی ثبت نشده است.', icon='handshake',
         buttons=new, filters={'select': ('status', 'همه وضعیت‌ها', list(Consignment.STATUSES))})


@_guard()
def acc_p_trade_consign_new(request, kind):
    if kind not in dict(Consignment.KINDS):
        raise Http404()
    muni = ledger.municipality_of(request.user)
    fields = [Field('on', 'تاریخ', 'date', size=1), Field('party', 'طرف حساب', 'fk', model=Party, size=2, label_of=_party_name),
              Field('warehouse', 'انبار', 'fk', model=Warehouse, size=1, label_of=str, required=False),
              Field('note', 'توضیحات', 'text', required=False, size=4, maxlength=300)]
    names = [c[0] for c in CONSIGN_COLUMNS]
    kw = dict(title=dict(Consignment.KINDS)[kind], action=_url('acc_p_trade_consign_new', kind), fields=fields, columns=CONSIGN_COLUMNS,
              hint='کالای امانی‌گرفته‌شده فقط یادداشت است و جزو موجودی شما حساب نمی‌شود.' if kind == 'taken' else LOCK_NOTE)
    if request.method != 'POST':
        return _trade_form(request, values={'on': jalali_str(date.today()), 'warehouse': inventory.default_warehouse(muni).id}, **kw)
    rows = _posted_rows(request.POST, names)
    try:
        data = formspec.parse(muni, fields, request.POST)
        lines = _post_lines(request, muni, names)
        c = consignment.create_consignment(request.user, kind, data['on'], data['party'], lines, warehouse=data.get('warehouse'),
                                           note=data.get('note') or '')
    except OfficeError as exc:
        return _trade_form(request, values=request.POST, rows=rows, error=str(exc), status=exc.status, **kw)
    return _done(f'{c.get_kind_display()} ثبت شد.')


def _consign_modal(request, c, error=None, status=200, notice=None, posted=None):
    return _modal(request, 'trade_consign.html', {
        'c': c, 'lines': [(l, consignment.open_quantity(l)) for l in c.lines.select_related('product')], 'error': error, 'notice': notice,
        'p': posted or {'date': jalali_str(date.today())}}, status)


@_guard()
def acc_p_trade_consign(request, consign_id):
    return _consign_modal(request, consignment.get_consignment(request.user, consign_id))


@_guard()
@require_POST
def acc_p_trade_consign_action(request, consign_id, action):
    c = consignment.get_consignment(request.user, consign_id)
    p = request.POST
    try:
        if action == 'return':
            returns = {int(k[4:]): _num(v) for k, v in p.items() if k.startswith('ret_') and k[4:].isdigit() and _num(v)}
            consignment.give_back(request.user, c, parse_jalali(p.get('date', '')), returns)
            notice = 'برگشت ثبت شد.'
        elif action == 'close':
            consignment.close(request.user, c)
            notice = 'امانی تسویه شد.'
        elif action == 'cancel':
            consignment.cancel(request.user, c)
            notice = 'امانی ابطال شد.'
        else:
            raise Http404()
    except OfficeError as exc:
        return _consign_modal(request, c, str(exc), exc.status, posted=p)
    c.refresh_from_db()
    return _consign_modal(request, c, notice=notice)


# =====================================================================================================================
# profit and sales reports
# =====================================================================================================================

def tab_trade_profit(request, year, ctx):
    from main.accounting import builder
    date_from, err_from = _date_param(request, 'date_from')
    date_to, err_to = _date_param(request, 'date_to')
    error = err_from or err_to
    ctx.update(profit_error=error, export_query=request.GET.urlencode())
    if error:
        return
    rows, totals = inventory.profit_by_product(request.user, year, date_from=date_from, date_to=date_to)
    ctx.update(profit_rows=rows, profit_totals=totals)
    for key, dim in (('by_visitor', 'visitor'), ('by_party', 'party')):
        try:
            out = builder.build(request.user, year, 'invoices', dim, measure='total', date_from=date_from, date_to=date_to)
            ctx[key] = [(r[0], r[1]) for r in out['rows']]
        except OfficeError:
            ctx[key] = []


@_guard()
def acc_p_trade_profit_export(request, year_id):
    year = ledger.get_year(request.user, year_id)
    date_from, err_from = _date_param(request, 'date_from')
    date_to, err_to = _date_param(request, 'date_to')
    if err_from or err_to:
        return HttpResponse(err_from or err_to, status=400, content_type='text/plain; charset=utf-8')
    rows, totals = inventory.profit_by_product(request.user, year, date_from=date_from, date_to=date_to)
    wb = Workbook()
    ws = wb.active
    ws.title = 'سود کالا'
    ws.sheet_view.rightToLeft = True
    ws.append(['کد', 'کالا', 'تعداد', 'فروش خالص', 'بهای تمام‌شده', 'سود', 'حاشیه سود ٪'])
    for r in rows:
        ws.append([r['product'].code, _cell(r['product'].name), float(r['qty']), r['revenue'], r['cost'], r['profit'], r['margin']])
    ws.append(['', 'جمع', '', totals['revenue'], totals['cost'], totals['profit'], ''])
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="profit-{year.year}.xlsx"'
    wb.save(response)
    return response


BUILDERS = {'trade_pos': tab_trade_pos, 'trade_stock': tab_trade_stock, 'trade_docs': tab_trade_docs, 'trade_production': tab_trade_production,
            'trade_consign': tab_trade_consign, 'trade_profit': tab_trade_profit}
