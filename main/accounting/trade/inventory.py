"""Products, warehouses and the stock-move log, with weighted-average valuation.

Every change of stock is a ``StockMove`` row (positive in, negative out). Quantity, average cost and value are *derived* by
walking a product's moves in (date, id) order: an inflow re-averages the cost, an outflow leaves at the current average.
So a back-dated document changes later figures instead of being refused, and nothing can drift from the log.
"""
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from main.accounting.ledger import _amount, _own, _text, municipality_of
from main.accounting.trade.movements import lot_balances, stock_in   # noqa: F401  (stock_in is re-exported: callers and tests read it here)
from main.models import Product, StockMove, Warehouse
from main.office.errors import Conflict, Invalid

ZERO = Decimal(0)
QTY_PLACES = Decimal('0.001')
MAX_QTY = Decimal(10) ** 11


def qty_of(value, label='مقدار', *, positive=True, signed=False):
    """A quantity with at most three decimals; ``signed`` allows negatives (stock adjustments)."""
    if value is None or isinstance(value, bool) or value == '':
        raise Invalid(f'{label} را وارد کنید.')
    try:
        number = Decimal(str(value).replace(',', '').replace('٬', '').strip())
    except Exception:
        raise Invalid(f'{label} نامعتبر است.')
    if not number.is_finite() or number != number.quantize(QTY_PLACES):
        raise Invalid(f'{label} حداکثر سه رقم اعشار دارد.')
    if abs(number) >= MAX_QTY:
        raise Invalid(f'{label} خارج از محدوده است.')
    if not signed and number < 0:
        raise Invalid(f'{label} نمی‌تواند منفی باشد.')
    if positive and number == 0:
        raise Invalid(f'{label} باید بیشتر از صفر باشد.')
    return number


def rial(value):
    return int(Decimal(value).quantize(Decimal(1), rounding=ROUND_HALF_UP))


# ---------- warehouses ----------

def default_warehouse(muni):
    """The municipality's default warehouse (created on first use)."""
    warehouse = Warehouse.objects.filter(municipality=muni, is_default=True).first() or Warehouse.objects.filter(municipality=muni).first()
    if warehouse is None:
        warehouse = Warehouse.objects.create(municipality=muni, code='1', name='انبار اصلی', is_default=True)
    return warehouse


def warehouses_for(actor):
    muni = municipality_of(actor)
    default_warehouse(muni)
    return Warehouse.objects.filter(municipality=muni)


def get_warehouse(actor, pk):
    muni = municipality_of(actor)
    return _own(muni, Warehouse.objects.filter(pk=pk).first())


def create_warehouse(actor, *, code, name, is_default=False):
    muni = municipality_of(actor)
    code, name = _text(code, 'کد انبار'), _text(name, 'نام انبار')
    if len(code) > 20 or len(name) > 100:
        raise Invalid('کد یا نام انبار بیش از حد بلند است.')
    if Warehouse.objects.filter(municipality=muni, code=code).exists():
        raise Conflict('انباری با این کد هست.')
    with transaction.atomic():
        if is_default:
            Warehouse.objects.filter(municipality=muni).update(is_default=False)
        return Warehouse.objects.create(municipality=muni, code=code, name=name,
                                        is_default=is_default or not Warehouse.objects.filter(municipality=muni).exists())


# ---------- products ----------

def products_for(actor, *, active=None):
    muni = municipality_of(actor)
    qs = Product.objects.filter(municipality=muni)
    return qs if active is None else qs.filter(is_active=active)


def get_product(actor, pk):
    muni = municipality_of(actor)
    return _own(muni, Product.objects.filter(pk=pk).first())


def _product_values(values):
    out = {}
    out['code'] = _text(values['code'], 'کد کالا')
    out['name'] = _text(values['name'], 'نام کالا')
    out['unit'] = _text(values.get('unit') or 'عدد', 'واحد')
    out['category'] = _text(values.get('category'), 'دسته', required=False)
    out['barcode'] = _text(values.get('barcode'), 'بارکد', required=False)
    for key, limit in (('code', 30), ('name', 200), ('unit', 30), ('category', 100), ('barcode', 40)):
        if len(out[key]) > limit:
            raise Invalid(f'{key} بیش از حد بلند است.')
    out['buy_price'] = _amount(values.get('buy_price') or 0)
    out['sell_price'] = _amount(values.get('sell_price') or 0)
    out['min_stock'] = qty_of(values.get('min_stock') or 0, 'حداقل موجودی', positive=False)
    return out


