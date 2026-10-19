"""Consignment (امانی). Goods *given* leave our stock until returned; goods *taken* are a memo only (they are not our stock)."""
from django.db import transaction

from main.accounting.ledger import _locked, _own, _own_or_invalid, _text, check_unlocked, municipality_of
from main.accounting.trade import inventory, stockdocs
from main.accounting.trade.inventory import ZERO, qty_of
from main.models import Consignment, ConsignmentLine
from main.office.errors import Conflict, Invalid


def consignments_for(actor, *, status=None):
    muni = municipality_of(actor)
    qs = Consignment.objects.filter(municipality=muni).select_related('party', 'warehouse').prefetch_related('lines__product')
    return qs.filter(status=status) if status else qs


def get_consignment(actor, pk):
    muni = municipality_of(actor)
    return _own(muni, Consignment.objects.filter(pk=pk).select_related('party', 'warehouse').first())


def open_quantity(line):
    return line.qty - line.returned


def create_consignment(actor, kind, on, party, lines, *, warehouse=None, note=''):
    muni = municipality_of(actor)
    if kind not in dict(Consignment.KINDS):
        raise Invalid('نوع امانی نامعتبر است.')
    check_unlocked(muni, on)
    party = _own_or_invalid(muni, party, 'طرف حساب')
    warehouse = _own_or_invalid(muni, warehouse, 'انبار') if warehouse is not None else inventory.default_warehouse(muni)
    if not lines:
        raise Invalid('امانی باید حداقل یک ردیف داشته باشد.')
    cleaned, seen = [], set()
    for row, item in enumerate(lines, start=1):
        product = _own_or_invalid(muni, item.get('product'), 'کالا')
        if product.id in seen:
            raise Invalid(f'ردیف {row}: کالا تکراری است.')
        seen.add(product.id)
        cleaned.append((product, qty_of(item.get('qty'), f'ردیف {row}: مقدار')))
    with transaction.atomic():
        consignment = Consignment.objects.create(municipality=muni, kind=kind, party=party, warehouse=warehouse, date=on,
                                                 note=_text(note, 'توضیحات', required=False), created_by=actor)
        for product, qty in cleaned:
            ConsignmentLine.objects.create(consignment=consignment, product=product, qty=qty)
            if kind == 'given':
                inventory.check_available(muni, product, warehouse, qty)
                inventory.add_move(muni, product, warehouse, on, -qty, 'consignment', consignment=consignment)
        stockdocs.ensure_not_negative(muni, [p.id for p, _ in cleaned])
    return consignment


def give_back(actor, consignment, on, returns):
    """Record returned quantities: ``returns`` is ``{line_id: qty}``. Goods we gave come back into stock at the average cost."""
    muni = municipality_of(actor)
    _own(muni, consignment)
    check_unlocked(muni, on)
    with transaction.atomic():
        consignment = _locked(Consignment, consignment.pk)
        if consignment.status != 'open':
            raise Conflict('این امانی باز نیست.')
        if on < consignment.date:
            raise Invalid('تاریخ برگشت نمی‌تواند پیش از تاریخ امانی باشد.')
        any_return = False
        for line in consignment.lines.select_related('product'):
            raw = returns.get(line.id)
            if raw in (None, '', 0, '0'):
                continue
            qty = qty_of(raw, f'مقدار برگشتی «{line.product.name}»')
            if qty > open_quantity(line):
                raise Conflict(f'برگشت «{line.product.name}» از مقدار باقی‌مانده بیشتر است.')
            line.returned += qty
            line.save(update_fields=['returned'])
            any_return = True
            if consignment.kind == 'given':
                inventory.add_move(muni, line.product, consignment.warehouse, on, qty, 'consignment',
                                   unit_cost=inventory.current_avg(muni, line.product, upto=on), consignment=consignment)
        if not any_return:
            raise Invalid('مقدار برگشتی را وارد کنید.')
        if all(open_quantity(l) == ZERO for l in consignment.lines.all()):
            consignment.status = 'closed'
            consignment.save(update_fields=['status'])
    return consignment


def close(actor, consignment):
    """Settle without returning the rest (the goods were sold; issue the sale invoice separately)."""
    _own(municipality_of(actor), consignment)
    if consignment.status != 'open':
        raise Conflict('این امانی باز نیست.')
    consignment.status = 'closed'
    consignment.save(update_fields=['status'])


def cancel(actor, consignment):
    muni = municipality_of(actor)
    _own(muni, consignment)
    check_unlocked(muni, consignment.date)
    with transaction.atomic():
        consignment = _locked(Consignment, consignment.pk)
        if consignment.status == 'canceled':
            raise Conflict('این امانی قبلاً ابطال شده است.')
        if any(l.returned for l in consignment.lines.all()):
            raise Conflict('از این امانی کالا برگشت خورده است؛ ابطال ممکن نیست.')
        products = list(consignment.moves.values_list('product_id', flat=True))
        consignment.moves.all().delete()
        consignment.status = 'canceled'
        consignment.save(update_fields=['status'])
        stockdocs.ensure_not_negative(muni, products)
    return consignment
