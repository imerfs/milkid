"""Audit trail and configurable access levels of the accounting workspace. Imported at the end of main/models.py."""
from django.conf import settings
from django.db import models

__all__ = ['AuditEvent', 'AccessRule']


class AuditEvent(models.Model):
    """One change to an accounting record, or a sign-in/sign-out. Written by main/audit.py; never edited."""
    ACTIONS = [('create', 'ایجاد'), ('update', 'ویرایش'), ('delete', 'حذف'), ('login', 'ورود'), ('logout', 'خروج'),
               ('login_failed', 'ورود ناموفق')]

    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, null=True, blank=True, related_name='audit_events')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    username = models.CharField(max_length=150, blank=True, verbose_name='کاربر')
    action = models.CharField(max_length=20, choices=ACTIONS, verbose_name='عملیات')
    model = models.CharField(max_length=60, blank=True, verbose_name='نوع رکورد')
    object_id = models.CharField(max_length=40, blank=True)
    summary = models.CharField(max_length=300, blank=True, verbose_name='شرح')
    changes = models.JSONField(default=dict, blank=True, verbose_name='تغییرات')
    ip = models.GenericIPAddressField(null=True, blank=True)
    at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='زمان')

    class Meta:
        verbose_name = 'رویداد ممیزی'
        verbose_name_plural = 'رویدادهای ممیزی'
        ordering = ['-at', '-id']
        indexes = [models.Index(fields=['municipality', '-at'])]


class AccessRule(models.Model):
    """How much of one area of the accounting workspace a role may use in one municipality (none / view / edit)."""
    LEVELS = [('none', 'بدون دسترسی'), ('view', 'فقط مشاهده'), ('edit', 'مشاهده و ویرایش')]

    municipality = models.ForeignKey('main.Municipality', on_delete=models.CASCADE, related_name='access_rules')
    role = models.CharField(max_length=20)
    area = models.CharField(max_length=30)
    level = models.CharField(max_length=10, choices=LEVELS, default='edit')

    class Meta:
        verbose_name = 'سطح دسترسی حسابداری'
        verbose_name_plural = 'سطوح دسترسی حسابداری'
        constraints = [models.UniqueConstraint(fields=['municipality', 'role', 'area'], name='uniq_access_rule')]
