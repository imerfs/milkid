"""Fixed assets and their depreciation. Imported at the end of main/models.py.

Money is whole rials. Rules (schedules, posting, disposal) live in main/accounting/assets.py.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q

__all__ = ['Asset', 'AssetDepreciation']

MONEY = {'max_digits': 16, 'decimal_places': 0}


class Asset(models.Model):
    METHODS = [('line', 'خط مستقیم'), ('declining', 'نزولی (مانده)')]
    STATUSES = [('active', 'در خدمت'), ('disposed', 'خارج‌شده')]

    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='assets')
    code = models.CharField(max_length=30, verbose_name='کد دارایی')
    title = models.CharField(max_length=200, verbose_name='عنوان')
    acquisition_date = models.DateField(verbose_name='تاریخ تحصیل')
    cost = models.DecimalField(verbose_name='بهای تمام‌شده', **MONEY)
    salvage = models.DecimalField(default=0, verbose_name='ارزش اسقاط', **MONEY)
    life_years = models.PositiveSmallIntegerField(verbose_name='عمر مفید (سال)')
    method = models.CharField(max_length=10, choices=METHODS, default='line', verbose_name='روش استهلاک')
    account = models.ForeignKey('main.Account', on_delete=models.PROTECT, related_name='+', verbose_name='حساب دارایی')
    accumulated_account = models.ForeignKey('main.Account', on_delete=models.PROTECT, related_name='+', verbose_name='حساب استهلاک انباشته')
    expense_account = models.ForeignKey('main.Account', on_delete=models.PROTECT, related_name='+', verbose_name='حساب هزینه استهلاک')
    status = models.CharField(max_length=10, choices=STATUSES, default='active', verbose_name='وضعیت')
    disposed_on = models.DateField(null=True, blank=True, verbose_name='تاریخ خروج')
    disposal_amount = models.DecimalField(default=0, verbose_name='مبلغ فروش', **MONEY)
    disposal_voucher = models.ForeignKey('main.Voucher', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    description = models.CharField(max_length=500, blank=True, verbose_name='توضیحات')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'دارایی ثابت'
        verbose_name_plural = 'دارایی‌های ثابت'
        ordering = ['code']
        constraints = [
            models.UniqueConstraint(fields=['municipality', 'code'], name='uniq_asset_code'),
            models.CheckConstraint(condition=Q(cost__gt=0) & Q(salvage__gte=0) & Q(salvage__lt=models.F('cost')), name='asset_amounts'),
            models.CheckConstraint(condition=Q(life_years__gte=1), name='asset_life_positive'),
        ]

    def __str__(self):
        return f'{self.code} - {self.title}'


class AssetDepreciation(models.Model):
    """Depreciation of one asset in one fiscal year, posted by a voucher."""
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='depreciations')
    fiscal_year = models.ForeignKey('main.FiscalYear', on_delete=models.PROTECT, related_name='asset_depreciations')
    amount = models.DecimalField(verbose_name='استهلاک سال', **MONEY)
    voucher = models.ForeignKey('main.Voucher', on_delete=models.PROTECT, related_name='asset_depreciations')

    class Meta:
        verbose_name = 'استهلاک سال'
        verbose_name_plural = 'استهلاک‌های سال'
        constraints = [models.UniqueConstraint(fields=['asset', 'fiscal_year'], name='uniq_asset_year'),
                       models.CheckConstraint(condition=Q(amount__gt=0), name='asset_depreciation_positive')]
