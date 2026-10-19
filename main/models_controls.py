"""Accounting controls: the date lock and bank reconciliation marks. Imported at the end of main/models.py."""
from django.conf import settings
from django.db import models

__all__ = ['AccountingLock', 'ReconMark']


class AccountingLock(models.Model):
    """No voucher dated on or before ``lock_date`` can be created, changed, finalized, reverted or deleted."""
    municipality = models.OneToOneField('main.Municipality', on_delete=models.CASCADE, related_name='accounting_lock')
    lock_date = models.DateField(null=True, blank=True, verbose_name='قفل تا تاریخ')
    set_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    set_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'قفل تاریخ حسابداری'
        verbose_name_plural = 'قفل‌های تاریخ حسابداری'


class ReconMark(models.Model):
    """A voucher line of a bank/cash account that appears on the bank statement (ticked in the reconciliation)."""
    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='recon_marks')
    line = models.OneToOneField('main.VoucherLine', on_delete=models.CASCADE, related_name='recon_mark')
    marked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    marked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'تیک مغایرت‌گیری'
        verbose_name_plural = 'تیک‌های مغایرت‌گیری'
