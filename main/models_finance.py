"""Models of the accountant's extra sections: credit provisioning, contracts, guarantees, payable-document treasury
and voucher images. Imported at the end of main/models.py.

Money is whole rials in ``DecimalField(16, 0)``; every row belongs to one Municipality (the tenant).
Rules live in main/accounting/{credit,contracts,treasury,images}.py.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q

from main.models_accounting import MONEY
from main.storage import PrivateStorage


class CreditProvision(models.Model):
    """تامین اعتبار: money reserved from a resource account for a use account (project/service) of one year."""
    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='credit_provisions')
    fiscal_year = models.ForeignKey('main.FiscalYear', on_delete=models.PROTECT, related_name='credit_provisions')
    number = models.PositiveIntegerField(verbose_name='شماره')   # restarts every fiscal year
    date = models.DateField(verbose_name='تاریخ')
    allocation_no = models.CharField(max_length=30, blank=True, verbose_name='شماره تخصیص')
    allocation_date = models.DateField(null=True, blank=True, verbose_name='تاریخ تخصیص')
    expires_on = models.DateField(null=True, blank=True, verbose_name='تاریخ انقضا')
    description = models.CharField(max_length=500, blank=True, verbose_name='توضیحات')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    canceled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'تامین اعتبار'
        verbose_name_plural = 'تامین اعتبارها'
        ordering = ['fiscal_year', 'number']
        constraints = [models.UniqueConstraint(fields=['fiscal_year', 'number'], name='uniq_credit_number')]


class CreditProvisionLine(models.Model):
    provision = models.ForeignKey(CreditProvision, on_delete=models.CASCADE, related_name='lines')
    row = models.PositiveSmallIntegerField(verbose_name='ردیف')
    use_account = models.ForeignKey('main.Account', on_delete=models.PROTECT, related_name='+', verbose_name='کد حساب مصرف')
    source_account = models.ForeignKey('main.Account', on_delete=models.PROTECT, related_name='+', verbose_name='کد حساب منبع')
    project = models.CharField(max_length=200, blank=True, verbose_name='عنوان پروژه/خدمت')
    description = models.CharField(max_length=300, blank=True, verbose_name='شرح اعتبار')
    amount = models.DecimalField(verbose_name='مبلغ', **MONEY)

    class Meta:
        ordering = ['provision', 'row']
        constraints = [
            models.UniqueConstraint(fields=['provision', 'row'], name='uniq_credit_row'),
            models.CheckConstraint(condition=Q(amount__gt=0), name='credit_line_positive'),
        ]


class Contract(models.Model):
    STATUSES = [('active', 'در حال اجرا'), ('suspended', 'متوقف'), ('finished', 'خاتمه‌یافته'), ('terminated', 'فسخ‌شده')]

    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='contracts')
    fiscal_year = models.ForeignKey('main.FiscalYear', on_delete=models.PROTECT, related_name='contracts')
    number = models.PositiveIntegerField(verbose_name='شماره قرارداد')   # restarts every fiscal year
    kind = models.CharField(max_length=100, blank=True, verbose_name='نوع قرارداد')
    subject = models.CharField(max_length=300, verbose_name='موضوع')
    contractor = models.ForeignKey('main.Party', on_delete=models.PROTECT, related_name='contracts', verbose_name='پیمانکار')
    date = models.DateField(verbose_name='تاریخ قرارداد')
    start_date = models.DateField(verbose_name='تاریخ شروع')
    end_date = models.DateField(verbose_name='تاریخ پایان')
    amount = models.DecimalField(verbose_name='مبلغ قرارداد', **MONEY)
    ceiling = models.DecimalField(verbose_name='سقف مبلغ', **MONEY)   # statements may never exceed this
    status = models.CharField(max_length=12, choices=STATUSES, default='active', verbose_name='وضعیت')
    adjustable = models.BooleanField(default=False, verbose_name='تعدیل‌پذیر')
    cost_center = models.ForeignKey('main.CostCenter', on_delete=models.PROTECT, null=True, blank=True, related_name='+',
                                    verbose_name='مرکز هزینه')
    supervisor = models.CharField(max_length=150, blank=True, verbose_name='ناظر')
    vat_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='٪ ارزش افزوده')
    good_performance_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='٪ حسن انجام کار')
    contractor_insurance_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='٪ بیمه پیمانکار')
    employer_insurance_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='٪ بیمه کارفرما')
    tax_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='٪ مالیات')
    description = models.CharField(max_length=500, blank=True, verbose_name='توضیحات')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'قرارداد'
        verbose_name_plural = 'قراردادها'
        ordering = ['fiscal_year', 'number']
        constraints = [
            models.UniqueConstraint(fields=['fiscal_year', 'number'], name='uniq_contract_number'),
            models.CheckConstraint(condition=Q(amount__gt=0), name='contract_amount_positive'),
            models.CheckConstraint(condition=Q(ceiling__gte=models.F('amount')), name='contract_ceiling_covers_amount'),
        ]


class ContractStatement(models.Model):
    """صورت وضعیت: one progress payment of a contract, with its deductions fixed at the contract's percentages."""
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='statements')
    number = models.PositiveSmallIntegerField(verbose_name='شماره صورت وضعیت')   # per contract
    date = models.DateField(verbose_name='تاریخ')
    description = models.CharField(max_length=300, blank=True, verbose_name='شرح')
    gross = models.DecimalField(verbose_name='کارکرد ناخالص', **MONEY)
    vat = models.DecimalField(verbose_name='ارزش افزوده', **MONEY)
    good_performance = models.DecimalField(verbose_name='حسن انجام کار', **MONEY)
    contractor_insurance = models.DecimalField(verbose_name='بیمه پیمانکار', **MONEY)
    employer_insurance = models.DecimalField(verbose_name='بیمه کارفرما', **MONEY)   # employer's own cost, not deducted
    tax = models.DecimalField(verbose_name='مالیات', **MONEY)
    net = models.DecimalField(verbose_name='خالص قابل پرداخت', **MONEY)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    canceled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'صورت وضعیت'
        verbose_name_plural = 'صورت‌وضعیت‌ها'
        ordering = ['contract', 'number']
        constraints = [
            models.UniqueConstraint(fields=['contract', 'number'], name='uniq_statement_number'),
            models.CheckConstraint(condition=Q(gross__gt=0), name='statement_gross_positive'),
        ]


