"""Models of the accounting section (chart of accounts, parties, vouchers). Imported at the end of main/models.py.

Money is whole rials in ``DecimalField(16, 0)``. Every row belongs to one Municipality (the tenant).
Business rules live in ``main/accounting/ledger.py``; constraints here are the last line of defence.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from main.validators import validate_iranian_national_id

MONEY = {'max_digits': 16, 'decimal_places': 0}


class FiscalYear(models.Model):
    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='fiscal_years')
    year = models.PositiveSmallIntegerField(verbose_name='سال مالی')  # Jalali, e.g. 1404
    start_date = models.DateField(verbose_name='شروع')
    end_date = models.DateField(verbose_name='پایان')
    is_closed = models.BooleanField(default=False, verbose_name='بسته‌شده')

    class Meta:
        verbose_name = 'سال مالی'
        verbose_name_plural = 'سال‌های مالی'
        ordering = ['-year']
        constraints = [models.UniqueConstraint(fields=['municipality', 'year'], name='uniq_fiscal_year')]

    def __str__(self):
        return str(self.year)


class Account(models.Model):
    KINDS = [
        ('asset', 'دارایی'), ('liability', 'بدهی'), ('equity', 'حقوق صاحبان سرمایه'),
        ('budget_resource', 'منابع بودجه'), ('budget_use', 'مصارف بودجه'), ('closing', 'اختتامیه'),
    ]
    NATURES = [('debit', 'بدهکار'), ('credit', 'بستانکار')]

    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='accounts')
    code = models.CharField(max_length=20, verbose_name='کد حساب')
    title = models.CharField(max_length=200, verbose_name='شرح حساب')
    parent = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True, related_name='children')
    kind = models.CharField(max_length=20, choices=KINDS, verbose_name='نوع حساب')
    nature = models.CharField(max_length=10, choices=NATURES, verbose_name='ماهیت')
    requires_party = models.BooleanField(default=False, verbose_name='نیازمند طرف حساب')
    is_postable = models.BooleanField(default=True, verbose_name='قابل ثبت سند')

    class Meta:
        verbose_name = 'حساب'
        verbose_name_plural = 'حساب‌ها'
        ordering = ['code']
        constraints = [models.UniqueConstraint(fields=['municipality', 'code'], name='uniq_account_code')]

    def __str__(self):
        return f'{self.code} - {self.title}'


class Party(models.Model):
    KINDS = [('real', 'حقیقی'), ('legal', 'حقوقی')]

    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='parties')
    kind = models.CharField(max_length=10, choices=KINDS, default='real', verbose_name='نوع شخص')
    national_id = models.CharField(max_length=11, blank=True, verbose_name='شماره/شناسه ملی')
    name = models.CharField(max_length=200, verbose_name='نام')
    father_name = models.CharField(max_length=100, blank=True, verbose_name='نام پدر')
    economic_code = models.CharField(max_length=20, blank=True, verbose_name='کد اقتصادی')
    phone = models.CharField(max_length=20, blank=True, verbose_name='تلفن')
    mobile = models.CharField(max_length=20, blank=True, verbose_name='همراه')
    postal_code = models.CharField(max_length=10, blank=True, verbose_name='کد پستی')
    address = models.CharField(max_length=500, blank=True, verbose_name='نشانی')
    bank_name = models.CharField(max_length=100, blank=True, verbose_name='نام بانک')
    account_no = models.CharField(max_length=30, blank=True, verbose_name='شماره حساب')
    iban = models.CharField(max_length=26, blank=True, verbose_name='شماره شبا')

    class Meta:
        verbose_name = 'طرف حساب'
        verbose_name_plural = 'طرف حساب‌ها'
        ordering = ['name']

    def __str__(self):
        return self.name

    def clean(self):
        nid = (self.national_id or '').strip()
        self.national_id = nid
        if not nid:
            return
        if self.kind == 'legal':
            if len(nid) != 11 or not nid.isdigit():
                raise ValidationError({'national_id': 'شناسه ملی شخص حقوقی باید ۱۱ رقم باشد.'})
        else:
            validate_iranian_national_id(nid)
            if len(set(nid)) == 1:
                raise ValidationError({'national_id': 'کد ملی معتبر نیست.'})
        dup = Party.objects.filter(municipality_id=self.municipality_id, national_id=nid).exclude(pk=self.pk)
        if dup.exists():
            raise ValidationError({'national_id': 'این کد ملی قبلاً ثبت شده است.'})


class CostCenter(models.Model):
    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='cost_centers')
    code = models.CharField(max_length=10, verbose_name='کد')
    title = models.CharField(max_length=100, verbose_name='شرح')

    class Meta:
        verbose_name = 'مرکز هزینه'
        verbose_name_plural = 'مراکز هزینه'
        ordering = ['code']
        constraints = [models.UniqueConstraint(fields=['municipality', 'code'], name='uniq_cost_center_code')]

    def __str__(self):
        return f'{self.code} - {self.title}'


class Voucher(models.Model):
    KINDS = [
        ('general', 'عمومی'), ('income', 'درآمد'), ('expense', 'هزینه'), ('transfer', 'انتقالی'),
        ('offset', 'تهاتر'), ('warehouse', 'انبار'), ('opening', 'افتتاحیه'),
        ('temp_closing', 'بستن حساب‌های موقت'), ('closing', 'اختتامیه'),
    ]
    STATUSES = [('temporary', 'موقت'), ('final', 'قطعی')]

    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='vouchers')
    fiscal_year = models.ForeignKey(FiscalYear, on_delete=models.PROTECT, related_name='vouchers')
    number = models.PositiveIntegerField(verbose_name='شماره سند')   # restarts every fiscal year
    ref = models.PositiveIntegerField(verbose_name='شناسه سند')      # never repeats within the municipality
    date = models.DateField(verbose_name='تاریخ')
    kind = models.CharField(max_length=20, choices=KINDS, default='general', verbose_name='نوع سند')
    description = models.CharField(max_length=500, verbose_name='شرح سند')
    status = models.CharField(max_length=10, choices=STATUSES, default='temporary', verbose_name='وضعیت')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                   related_name='+')
    finalized_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='+')
    finalized_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'سند حسابداری'
        verbose_name_plural = 'اسناد حسابداری'
        ordering = ['fiscal_year', 'number']
        constraints = [
            models.UniqueConstraint(fields=['fiscal_year', 'number'], name='uniq_voucher_number'),
            models.UniqueConstraint(fields=['municipality', 'ref'], name='uniq_voucher_ref'),
        ]

    def __str__(self):
        return f'سند {self.number} - {self.description[:40]}'


class VoucherLine(models.Model):
    voucher = models.ForeignKey(Voucher, on_delete=models.CASCADE, related_name='lines')
    row = models.PositiveSmallIntegerField(verbose_name='ردیف')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='lines', verbose_name='کدحساب')
    party = models.ForeignKey(Party, on_delete=models.PROTECT, null=True, blank=True, related_name='lines',
                              verbose_name='طرف حساب')
    cost_center = models.ForeignKey(CostCenter, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name='lines', verbose_name='مرکز هزینه')
    description = models.CharField(max_length=500, blank=True, verbose_name='شرح')
    debit = models.DecimalField(default=0, verbose_name='بدهکار', **MONEY)
    credit = models.DecimalField(default=0, verbose_name='بستانکار', **MONEY)

    class Meta:
        verbose_name = 'ردیف سند'
        verbose_name_plural = 'ردیف‌های سند'
        ordering = ['voucher', 'row']
        constraints = [
            models.UniqueConstraint(fields=['voucher', 'row'], name='uniq_voucher_row'),
            models.CheckConstraint(
                condition=(Q(debit__gt=0, credit=0) | Q(credit__gt=0, debit=0)), name='voucher_line_one_side'),
        ]


class BudgetLine(models.Model):
    """Approved budget of one resource/use account in a fiscal year (whole rials). Actuals come from voucher lines."""
    fiscal_year = models.ForeignKey(FiscalYear, on_delete=models.CASCADE, related_name='budget_lines')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='budget_lines')
    amount = models.DecimalField(default=0, verbose_name='بودجه مصوب', **MONEY)

    class Meta:
        verbose_name = 'ردیف بودجه'
        verbose_name_plural = 'ردیف‌های بودجه'
        ordering = ['account__code']
        constraints = [
            models.UniqueConstraint(fields=['fiscal_year', 'account'], name='uniq_budget_line'),
            models.CheckConstraint(condition=Q(amount__gte=0), name='budget_amount_not_negative'),
        ]