def create_product(actor, *, opening_qty=0, opening_cost=0, opening_date=None, **values):
    """Create a product; an opening quantity becomes a receipt document so the stock log stays the only source of truth."""
    muni = municipality_of(actor)
    data = _product_values(values)
    if Product.objects.filter(municipality=muni, code=data['code']).exists():
        raise Conflict('کالایی با این کد ثبت شده است.')
    if data['barcode'] and Product.objects.filter(municipality=muni, barcode=data['barcode']).exists():
        raise Conflict('کالای دیگری این بارکد را دارد.')
    opening = qty_of(opening_qty or 0, 'موجودی اول دوره', positive=False)
    with transaction.atomic():
        product = Product.objects.create(municipality=muni, **data)
        if opening > 0:
            from main.accounting.trade import stockdocs
            stockdocs.opening_receipt(actor, product, opening, _amount(opening_cost or 0), opening_date)
    return product


def update_product(actor, product, **values):
    muni = municipality_of(actor)
    _own(muni, product)
    data = _product_values(values)
    data['is_active'] = bool(values.get('is_active', True))
    if Product.objects.filter(municipality=muni, code=data['code']).exclude(pk=product.pk).exists():
        raise Conflict('کالای دیگری این کد را دارد.')
    if data['barcode'] and Product.objects.filter(municipality=muni, barcode=data['barcode']).exclude(pk=product.pk).exists():
        raise Conflict('کالای دیگری این بارکد را دارد.')
    for name, value in data.items():
        setattr(product, name, value)
    product.save()
    return product


def update_prices(actor, items):
    """After a purchase: the new buying price and, when given, the selling price of each product ``(product, buy, sell)``."""
    muni = municipality_of(actor)
    for product, buy, sell in items:
        _own(muni, product)
        if buy:
            product.buy_price = buy
        if sell:
            product.sell_price = sell
        product.save(update_fields=['buy_price', 'sell_price'])


def delete_product(actor, product):
    muni = municipality_of(actor)
    _own(muni, product)
    if product.moves.exists() or product.invoice_lines.exists() or product.formulas.exists() or product.used_in.exists() \
            or product.consignment_lines.exists() or product.stock_doc_lines.exists():
        raise Conflict('کالا گردش دارد؛ به‌جای حذف، آن را غیرفعال کنید.')
    product.delete()


def find_product(actor, text):
    """By barcode (exact) or code (exact), then by name (contains): what the point of sale types or scans."""
    muni = municipality_of(actor)
    text = (text or '').strip()
    if not text:
        return None
    qs = Product.objects.filter(municipality=muni, is_active=True)
    return qs.filter(barcode=text).first() or qs.filter(code=text).first() or qs.filter(name__icontains=text).first()


# ---------- the move log ----------

def walk(moves):
    """Yield one dict per move in order: ``move, qty_after, avg, value, out_cost`` (out_cost: average the outflow left at)."""
    qty, avg = ZERO, ZERO
    for move in moves:
        out_cost = None
        if move.qty > 0:
            avg = move.unit_cost if qty <= 0 else (qty * avg + move.qty * move.unit_cost) / (qty + move.qty)
            qty += move.qty
        else:
            out_cost = avg
            qty += move.qty
        yield {'move': move, 'qty_after': qty, 'avg': avg, 'value': qty * avg if qty > 0 else ZERO, 'out_cost': out_cost}


def moves_of(muni, product, *, upto=None):
    qs = StockMove.objects.filter(municipality=muni, product=product).select_related('warehouse').order_by('date', 'id')
    return qs.filter(date__lte=upto) if upto else qs


def valuation(muni, product, *, upto=None):
    """Total quantity (all warehouses), weighted-average unit cost and value of a product."""
    last = None
    for last in walk(moves_of(muni, product, upto=upto)):
        pass
    if last is None:
        return {'qty': ZERO, 'avg': ZERO, 'value': ZERO}
    return {'qty': last['qty_after'], 'avg': last['avg'], 'value': last['value']}


def current_avg(muni, product, *, upto=None):
    return valuation(muni, product, upto=upto)['avg']


def lot_report(actor, *, warehouse=None, soon_days=30, today=None):
    """Series in stock, soonest expiry first: product, series, expiry, quantity and an expired / expiring-soon flag."""
    from datetime import timedelta
    from django.utils import timezone
    muni = municipality_of(actor)
    if warehouse is not None:
        _own(muni, warehouse)
    today = today or timezone.localdate()
    products = {p.id: p for p in Product.objects.filter(municipality=muni)}
    merged = defaultdict(lambda: ZERO)
    for (pid, _, lot, expiry), q in lot_balances(muni, warehouse=warehouse).items():
        if lot or expiry:
            merged[(pid, lot, expiry)] += q
    rows = []
    for (pid, lot, expiry), q in merged.items():
        state = None
        if expiry is not None:
            state = 'expired' if expiry < today else ('soon' if expiry <= today + timedelta(days=soon_days) else None)
        rows.append({'product': products[pid], 'lot': lot, 'expiry': expiry, 'qty': q, 'state': state})
    rows.sort(key=lambda r: (r['expiry'] is None, r['expiry'] or today, r['product'].code, r['lot']))
    return rows


