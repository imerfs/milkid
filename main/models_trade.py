"""Trade side of the accountant workspace: products, warehouses, invoices, stock documents, production, consignment.

Quantities are ``Decimal(14, 3)``; money is whole rials; a unit cost keeps four decimals (weighted average).
Rules live in ``main/accounting/trade/``; constraints here are the last line of defence. Imported at the end of main/models.py.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q

__all__ = ['Product', 'Warehouse', 'Invoice', 'InvoiceLine', 'InvoicePayment', 'StockDoc', 'StockDocLine', 'StockMove', 'Formula',
           'FormulaLine', 'ProductionRun', 'Consignment', 'ConsignmentLine', 'TradeSettings']

MONEY = {'max_digits': 16, 'decimal_places': 0}
QTY = {'max_digits': 14, 'decimal_places': 3}
COST = {'max_digits': 18, 'decimal_places': 4}


class Warehouse(models.Model):
    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='warehouses')
    code = models.CharField(max_length=20, verbose_name='کد')
    name = models.CharField(max_length=100, verbose_name='نام انبار')
    is_default = models.BooleanField(default=False, verbose_name='انبار پیش‌فرض')

    class Meta:
        verbose_name = 'انبار'
        verbose_name_plural = 'انبارها'
        ordering = ['code']
        constraints = [models.UniqueConstraint(fields=['municipality', 'code'], name='uniq_warehouse_code')]

    def __str__(self):
        return f'{self.code} - {self.name}'


class Product(models.Model):
    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='products')
    code = models.CharField(max_length=30, verbose_name='کد کالا')
    name = models.CharField(max_length=200, verbose_name='نام کالا')
    unit = models.CharField(max_length=30, default='عدد', verbose_name='واحد')
    category = models.CharField(max_length=100, blank=True, verbose_name='دسته')
    barcode = models.CharField(max_length=40, blank=True, verbose_name='بارکد')
    buy_price = models.DecimalField(default=0, verbose_name='قیمت خرید', **MONEY)
    sell_price = models.DecimalField(default=0, verbose_name='قیمت فروش', **MONEY)
    min_stock = models.DecimalField(default=0, verbose_name='حداقل موجودی', **QTY)
    is_active = models.BooleanField(default=True, verbose_name='فعال')

    class Meta:
        verbose_name = 'کالا'
        verbose_name_plural = 'کالاها'
        ordering = ['code']
        constraints = [models.UniqueConstraint(fields=['municipality', 'code'], name='uniq_product_code'),
                       models.CheckConstraint(condition=Q(buy_price__gte=0) & Q(sell_price__gte=0) & Q(min_stock__gte=0),
                                              name='product_amounts_not_negative')]

    def __str__(self):
        return f'{self.code} - {self.name}'


class Invoice(models.Model):
    KINDS = [('sale', 'فروش'), ('purchase', 'خرید'), ('sale_return', 'برگشت از فروش'), ('purchase_return', 'برگشت از خرید'),
             ('proforma', 'پیش‌فاکتور'), ('order', 'سفارش')]
    STOCK_SIGN = {'sale': -1, 'purchase': 1, 'sale_return': 1, 'purchase_return': -1}      # proforma and order never move stock
    STATUSES = [('issued', 'صادر شده'), ('converted', 'تبدیل‌شده'), ('canceled', 'ابطال‌شده')]

    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='invoices')
    fiscal_year = models.ForeignKey('main.FiscalYear', on_delete=models.PROTECT, related_name='invoices')
    kind = models.CharField(max_length=16, choices=KINDS, verbose_name='نوع')
    number = models.PositiveIntegerField(verbose_name='شماره')                      # restarts every year, per kind
    date = models.DateField(verbose_name='تاریخ')
    party = models.ForeignKey('main.Party', on_delete=models.PROTECT, related_name='invoices', verbose_name='طرف حساب')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='invoices', verbose_name='انبار')
    visitor = models.CharField(max_length=100, blank=True, verbose_name='ویزیتور')
    subtotal = models.DecimalField(default=0, **MONEY)
    discount = models.DecimalField(default=0, verbose_name='تخفیف', **MONEY)
    tax = models.DecimalField(default=0, verbose_name='مالیات بر ارزش افزوده', **MONEY)
    total = models.DecimalField(default=0, **MONEY)
    note = models.CharField(max_length=300, blank=True, verbose_name='توضیحات')
    status = models.CharField(max_length=10, choices=STATUSES, default='issued')
    source = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='converted_to')
    voucher = models.ForeignKey('main.Voucher', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    canceled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'فاکتور'
        verbose_name_plural = 'فاکتورها'
        ordering = ['fiscal_year', 'kind', 'number']
        constraints = [
            models.UniqueConstraint(fields=['fiscal_year', 'kind', 'number'], name='uniq_invoice_number'),
            models.CheckConstraint(condition=Q(subtotal__gte=0) & Q(discount__gte=0) & Q(tax__gte=0) & Q(total__gte=0),
                                   name='invoice_amounts_not_negative'),
        ]

    def __str__(self):
        return f'{self.get_kind_display()} {self.number}'


class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='lines')
    row = models.PositiveSmallIntegerField()
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='invoice_lines')
    qty = models.DecimalField(**QTY)
    unit_price = models.DecimalField(**MONEY)
    discount = models.DecimalField(default=0, **MONEY)
    total = models.DecimalField(**MONEY)
    lot = models.CharField(max_length=40, blank=True, verbose_name='سری ساخت')
    expiry = models.DateField(null=True, blank=True, verbose_name='تاریخ انقضا')

    class Meta:
        ordering = ['invoice', 'row']
        constraints = [models.UniqueConstraint(fields=['invoice', 'row'], name='uniq_invoice_row'),
                       models.CheckConstraint(condition=Q(qty__gt=0) & Q(unit_price__gte=0) & Q(discount__gte=0) & Q(total__gte=0),
                                              name='invoice_line_amounts')]


class InvoicePayment(models.Model):
    METHODS = [('cash', 'نقد'), ('card', 'کارتخوان'), ('transfer', 'واریز به حساب'), ('cheque', 'چک')]

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    date = models.DateField()
    amount = models.DecimalField(**MONEY)
    method = models.CharField(max_length=10, choices=METHODS, default='cash')
    bank_account = models.ForeignKey('main.Account', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    voucher = models.ForeignKey('main.Voucher', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    note = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')

    class Meta:
        ordering = ['date', 'id']
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name='invoice_payment_positive')]


class StockDoc(models.Model):
    KINDS = [('receipt', 'رسید انبار'), ('issue', 'حواله انبار'), ('adjust', 'تعدیل موجودی'), ('transfer', 'انتقال بین انبارها'),
             ('stocktake', 'انبارگردانی')]

    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='stock_docs')
    fiscal_year = models.ForeignKey('main.FiscalYear', on_delete=models.PROTECT, related_name='stock_docs')
    kind = models.CharField(max_length=10, choices=KINDS)
    number = models.PositiveIntegerField()
    date = models.DateField()
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='stock_docs')
    to_warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, null=True, blank=True, related_name='incoming_docs')
    note = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    canceled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'سند انبار'
        verbose_name_plural = 'اسناد انبار'
        ordering = ['fiscal_year', 'kind', 'number']
        constraints = [models.UniqueConstraint(fields=['fiscal_year', 'kind', 'number'], name='uniq_stockdoc_number')]


class StockDocLine(models.Model):
    doc = models.ForeignKey(StockDoc, on_delete=models.CASCADE, related_name='lines')
    row = models.PositiveSmallIntegerField()
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='stock_doc_lines')
    qty = models.DecimalField(**QTY)                       # receipt/issue/transfer: positive; adjust: signed; stocktake: difference
    unit_cost = models.DecimalField(default=0, **COST)     # receipt cost; outflows use the weighted average
    counted = models.DecimalField(null=True, blank=True, **QTY)   # stocktake: what was counted (qty = counted - book)
    lot = models.CharField(max_length=40, blank=True, verbose_name='سری ساخت')
    expiry = models.DateField(null=True, blank=True, verbose_name='تاریخ انقضا')

    class Meta:
        ordering = ['doc', 'row']
        constraints = [models.UniqueConstraint(fields=['doc', 'row'], name='uniq_stockdoc_row')]


class Formula(models.Model):
    """Bill of materials: how many of the component products make ``output_qty`` of the output product."""
    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='formulas')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='formulas', verbose_name='کالای تولیدی')
    output_qty = models.DecimalField(default=1, verbose_name='مقدار تولید', **QTY)
    note = models.CharField(max_length=300, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'فرمول ساخت'
        verbose_name_plural = 'فرمول‌های ساخت'
        ordering = ['product__code']
        constraints = [models.CheckConstraint(condition=Q(output_qty__gt=0), name='formula_output_positive')]


class FormulaLine(models.Model):
    formula = models.ForeignKey(Formula, on_delete=models.CASCADE, related_name='lines')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='used_in')
    qty = models.DecimalField(**QTY)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['formula', 'product'], name='uniq_formula_component'),
                       models.CheckConstraint(condition=Q(qty__gt=0), name='formula_line_positive')]


class ProductionRun(models.Model):
    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='production_runs')
    fiscal_year = models.ForeignKey('main.FiscalYear', on_delete=models.PROTECT, related_name='production_runs')
    number = models.PositiveIntegerField()
    formula = models.ForeignKey(Formula, on_delete=models.PROTECT, related_name='runs')
    batches = models.DecimalField(default=1, **QTY)
    date = models.DateField()
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='production_runs')
    unit_cost = models.DecimalField(default=0, **COST)    # cost of one unit of output, from the components' weighted averages
    lot = models.CharField(max_length=40, blank=True, verbose_name='سری ساخت')
    expiry = models.DateField(null=True, blank=True, verbose_name='تاریخ انقضا')
    note = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    canceled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'تولید'
        verbose_name_plural = 'تولیدها'
        ordering = ['fiscal_year', 'number']
        constraints = [models.UniqueConstraint(fields=['fiscal_year', 'number'], name='uniq_production_number'),
                       models.CheckConstraint(condition=Q(batches__gt=0), name='production_batches_positive')]


class Consignment(models.Model):
    """امانی: goods given to a party to sell (stock leaves) or taken from one (memo only: not our stock)."""
    KINDS = [('given', 'امانی داده‌شده'), ('taken', 'امانی گرفته‌شده')]
    STATUSES = [('open', 'باز'), ('closed', 'تسویه‌شده'), ('canceled', 'ابطال‌شده')]

    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='consignments')
    kind = models.CharField(max_length=6, choices=KINDS)
    party = models.ForeignKey('main.Party', on_delete=models.PROTECT, related_name='consignments')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='consignments')
    date = models.DateField()
    note = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default='open')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'امانی'
        verbose_name_plural = 'امانی‌ها'
        ordering = ['-date', '-id']


class ConsignmentLine(models.Model):
    consignment = models.ForeignKey(Consignment, on_delete=models.CASCADE, related_name='lines')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='consignment_lines')
    qty = models.DecimalField(**QTY)
    returned = models.DecimalField(default=0, **QTY)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(qty__gt=0) & Q(returned__gte=0) & Q(returned__lte=models.F('qty')),
                                              name='consignment_line_amounts')]


class StockMove(models.Model):
    """The single source of truth for stock: every receipt, sale, issue, transfer or production writes rows here."""
    KINDS = [('invoice', 'فاکتور'), ('doc', 'سند انبار'), ('production_in', 'تولید (محصول)'), ('production_out', 'تولید (مصرف)'),
             ('consignment', 'امانی')]

    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='stock_moves')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='moves')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='moves')
    date = models.DateField(db_index=True)
    qty = models.DecimalField(**QTY)                       # signed: + in, - out
    unit_cost = models.DecimalField(default=0, **COST)     # inflows only; outflows leave at the weighted average
    kind = models.CharField(max_length=16, choices=KINDS)
    lot = models.CharField(max_length=40, blank=True)     # production series; blank = untracked
    expiry = models.DateField(null=True, blank=True)
    invoice_line = models.ForeignKey(InvoiceLine, on_delete=models.CASCADE, null=True, blank=True, related_name='moves')
    doc = models.ForeignKey(StockDoc, on_delete=models.CASCADE, null=True, blank=True, related_name='moves')
    production = models.ForeignKey(ProductionRun, on_delete=models.CASCADE, null=True, blank=True, related_name='moves')
    consignment = models.ForeignKey(Consignment, on_delete=models.CASCADE, null=True, blank=True, related_name='moves')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date', 'id']
        indexes = [models.Index(fields=['municipality', 'product', 'date'])]
        constraints = [models.CheckConstraint(condition=~Q(qty=0), name='stock_move_not_zero')]


class TradeSettings(models.Model):
    """Accounts the invoices post to (all optional: without them an invoice simply cannot be posted to the ledger)."""
    municipality = models.OneToOneField('main.Municipality', on_delete=models.CASCADE, related_name='trade_settings')
    receivable_account = models.ForeignKey('main.Account', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
                                           verbose_name='حساب دریافتنی (مشتریان)')
    payable_account = models.ForeignKey('main.Account', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
                                        verbose_name='حساب پرداختنی (تامین‌کنندگان)')
    sales_account = models.ForeignKey('main.Account', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
                                      verbose_name='حساب درآمد فروش')
    inventory_account = models.ForeignKey('main.Account', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
                                          verbose_name='حساب موجودی کالا')
    cogs_account = models.ForeignKey('main.Account', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
                                     verbose_name='حساب بهای تمام‌شده فروش')
    tax_account = models.ForeignKey('main.Account', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
                                    verbose_name='حساب مالیات بر ارزش افزوده')
    vat_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='درصد مالیات بر ارزش افزوده')
    allow_shortage = models.BooleanField(default=False, verbose_name='فروش با کمبود موجودی مجاز است')

    class Meta:
        verbose_name = 'تنظیمات بازرگانی'
        verbose_name_plural = 'تنظیمات بازرگانی'
