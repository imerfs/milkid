"""Stock movements: the one place that writes to the stock log.

Callers say what happened (receive, issue, transfer, reverse) and never deal with availability checks, series (lots) or
the no-negative-balance rule themselves:

* ``receive`` writes an inflow that keeps its series and expiry.
* ``issue`` checks the quantity is there (unless the caller allows a shortage), then takes it from the series that expire
  first (expired ones last, untracked stock after the series) and writes one move per series taken.
* ``transfer`` is an issue from one warehouse and a receipt of the same series in another.
* ``reverse`` removes the moves of a cancelled document and refuses when later movements would then have gone negative.

Quantities are positive; the log stores them signed. Callers have already checked ownership, dates and fiscal years.
"""
from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from main.models import StockMove
from main.office.errors import Conflict

ZERO = Decimal('0')


def stock_in(muni, product, warehouse, *, upto=None):
    """Quantity of a product in one warehouse."""
    qs = StockMove.objects.filter(municipality=muni, product=product, warehouse=warehouse)
    if upto:
        qs = qs.filter(date__lte=upto)
    return qs.aggregate(s=Sum('qty'))['s'] or ZERO


def lot_balances(muni, product=None, *, warehouse=None, upto=None):
    """Quantity per (product, warehouse, series, expiry), positive balances only; untracked stock has a blank series."""
    qs = StockMove.objects.filter(municipality=muni)
    if product is not None:
        qs = qs.filter(product=product)
    if warehouse is not None:
        qs = qs.filter(warehouse=warehouse)
    if upto:
        qs = qs.filter(date__lte=upto)
    rows = qs.values('product_id', 'warehouse_id', 'lot', 'expiry').annotate(q=Sum('qty'))
    return {(r['product_id'], r['warehouse_id'], r['lot'], r['expiry']): r['q'] for r in rows if r['q'] and r['q'] > 0}


def _allocate(muni, product, warehouse, qty, on):
    """``[(lot, expiry, qty)]`` an outflow takes from; what the series cannot cover goes out untracked (a permitted shortage)."""
    balances = [(lot, expiry, q) for (_, _, lot, expiry), q in lot_balances(muni, product, warehouse=warehouse).items() if lot or expiry]
    balances.sort(key=lambda b: (b[1] is not None and b[1] < on, b[1] is None, b[1] or on, b[0]))
    left, out = qty, []
    for lot, expiry, have in balances:
        take = min(have, left)
        if take > 0:
            out.append((lot, expiry, take))
            left -= take
        if left <= 0:
            break
    if left > 0:
        out.append(('', None, left))
    return out


def receive(muni, product, warehouse, on, qty, kind, *, unit_cost=ZERO, lot='', expiry=None, **links):
    """Write an inflow of ``qty`` (positive). Returns the moves written (one)."""
    return [StockMove.objects.create(municipality=muni, product=product, warehouse=warehouse, date=on, qty=qty, unit_cost=unit_cost,
                                     kind=kind, lot=lot or '', expiry=expiry, **links)]


def require_available(muni, product, warehouse, qty):
    """Refuse (Conflict) when the warehouse holds less than ``qty``."""
    have = stock_in(muni, product, warehouse)
    if have < qty:
        raise Conflict(f'موجودی «{product.name}» در انبار «{warehouse.name}» کافی نیست (موجود {Decimal(have).normalize():f}، لازم {Decimal(qty).normalize():f}).')


def issue(muni, product, warehouse, on, qty, kind, *, allow_shortage=False, **links):
    """Write an outflow of ``qty`` (positive), split over the series it takes from. Returns the moves written."""
    if not allow_shortage:
        require_available(muni, product, warehouse, qty)
    return [StockMove.objects.create(municipality=muni, product=product, warehouse=warehouse, date=on, qty=-part, kind=kind,
                                     lot=lot, expiry=expiry, **links)
            for lot, expiry, part in _allocate(muni, product, warehouse, qty, on)]


def transfer(muni, product, source, target, on, qty, kind, *, unit_cost=ZERO, **links):
    """Move ``qty`` between warehouses; each series arrives with its own expiry."""
    return [receive(muni, product, target, on, -taken.qty, kind, unit_cost=unit_cost, lot=taken.lot, expiry=taken.expiry, **links)[0]
            for taken in issue(muni, product, source, on, qty, kind, **links)]


def guard_not_negative(muni, product_ids):
    """After removing moves, no warehouse may have had a negative balance at any point."""
    for product_id in set(product_ids):
        balance = defaultdict(lambda: ZERO)
        for move in StockMove.objects.filter(municipality=muni, product_id=product_id).order_by('date', 'id').select_related('product', 'warehouse'):
            balance[move.warehouse_id] += move.qty
            if balance[move.warehouse_id] < 0:
                raise Conflict(f'با این کار موجودی «{move.product.name}» در انبار «{move.warehouse.name}» در تاریخ‌های بعد منفی می‌شود.')


def reverse(muni, moves):
    """Remove the moves of a cancelled document (a queryset) and make sure nothing later went negative."""
    with transaction.atomic():
        products = list(moves.values_list('product_id', flat=True))
        moves.delete()
        guard_not_negative(muni, products)       # raising rolls the removal back