def nearest_expiry(muni, warehouse=None):
    """Earliest expiry among the series of each product that still have stock: ``{product_id: date}``."""
    out = {}
    for (pid, _, _, expiry) in lot_balances(muni, warehouse=warehouse):
        if expiry is not None and (pid not in out or expiry < out[pid]):
            out[pid] = expiry
    return out


def stock_report(actor, *, warehouse=None, upto=None, low_only=False):
    """One row per product: quantity (in ``warehouse`` or in total), average cost, value, minimum and a shortage flag."""
    muni = municipality_of(actor)
    if warehouse is not None:
        _own(muni, warehouse)
    moves = StockMove.objects.filter(municipality=muni).order_by('product_id', 'date', 'id')
    if upto:
        moves = moves.filter(date__lte=upto)
    by_product = defaultdict(list)
    for move in moves:
        by_product[move.product_id].append(move)
    rows = []
    for product in Product.objects.filter(municipality=muni).order_by('code'):
        rows_for = list(walk(by_product.get(product.id, [])))
        total_qty = rows_for[-1]['qty_after'] if rows_for else ZERO
        avg = rows_for[-1]['avg'] if rows_for else ZERO
        qty = (sum((m.qty for m in by_product.get(product.id, []) if m.warehouse_id == warehouse.id), ZERO)
               if warehouse is not None else total_qty)
        low = qty < product.min_stock and product.is_active
        if low_only and not low:
            continue
        rows.append({'product': product, 'qty': qty, 'avg': avg, 'value': rial(qty * avg) if qty > 0 else 0,
                     'min_stock': product.min_stock, 'low': low})
    return rows


def kardex(actor, product, *, warehouse=None, date_from=None, date_to=None):
    """Movements of one product with the running quantity and value (valuation always over all warehouses)."""
    muni = municipality_of(actor)
    _own(muni, product)
    if warehouse is not None:
        _own(muni, warehouse)
    out, running = [], ZERO
    for row in walk(moves_of(muni, product, upto=date_to)):
        move = row['move']
        if warehouse is not None and move.warehouse_id != warehouse.id:
            continue
        if warehouse is not None:
            running += move.qty
        else:
            running = row['qty_after']
        if date_from and move.date < date_from:
            continue
        out.append({'move': move, 'in': move.qty if move.qty > 0 else ZERO, 'out': -move.qty if move.qty < 0 else ZERO,
                    'balance': running, 'avg': row['avg'], 'value': rial(row['value'])})
    return out


def profit_by_product(actor, year, *, date_from=None, date_to=None):
    """Gross profit per product from issued sale and sale-return invoices: revenue (net of discounts, invoice discount spread
    pro rata), cost (the weighted average the goods left at) and margin."""
    from main.models import InvoiceLine
    muni = municipality_of(actor)
    _own(muni, year)
    lines = InvoiceLine.objects.filter(invoice__municipality=muni, invoice__fiscal_year=year, invoice__status='issued',
                                       invoice__kind__in=('sale', 'sale_return')).select_related('invoice', 'product')
    if date_from:
        lines = lines.filter(invoice__date__gte=date_from)
    if date_to:
        lines = lines.filter(invoice__date__lte=date_to)
    line_ids = set(lines.values_list('id', flat=True))
    out_cost_of_line, cost_in_of_line = {}, {}
    product_ids = {line.product_id for line in lines}
    for product in Product.objects.filter(municipality=muni, pk__in=product_ids):
        for row in walk(moves_of(muni, product)):
            line_id = row['move'].invoice_line_id
            if line_id in line_ids:
                if row['out_cost'] is not None:
                    out_cost_of_line[line_id] = out_cost_of_line.get(line_id, ZERO) + (-row['move'].qty) * row['out_cost']
                else:
                    cost_in_of_line[line_id] = cost_in_of_line.get(line_id, ZERO) + row['move'].qty * row['move'].unit_cost
    result = {}
    for line in lines:
        invoice = line.invoice
        share = (invoice.discount * line.total / invoice.subtotal) if invoice.subtotal else ZERO
        sign = 1 if invoice.kind == 'sale' else -1
        row = result.setdefault(line.product_id, {'product': line.product, 'qty': ZERO, 'revenue': ZERO, 'cost': ZERO})
        row['qty'] += sign * line.qty
        row['revenue'] += sign * (line.total - share)
        row['cost'] += out_cost_of_line.get(line.id, ZERO) if sign == 1 else -cost_in_of_line.get(line.id, ZERO)
    rows = []
    for row in sorted(result.values(), key=lambda r: r['product'].code):
        revenue, cost = rial(row['revenue']), rial(row['cost'])
        rows.append({'product': row['product'], 'qty': row['qty'], 'revenue': revenue, 'cost': cost, 'profit': revenue - cost,
                     'margin': round((revenue - cost) * 100 / revenue) if revenue else None})
    totals = {'revenue': sum(r['revenue'] for r in rows), 'cost': sum(r['cost'] for r in rows)}
    totals['profit'] = totals['revenue'] - totals['cost']
    return rows, totals
