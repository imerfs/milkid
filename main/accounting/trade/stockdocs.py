"""Stock documents: receipt, issue, transfer between warehouses, adjustment and stocktake. Each writes moves in the log."""
from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from main.accounting import ledger
from main.accounting.ledger import _locked, _own, _own_or_invalid, _text, check_unlocked, municipality_of
from main.accounting.trade import inventory
from main.accounting.trade.inventory import ZERO, qty_of
from main.models import FiscalYear, Municipality, Product, StockDoc, StockDocLine, StockMove
from main.office.errors import Conflict, Invalid

KINDS = dict(StockDoc.KINDS)


def next_number(model, muni, year, **where):
    last = model.objects.filter(municipality=muni, fiscal_year=year, **where).order_by('-number').values_list('number', flat=True).first()
    return (last or 0) + 1


def check_year_open(muni, year, on):
    _own(muni, year)
    if year.is_closed:
        raise Conflict('سال مالی بسته شده است.')
    if not (year.start_date <= on <= year.end_date):
        raise Invalid('تاریخ باید داخل سال مالی باشد.')
    check_unlocked(muni, on)


def ensure_not_negative(muni, product_ids):
    """After removing moves, no warehouse may have had a negative balance at any point."""
    for product_id in set(product_ids):
        balance = defaultdict(lambda: ZERO)
        for move in StockMove.objects.filter(municipality=muni, product_id=product_id).order_by('date', 'id').select_related('product', 'warehouse'):
            balance[move.warehouse_id] += move.qty
            if balance[move.warehouse_id] < 0:
                raise Conflict(f'با این کار موجودی «{move.product.name}» در انبار «{move.warehouse.name}» در تاریخ‌های بعد منفی می‌شود.')


def docs_for(actor, year, *, kind=None):
    muni = municipality_of(actor)
    _own(muni, year)
    qs = StockDoc.objects.filter(municipality=muni, fiscal_year=year).select_related('warehouse', 'to_warehouse')
    return qs.filter(kind=kind) if kind else qs


def get_doc(actor, pk):
    muni = municipality_of(actor)
    return _own(muni, StockDoc.objects.filter(pk=pk).select_related('warehouse', 'to_warehouse').first())


def _clean_lines(muni, kind, lines):
    if not lines:
        raise Invalid('سند باید حداقل یک ردیف داشته باشد.')
    out, seen = [], set()
    for row, item in enumerate(lines, start=1):
        product = _own_or_invalid(muni, item.get('product'), 'کالا')
        if product.id in seen:
            raise Invalid(f'ردیف {row}: کالا تکراری است.')
        seen.add(product.id)
        if kind == 'stocktake':
            counted = qty_of(item.get('counted'), f'ردیف {row}: مقدار شمارش‌شده', positive=False)
            out.append({'product': product, 'counted': counted, 'qty': ZERO, 'unit_cost': ZERO})
            continue
        qty = qty_of(item.get('qty'), f'ردیف {row}: مقدار', signed=(kind == 'adjust'))
        cost = item.get('unit_cost') or 0
        out.append({'product': product, 'qty': qty, 'counted': None, 'unit_cost': Decimal(str(cost)) if cost not in ('', None) else ZERO})
    return out


def create_doc(actor, year, kind, on, warehouse, lines, *, to_warehouse=None, note=''):
    muni = municipality_of(actor)
    if kind not in KINDS:
        raise Invalid('نوع سند انبار نامعتبر است.')
    check_year_open(muni, year, on)
    warehouse = _own_or_invalid(muni, warehouse, 'انبار')
    if kind == 'transfer':
        to_warehouse = _own_or_invalid(muni, to_warehouse, 'انبار مقصد')
        if to_warehouse.id == warehouse.id:
            raise Invalid('انبار مبدأ و مقصد باید فرق داشته باشند.')
    else:
        to_warehouse = None
    cleaned = _clean_lines(muni, kind, lines)
    note = _text(note, 'توضیحات', required=False)
    with transaction.atomic():
        _locked(Municipality, muni.id)
        doc = StockDoc.objects.create(municipality=muni, fiscal_year=year, kind=kind, number=next_number(StockDoc, muni, year, kind=kind),
                                      date=on, warehouse=warehouse, to_warehouse=to_warehouse, note=note, created_by=actor)
        for row, item in enumerate(cleaned, start=1):
            product = item['product']
            avg = inventory.current_avg(muni, product, upto=on)
            if kind == 'stocktake':
                book = inventory.stock_in(muni, product, warehouse, upto=on)
                diff = item['counted'] - book
                line = StockDocLine.objects.create(doc=doc, row=row, product=product, qty=diff, unit_cost=avg, counted=item['counted'])
                if diff > 0:
                    inventory.add_move(muni, product, warehouse, on, diff, 'doc', unit_cost=avg, doc=doc)
                elif diff < 0:
                    inventory.add_move(muni, product, warehouse, on, diff, 'doc', doc=doc)
                continue
            qty, cost = item['qty'], item['unit_cost']
            StockDocLine.objects.create(doc=doc, row=row, product=product, qty=qty, unit_cost=cost)
            if kind == 'receipt':
                inventory.add_move(muni, product, warehouse, on, qty, 'doc', unit_cost=cost, doc=doc)
            elif kind == 'issue':
                inventory.check_available(muni, product, warehouse, qty)
                inventory.add_move(muni, product, warehouse, on, -qty, 'doc', doc=doc)
            elif kind == 'transfer':
                inventory.check_available(muni, product, warehouse, qty)
                inventory.add_move(muni, product, warehouse, on, -qty, 'doc', doc=doc)
                inventory.add_move(muni, product, to_warehouse, on, qty, 'doc', unit_cost=avg, doc=doc)
            else:                                                                  # adjust: signed
                if qty > 0:
                    inventory.add_move(muni, product, warehouse, on, qty, 'doc', unit_cost=cost or avg, doc=doc)
                else:
                    inventory.check_available(muni, product, warehouse, -qty)
                    inventory.add_move(muni, product, warehouse, on, qty, 'doc', doc=doc)
        ensure_not_negative(muni, [i['product'].id for i in cleaned])
    return doc


def cancel_doc(actor, doc):
    muni = municipality_of(actor)
    _own(muni, doc)
    with transaction.atomic():
        doc = _locked(StockDoc, doc.pk)
        if doc.canceled_at is not None:
            raise Conflict('این سند قبلاً ابطال شده است.')
        if doc.fiscal_year.is_closed:
            raise Conflict('سال مالی بسته شده است.')
        check_unlocked(muni, doc.date)
        products = list(doc.moves.values_list('product_id', flat=True))
        doc.moves.all().delete()
        doc.canceled_at = timezone.now()
        doc.save(update_fields=['canceled_at'])
        ensure_not_negative(muni, products)
    return doc


def opening_receipt(actor, product, qty, unit_cost, on=None):
    """Opening stock of a new product as an ordinary receipt in the year that contains ``on`` (default today, else the latest year)."""
    muni = municipality_of(actor)
    today = timezone.localdate()
    year = (FiscalYear.objects.filter(municipality=muni, start_date__lte=on or today, end_date__gte=on or today).first()
            or FiscalYear.objects.filter(municipality=muni).order_by('-year').first())
    if year is None:
        raise Conflict('برای ثبت موجودی اول دوره ابتدا یک سال مالی باز کنید.')
    on = on or (today if year.start_date <= today <= year.end_date else year.start_date)
    return create_doc(actor, year, 'receipt', on, inventory.default_warehouse(muni),
                      [{'product': product, 'qty': qty, 'unit_cost': unit_cost}], note='موجودی اول دوره')
