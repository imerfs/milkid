"""Invoices: sale, purchase, returns, proforma and order; payments, conversion of a proforma/order, and the quick (cash) sale.

An issued sale or purchase moves stock (proforma and order never do) and may be posted to the ledger as a temporary voucher
(see posting.py). Numbers restart every fiscal year, per kind.
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from main.accounting import ledger
from main.accounting.ledger import _amount, _locked, _own, _own_or_invalid, _text, check_unlocked, municipality_of
from main.accounting.trade import inventory, stockdocs
from main.accounting.trade.inventory import ZERO, qty_of, rial
from main.models import Invoice, InvoiceLine, InvoicePayment, Municipality, Party, StockMove, TradeSettings
from main.office.errors import Conflict, Invalid

KINDS = dict(Invoice.KINDS)
STOCK_KINDS = tuple(Invoice.STOCK_SIGN)
PAYABLE_KINDS = ('sale', 'purchase')
CASH_CUSTOMER = 'مشتری نقدی'


def settings_of(actor):
    muni = municipality_of(actor)
    return TradeSettings.objects.get_or_create(municipality=muni)[0]


def update_settings(actor, **values):
    muni = municipality_of(actor)
    config = settings_of(actor)
    for name in ('receivable_account', 'payable_account', 'sales_account', 'inventory_account', 'cogs_account', 'tax_account'):
        account = values.get(name)
        if account is not None:
            account = _own_or_invalid(muni, account, name)
            if not account.is_postable:
                raise Invalid('حساب انتخاب‌شده قابل ثبت سند نیست.')
        setattr(config, name, account)
    try:
        vat = Decimal(str(values.get('vat_percent') or 0))
    except Exception:
        raise Invalid('درصد مالیات نامعتبر است.')
    if not (0 <= vat <= 100):
        raise Invalid('درصد مالیات باید بین ۰ تا ۱۰۰ باشد.')
    config.vat_percent = vat
    config.allow_shortage = bool(values.get('allow_shortage'))
    config.save()
    return config


def invoices_for(actor, year, *, kind=None):
    muni = municipality_of(actor)
    _own(muni, year)
    qs = Invoice.objects.filter(municipality=muni, fiscal_year=year).select_related('party', 'warehouse')
    return qs.filter(kind=kind) if kind else qs


def get_invoice(actor, pk):
    muni = municipality_of(actor)
    return _own(muni, Invoice.objects.filter(pk=pk).select_related('party', 'warehouse', 'fiscal_year').first())


def paid_of(invoice):
    return invoice.payments.aggregate(s=Sum('amount'))['s'] or ZERO


def remaining_of(invoice):
    return invoice.total - paid_of(invoice)


def cash_customer(muni):
    party = Party.objects.filter(municipality=muni, name=CASH_CUSTOMER, national_id='').first()
    return party or Party.objects.create(municipality=muni, name=CASH_CUSTOMER)


def _clean_lines(muni, lines):
    if not lines:
        raise Invalid('فاکتور باید حداقل یک ردیف داشته باشد.')
    cleaned, seen = [], set()
    for row, item in enumerate(lines, start=1):
        product = _own_or_invalid(muni, item.get('product'), 'کالا')
        if not product.is_active:
            raise Invalid(f'ردیف {row}: کالای «{product.name}» غیرفعال است.')
        if product.id in seen:
            raise Invalid(f'ردیف {row}: کالا تکراری است؛ مقدار را در یک ردیف جمع کنید.')
        seen.add(product.id)
        qty = qty_of(item.get('qty'), f'ردیف {row}: تعداد')
        price = _amount(item.get('unit_price') if item.get('unit_price') not in (None, '') else 0)
        discount = _amount(item.get('discount') or 0)
        total = rial(qty * price) - discount
        if total < 0:
            raise Invalid(f'ردیف {row}: تخفیف از مبلغ ردیف بیشتر است.')
        lot = _text(item.get('lot') or '', f'ردیف {row}: سری ساخت', required=False)[:40]
        expiry = item.get('expiry') or None
        cleaned.append({'product': product, 'qty': qty, 'unit_price': price, 'discount': discount, 'total': total, 'lot': lot, 'expiry': expiry})
    return cleaned


def create_invoice(actor, year, kind, on, party, lines, *, warehouse=None, discount=0, tax=None, visitor='', note='',
                   allow_shortage=False, source=None, paid=0, method='cash', bank_account=None):
    muni = municipality_of(actor)
    if kind not in KINDS:
        raise Invalid('نوع فاکتور نامعتبر است.')
    stockdocs.check_year_open(muni, year, on)
    party = _own_or_invalid(muni, party, 'طرف حساب')
    warehouse = _own_or_invalid(muni, warehouse, 'انبار') if warehouse is not None else inventory.default_warehouse(muni)
    cleaned = _clean_lines(muni, lines)
    config = settings_of(actor)
    subtotal = sum((c['total'] for c in cleaned), 0)
    discount = _amount(discount or 0)
    if discount > subtotal:
        raise Invalid('تخفیف فاکتور از جمع ردیف‌ها بیشتر است.')
    tax = rial((subtotal - discount) * config.vat_percent / 100) if tax in (None, '') else _amount(tax)
    total = subtotal - discount + tax
    visitor, note = _text(visitor, 'ویزیتور', required=False)[:100], _text(note, 'توضیحات', required=False)
    paid = _amount(paid or 0)
    if paid and kind not in PAYABLE_KINDS:
        raise Invalid('برای این نوع فاکتور پرداخت ثبت نمی‌شود.')
    if paid > total:
        raise Invalid('پرداخت از مبلغ فاکتور بیشتر است.')
    shortage_ok = allow_shortage or config.allow_shortage
    with transaction.atomic():
        _locked(Municipality, muni.id)
        invoice = Invoice.objects.create(
            municipality=muni, fiscal_year=year, kind=kind, number=stockdocs.next_number(Invoice, muni, year, kind=kind), date=on,
            party=party, warehouse=warehouse, visitor=visitor, subtotal=subtotal, discount=discount, tax=tax, total=total, note=note,
            source=source, created_by=actor)
        for row, item in enumerate(cleaned, start=1):
            line = InvoiceLine.objects.create(invoice=invoice, row=row, **item)
            sign = Invoice.STOCK_SIGN.get(kind)
            if sign is None:
                continue
            product = item['product']
            if sign < 0:
                if not shortage_ok:
                    inventory.check_available(muni, product, warehouse, item['qty'])
                inventory.add_move(muni, product, warehouse, on, -item['qty'], 'invoice', invoice_line=line)
            else:
                unit_cost = (Decimal(item['total']) / item['qty']) if kind == 'purchase' else inventory.current_avg(muni, product, upto=on)
                inventory.add_move(muni, product, warehouse, on, item['qty'], 'invoice', unit_cost=unit_cost, invoice_line=line,
                                   lot=item['lot'], expiry=item['expiry'])
        if paid:
            add_payment(actor, invoice, on, paid, method, bank_account)
    return invoice


def convert(actor, source, on, *, kind='sale', allow_shortage=False):
    """Turn a proforma or an order into a sale invoice with the same lines; the source is marked converted."""
    muni = municipality_of(actor)
    _own(muni, source)
    if source.kind not in ('proforma', 'order') or source.status != 'issued':
        raise Conflict('فقط پیش‌فاکتور یا سفارش باز تبدیل می‌شود.')
    if kind not in ('sale', 'purchase'):
        raise Invalid('نوع فاکتور مقصد نامعتبر است.')
    lines = [{'product': l.product, 'qty': l.qty, 'unit_price': l.unit_price, 'discount': l.discount, 'lot': l.lot, 'expiry': l.expiry}
             for l in source.lines.select_related('product')]
    with transaction.atomic():
        invoice = create_invoice(actor, source.fiscal_year, kind, on, source.party, lines, warehouse=source.warehouse,
                                 discount=source.discount, tax=source.tax, visitor=source.visitor, note=source.note,
                                 allow_shortage=allow_shortage, source=source)
        source.status = 'converted'
        source.save(update_fields=['status'])
    return invoice


def add_payment(actor, invoice, on, amount, method, bank_account=None, note=''):
    muni = municipality_of(actor)
    _own(muni, invoice)
    if invoice.kind not in PAYABLE_KINDS or invoice.status != 'issued':
        raise Conflict('برای این فاکتور پرداخت ثبت نمی‌شود.')
    if method not in dict(InvoicePayment.METHODS):
        raise Invalid('روش پرداخت نامعتبر است.')
    amount = _amount(amount)
    if amount <= 0:
        raise Invalid('مبلغ پرداخت باید بیشتر از صفر باشد.')
    if on < invoice.date:
        raise Invalid('تاریخ پرداخت نمی‌تواند پیش از تاریخ فاکتور باشد.')
    check_unlocked(muni, on)
    if bank_account is not None:
        bank_account = _own_or_invalid(muni, bank_account, 'حساب بانک/صندوق')
        if bank_account.kind != 'asset' or not bank_account.is_postable:
            raise Invalid('حساب بانک/صندوق باید یک حساب دارایی قابل ثبت باشد.')
    with transaction.atomic():
        invoice = _locked(Invoice, invoice.pk)
        if amount > remaining_of(invoice):
            raise Conflict('پرداخت از باقی‌مانده فاکتور بیشتر است.')
        payment = InvoicePayment.objects.create(invoice=invoice, date=on, amount=amount, method=method, bank_account=bank_account,
                                                note=_text(note, 'توضیحات', required=False), created_by=actor)
        if invoice.voucher_id and bank_account is not None:
            from main.accounting.trade import posting
            posting.post_payment(actor, invoice, payment)
    return payment


def delete_payment(actor, payment):
    muni = municipality_of(actor)
    _own(muni, payment.invoice)
    check_unlocked(muni, payment.date)
    with transaction.atomic():
        voucher = payment.voucher
        if voucher is not None and voucher.status != 'temporary':
            raise Conflict('سند این پرداخت قطعی شده است؛ ابتدا دهیار آن را به موقت برگرداند.')
        payment.delete()
        if voucher is not None:
            ledger.delete_voucher(actor, voucher)


def cancel_invoice(actor, invoice):
    """Cancel: stock comes back, the temporary ledger voucher goes. Refused with payments or a final voucher."""
    muni = municipality_of(actor)
    _own(muni, invoice)
    with transaction.atomic():
        invoice = _locked(Invoice, invoice.pk)
        if invoice.status == 'canceled':
            raise Conflict('این فاکتور قبلاً ابطال شده است.')
        if invoice.status == 'converted':
            raise Conflict('این پیش‌فاکتور به فاکتور تبدیل شده است؛ فاکتور حاصل را ابطال کنید.')
        if invoice.fiscal_year.is_closed:
            raise Conflict('سال مالی بسته شده است.')
        check_unlocked(muni, invoice.date)
        if invoice.payments.exists():
            raise Conflict('فاکتور پرداخت دارد؛ ابتدا پرداخت‌ها را حذف کنید.')
        if invoice.voucher_id:
            if invoice.voucher.status != 'temporary':
                raise Conflict('سند این فاکتور قطعی شده است؛ ابتدا دهیار آن را به موقت برگرداند.')
            ledger.delete_voucher(actor, invoice.voucher)
        products = list(StockMove.objects.filter(invoice_line__invoice=invoice).values_list('product_id', flat=True))
        StockMove.objects.filter(invoice_line__invoice=invoice).delete()
        invoice.status, invoice.canceled_at, invoice.voucher = 'canceled', timezone.now(), None
        invoice.save(update_fields=['status', 'canceled_at', 'voucher'])
        if invoice.source_id:                                    # the proforma goes back to being open
            invoice.source.status = 'issued'
            invoice.source.save(update_fields=['status'])
        stockdocs.ensure_not_negative(muni, products)
    return invoice


def quick_sale(actor, year, items, *, on=None, method='cash', bank_account=None, party=None, visitor='', allow_shortage=False):
    """Point of sale: a sale invoice paid in full at once, to the cash customer unless a party is given."""
    muni = municipality_of(actor)
    on = on or timezone.localdate()
    party = party or cash_customer(muni)
    lines = [{'product': i['product'], 'qty': i['qty'], 'unit_price': i.get('unit_price', i['product'].sell_price),
              'discount': i.get('discount', 0)} for i in items]
    cleaned = _clean_lines(muni, lines)
    total = sum(c['total'] for c in cleaned)
    config = settings_of(actor)
    total += rial(total * config.vat_percent / 100)
    return create_invoice(actor, year, 'sale', on, party, lines, visitor=visitor, allow_shortage=allow_shortage, paid=total,
                          method=method, bank_account=bank_account)
