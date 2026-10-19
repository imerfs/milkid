"""Bills of materials (formulas) and production runs.

A run consumes the components of the formula (at their weighted-average cost) and produces the output product at the cost of
those components, so the output enters stock already valued.
"""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from main.accounting.ledger import _locked, _own, _own_or_invalid, _text, check_unlocked, municipality_of
from main.accounting.trade import inventory, stockdocs
from main.accounting.trade.inventory import ZERO, qty_of
from main.models import Formula, FormulaLine, Municipality, ProductionRun
from main.office.errors import Conflict, Invalid


def formulas_for(actor):
    muni = municipality_of(actor)
    return Formula.objects.filter(municipality=muni).select_related('product').prefetch_related('lines__product')


def get_formula(actor, pk):
    muni = municipality_of(actor)
    return _own(muni, Formula.objects.filter(pk=pk).select_related('product').first())


def create_formula(actor, product, output_qty, components, note=''):
    muni = municipality_of(actor)
    product = _own_or_invalid(muni, product, 'کالای تولیدی')
    output_qty = qty_of(output_qty, 'مقدار تولید')
    if not components:
        raise Invalid('فرمول باید حداقل یک ماده اولیه داشته باشد.')
    cleaned, seen = [], set()
    for row, item in enumerate(components, start=1):
        component = _own_or_invalid(muni, item.get('product'), 'ماده اولیه')
        if component.id == product.id:
            raise Invalid(f'ردیف {row}: محصول نمی‌تواند ماده اولیه خودش باشد.')
        if component.id in seen:
            raise Invalid(f'ردیف {row}: ماده اولیه تکراری است.')
        seen.add(component.id)
        cleaned.append((component, qty_of(item.get('qty'), f'ردیف {row}: مقدار')))
    with transaction.atomic():
        formula = Formula.objects.create(municipality=muni, product=product, output_qty=output_qty,
                                         note=_text(note, 'توضیحات', required=False))
        FormulaLine.objects.bulk_create([FormulaLine(formula=formula, product=p, qty=q) for p, q in cleaned])
    return formula


def set_formula_active(actor, formula, active):
    _own(municipality_of(actor), formula)
    formula.is_active = bool(active)
    formula.save(update_fields=['is_active'])


def delete_formula(actor, formula):
    _own(municipality_of(actor), formula)
    if formula.runs.exists():
        raise Conflict('از این فرمول تولید انجام شده است؛ آن را غیرفعال کنید.')
    formula.delete()


def estimate(actor, formula, batches, warehouse=None, *, on=None):
    """What a run would need and cost, and how many whole batches the stock allows."""
    muni = municipality_of(actor)
    _own(muni, formula)
    batches = qty_of(batches, 'تعداد دفعات')
    warehouse = _own_or_invalid(muni, warehouse, 'انبار') if warehouse is not None else inventory.default_warehouse(muni)
    rows, cost, possible = [], ZERO, None
    for line in formula.lines.select_related('product'):
        need = line.qty * batches
        have = inventory.stock_in(muni, line.product, warehouse)
        avg = inventory.current_avg(muni, line.product, upto=on)
        cost += need * avg
        rows.append({'product': line.product, 'need': need, 'have': have, 'short': max(need - have, ZERO), 'avg': avg})
        fits = int(have // line.qty) if line.qty else 0
        possible = fits if possible is None else min(possible, fits)
    output = formula.output_qty * batches
    return {'rows': rows, 'output': output, 'cost': inventory.rial(cost), 'unit_cost': (cost / output) if output else ZERO,
            'possible_batches': possible or 0, 'short': any(r['short'] > 0 for r in rows)}


def runs_for(actor, year):
    muni = municipality_of(actor)
    _own(muni, year)
    return ProductionRun.objects.filter(municipality=muni, fiscal_year=year).select_related('formula__product', 'warehouse')


def get_run(actor, pk):
    muni = municipality_of(actor)
    return _own(muni, ProductionRun.objects.filter(pk=pk).select_related('formula__product', 'warehouse', 'fiscal_year').first())


def run_production(actor, year, formula, batches, on, *, warehouse=None, note=''):
    muni = municipality_of(actor)
    stockdocs.check_year_open(muni, year, on)
    _own(muni, formula)
    if not formula.is_active:
        raise Conflict('این فرمول غیرفعال است.')
    batches = qty_of(batches, 'تعداد دفعات')
    warehouse = _own_or_invalid(muni, warehouse, 'انبار') if warehouse is not None else inventory.default_warehouse(muni)
    with transaction.atomic():
        _locked(Municipality, muni.id)
        lines = list(formula.lines.select_related('product'))
        cost = ZERO
        for line in lines:
            inventory.check_available(muni, line.product, warehouse, line.qty * batches)
            cost += line.qty * batches * inventory.current_avg(muni, line.product, upto=on)
        output = formula.output_qty * batches
        unit_cost = cost / output
        run = ProductionRun.objects.create(
            municipality=muni, fiscal_year=year, number=stockdocs.next_number(ProductionRun, muni, year), formula=formula, batches=batches,
            date=on, warehouse=warehouse, unit_cost=unit_cost, note=_text(note, 'توضیحات', required=False), created_by=actor)
        for line in lines:
            inventory.add_move(muni, line.product, warehouse, on, -(line.qty * batches), 'production_out', production=run)
        inventory.add_move(muni, formula.product, warehouse, on, output, 'production_in', unit_cost=unit_cost, production=run)
    return run


def cancel_run(actor, run):
    muni = municipality_of(actor)
    _own(muni, run)
    with transaction.atomic():
        run = _locked(ProductionRun, run.pk)
        if run.canceled_at is not None:
            raise Conflict('این تولید قبلاً ابطال شده است.')
        if run.fiscal_year.is_closed:
            raise Conflict('سال مالی بسته شده است.')
        check_unlocked(muni, run.date)
        products = list(run.moves.values_list('product_id', flat=True))
        run.moves.all().delete()
        run.canceled_at = timezone.now()
        run.save(update_fields=['canceled_at'])
        stockdocs.ensure_not_negative(muni, products)
    return run
