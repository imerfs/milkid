"""Letters linked to accounting records and per-municipality accounting backups. Imported at the end of main/models.py."""
from django.conf import settings
from django.db import models
from django.db.models import Q

from main.storage import PrivateStorage

__all__ = ['LetterLink', 'BackupFile']


class LetterLink(models.Model):
    """An office letter attached to a voucher, contract or instalment plan, so the paper trail is one click away."""
    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='letter_links')
    letter = models.ForeignKey('main.Letter', on_delete=models.CASCADE, related_name='accounting_links')
    voucher = models.ForeignKey('main.Voucher', on_delete=models.CASCADE, null=True, blank=True, related_name='letter_links')
    contract = models.ForeignKey('main.Contract', on_delete=models.CASCADE, null=True, blank=True, related_name='letter_links')
    plan = models.ForeignKey('main.InstallmentPlan', on_delete=models.CASCADE, null=True, blank=True, related_name='letter_links')
    linked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'نامه مرتبط'
        verbose_name_plural = 'نامه‌های مرتبط'
        ordering = ['-id']
        constraints = [
            models.CheckConstraint(
                condition=(Q(voucher__isnull=False, contract__isnull=True, plan__isnull=True)
                           | Q(voucher__isnull=True, contract__isnull=False, plan__isnull=True)
                           | Q(voucher__isnull=True, contract__isnull=True, plan__isnull=False)),
                name='letter_link_one_target'),
            models.UniqueConstraint(fields=['letter', 'voucher'], condition=Q(voucher__isnull=False), name='uniq_letter_voucher'),
            models.UniqueConstraint(fields=['letter', 'contract'], condition=Q(contract__isnull=False), name='uniq_letter_contract'),
            models.UniqueConstraint(fields=['letter', 'plan'], condition=Q(plan__isnull=False), name='uniq_letter_plan'),
        ]


class BackupFile(models.Model):
    """A downloadable snapshot of one municipality's accounting data (see main/accounting/backup.py)."""
    KINDS = [('manual', 'دستی'), ('auto', 'خودکار'), ('before_restore', 'پیش از بازیابی'), ('before_yearend', 'پیش از عملیات سال مالی')]

    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='backup_files')
    kind = models.CharField(max_length=20, choices=KINDS, default='manual')
    file = models.FileField(upload_to='accounting_backups/%Y/%m/', storage=PrivateStorage())
    size = models.PositiveIntegerField(default=0)
    rows = models.PositiveIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True)
    note = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'نسخه پشتیبان حسابداری'
        verbose_name_plural = 'نسخه‌های پشتیبان حسابداری'
        ordering = ['-id']
