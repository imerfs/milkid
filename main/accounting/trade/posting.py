"""Posting invoices (and their payments) to the ledger as temporary vouchers, using the accounts of TradeSettings.

sale:             debit receivable (party) / credit sales (and VAT payable); cost of goods: debit COGS / credit inventory
purchase:         debit inventory (and VAT) / credit payable (party)
returns:          the mirror image
payment:          debit bank / credit receivable (sale); debit payable / credit bank (purchase)
A proforma or an order is never posted. Voucher numbering, dates, locks and the closed-year rule are the ledger's own.
"""
from django.db import transaction

from main.accounting import ledger
from main.accounting.ledger import _own, municipality_of
from main.accounting.trade import inventory, invoices
from main.accounting.trade.inventory import ZERO, rial
from main.office.errors import Conflict, Invalid

LABELS = {'receivable_account': 'حساب دریافتنی', 'payable_account': 'حساب پرداختنی', 'sales_account': 'حساب درآمد فروش',
          'inventory_account': 'حساب موجودی کالا', 'tax_account': 'حساب مالیات بر ارزش افزوده',
          'cogs_account': 'حساب بهای تمام‌شده'}


def _need(config, *names):
    missing = [LABELS[n] for n in names if getattr(config, n) is None]
    if missing:
        raise Invalid('در تنظیمات بازرگانی این حساب‌ها را مشخص کنید: ' + '، '.join(missing) + '.')


def invoice_cost(muni, invoice):
    """Cost of the goods of a sale (what left at the weighted average) or a sale return (what came back)."""
    cost = ZERO
    for product in {l.product for l in invoice.lines.select_related('product')}:
        for row in inventory.walk(inventory.moves_of(muni, product)):
            move = row['move']
            if move.invoice_line_id and move.invoice_line.invoice_id == invoice.id:
                cost += (-move.qty * row['out_cost']) if row['out_cost'] is not None else move.qty * move.unit_cost
    return rial(cost)


def _line(account, debit, credit, party=None, description=''):
    return {'account': account, 'debit': debit, 'credit': credit, 'party': party, 'description': description}


def build_lines(muni, invoice, config):
    """Voucher lines of one invoice; raises Invalid when a needed account is not configured."""
    net = int(invoice.subtotal - invoice.discount)
    tax, total = int(invoice.tax), int(invoice.total)
    sale_side = invoice.kind in ('sale', 'sale_return')
    _need(config, 'receivable_account' if sale_side else 'payable_account', 'sales_account' if sale_side else 'inventory_account')
    if tax:
        _need(config, 'tax_account')
    party_account = config.receivable_account if sale_side else config.payable_account
    lines = []
    if invoice.kind == 'sale':
        lines = [_line(party_account, total, 0, invoice.party), _line(config.sales_account, 0, net)]
        if tax:
            lines.append(_line(config.tax_account, 0, tax))
    elif invoice.kind == 'sale_return':
        lines = [_line(config.sales_account, net, 0), _line(party_account, 0, total, invoice.party)]
        if tax:
            lines.append(_line(config.tax_account, tax, 0))
    elif invoice.kind == 'purchase':
        lines = [_line(config.inventory_account, net, 0), _line(party_account, 0, total, invoice.party)]
        if tax:
            lines.append(_line(config.tax_account, tax, 0))
    else:                                                                    # purchase_return
        lines = [_line(party_account, total, 0, invoice.party), _line(config.inventory_account, 0, net)]
        if tax:
            lines.append(_line(config.tax_account, 0, tax))
    if sale_side and config.cogs_account is not None and config.inventory_account is not None:
        cost = invoice_cost(muni, invoice)
        if cost > 0:
            if invoice.kind == 'sale':
                lines += [_line(config.cogs_account, cost, 0, description='بهای تمام‌شده کالای فروخته‌شده'),
                          _line(config.inventory_account, 0, cost, description='خروج کالا از انبار')]
            else:
                lines += [_line(config.inventory_account, cost, 0, description='برگشت کالا به انبار'),
                          _line(config.cogs_account, 0, cost, description='کاهش بهای تمام‌شده')]
    return [l for l in lines if l['debit'] or l['credit']]


def post_invoice(actor, invoice):
    """Create the temporary voucher of an issued invoice (and of the payments already recorded) and link it."""
    muni = municipality_of(actor)
    _own(muni, invoice)
    if invoice.kind in ('proforma', 'order'):
        raise Conflict('پیش‌فاکتور و سفارش در دفتر ثبت نمی‌شود.')
    if invoice.status != 'issued':
        raise Conflict('فقط فاکتور صادرشده در دفتر ثبت می‌شود.')
    if invoice.voucher_id:
        raise Conflict('این فاکتور قبلاً در دفتر ثبت شده است.')
    config = invoices.settings_of(actor)
    with transaction.atomic():
        lines = build_lines(muni, invoice, config)
        voucher = ledger.create_voucher(actor, invoice.fiscal_year, invoice.date, 'general',
                                        f'{invoice.get_kind_display()} شماره {invoice.number} - {invoice.party.name}'[:500], lines)
        invoice.voucher = voucher
        invoice.save(update_fields=['voucher'])
        for payment in invoice.payments.filter(voucher__isnull=True, bank_account__isnull=False):
            post_payment(actor, invoice, payment)
    return voucher


def post_payment(actor, invoice, payment):
    config = invoices.settings_of(actor)
    sale = invoice.kind == 'sale'
    _need(config, 'receivable_account' if sale else 'payable_account')
    account = config.receivable_account if sale else config.payable_account
    bank = payment.bank_account
    amount = int(payment.amount)
    lines = ([_line(bank, amount, 0, description='دریافت وجه'), _line(account, 0, amount, invoice.party)] if sale
             else [_line(account, amount, 0, invoice.party), _line(bank, 0, amount, description='پرداخت وجه')])
    year = invoice.fiscal_year
    on = payment.date if year.start_date <= payment.date <= year.end_date else invoice.date
    voucher = ledger.create_voucher(actor, year, on, 'general',
                                    f'{"دریافت" if sale else "پرداخت"} وجه {invoice.get_kind_display()} شماره {invoice.number}'[:500], lines)
    payment.voucher = voucher
    payment.save(update_fields=['voucher'])
    return voucher


def unpost_invoice(actor, invoice):
    """Remove the temporary vouchers of the invoice and its payments (a final voucher must be reverted first)."""
    muni = municipality_of(actor)
    _own(muni, invoice)
    if not invoice.voucher_id:
        raise Conflict('این فاکتور در دفتر ثبت نشده است.')
    with transaction.atomic():
        vouchers = [invoice.voucher] + [p.voucher for p in invoice.payments.select_related('voucher') if p.voucher_id]
        if any(v.status != 'temporary' for v in vouchers):
            raise Conflict('یکی از اسناد قطعی شده است؛ ابتدا دهیار آن را به موقت برگرداند.')
        invoice.payments.update(voucher=None)
        voucher = invoice.voucher
        invoice.voucher = None
        invoice.save(update_fields=['voucher'])
        for v in vouchers:
            ledger.delete_voucher(actor, v)
    return voucher