class Guarantee(models.Model):
    KINDS = [('good_performance', 'حسن انجام کار'), ('advance', 'پیش‌پرداخت'), ('bid', 'شرکت در مناقصه'),
             ('obligations', 'حسن انجام تعهدات')]
    DOC_KINDS = [('bank_guarantee', 'ضمانت‌نامه بانکی'), ('cheque', 'چک'), ('promissory', 'سفته'), ('deposit', 'سپرده نقدی')]
    STATUSES = [('active', 'معتبر'), ('returned', 'مسترد شد'), ('seized', 'ضبط شد')]

    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='guarantees')
    contract = models.ForeignKey(Contract, on_delete=models.PROTECT, null=True, blank=True, related_name='guarantees',
                                 verbose_name='قرارداد')
    party = models.ForeignKey('main.Party', on_delete=models.PROTECT, related_name='guarantees', verbose_name='صاحب ضمانت‌نامه')
    kind = models.CharField(max_length=20, choices=KINDS, verbose_name='نوع ضمانت‌نامه')
    doc_kind = models.CharField(max_length=20, choices=DOC_KINDS, verbose_name='نوع مدرک')
    serial = models.CharField(max_length=60, verbose_name='شماره / سریال')
    bank = models.CharField(max_length=100, blank=True, verbose_name='بانک صادرکننده')
    date = models.DateField(verbose_name='تاریخ')
    expires_on = models.DateField(verbose_name='تاریخ سررسید')
    amount = models.DecimalField(verbose_name='مبلغ', **MONEY)
    status = models.CharField(max_length=10, choices=STATUSES, default='active', verbose_name='وضعیت')
    status_changed_on = models.DateField(null=True, blank=True)
    description = models.CharField(max_length=300, blank=True, verbose_name='توضیحات')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'ضمانت‌نامه'
        verbose_name_plural = 'ضمانت‌نامه‌ها'
        ordering = ['expires_on', 'id']
        constraints = [
            models.UniqueConstraint(fields=['municipality', 'doc_kind', 'serial'], name='uniq_guarantee_serial'),
            models.CheckConstraint(condition=Q(amount__gt=0), name='guarantee_amount_positive'),
        ]


class PayableDocument(models.Model):
    """خزانه اسناد پرداختی: a cheque or promissory note the municipality issued, followed until it is cleared."""
    KINDS = [('cheque', 'چک'), ('promissory', 'سفته')]
    STATUSES = [('issued', 'صادر شده'), ('passed', 'پاس شده'), ('returned', 'برگشت خورده'), ('canceled', 'باطل شده')]

    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='payable_documents')
    fiscal_year = models.ForeignKey('main.FiscalYear', on_delete=models.PROTECT, related_name='payable_documents')
    kind = models.CharField(max_length=12, choices=KINDS, default='cheque', verbose_name='نوع سند')
    serial = models.CharField(max_length=60, verbose_name='سریال / شماره')
    party = models.ForeignKey('main.Party', on_delete=models.PROTECT, related_name='payable_documents', verbose_name='در وجه')
    bank_account = models.ForeignKey('main.Account', on_delete=models.PROTECT, related_name='+', verbose_name='حساب بانک')
    issue_date = models.DateField(verbose_name='تاریخ صدور')
    due_date = models.DateField(verbose_name='تاریخ سررسید')
    amount = models.DecimalField(verbose_name='مبلغ', **MONEY)
    status = models.CharField(max_length=10, choices=STATUSES, default='issued', verbose_name='وضعیت')
    status_date = models.DateField(null=True, blank=True)
    description = models.CharField(max_length=300, blank=True, verbose_name='شرح')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'سند پرداختی'
        verbose_name_plural = 'اسناد پرداختی'
        ordering = ['due_date', 'id']
        constraints = [
            models.UniqueConstraint(fields=['municipality', 'kind', 'serial'], name='uniq_payable_serial'),
            models.CheckConstraint(condition=Q(amount__gt=0), name='payable_amount_positive'),
        ]


class PayableEvent(models.Model):
    """History of a payable document: every status change with its date and the user who made it."""
    document = models.ForeignKey(PayableDocument, on_delete=models.CASCADE, related_name='events')
    status = models.CharField(max_length=10, choices=PayableDocument.STATUSES)
    date = models.DateField()
    note = models.CharField(max_length=300, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']


class DocumentImage(models.Model):
    """تصاویر اسناد: scan/photo of the paper behind a voucher. Private storage, served only to the same municipality."""
    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='document_images')
    voucher = models.ForeignKey('main.Voucher', on_delete=models.PROTECT, related_name='images')
    title = models.CharField(max_length=150, verbose_name='عنوان')
    file = models.FileField(upload_to='voucher_images/%Y/%m/', storage=PrivateStorage())
    content_type = models.CharField(max_length=60, blank=True)
    size = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'تصویر سند'
        verbose_name_plural = 'تصاویر اسناد'
        ordering = ['-id']
