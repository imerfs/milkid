"""One row per page view, for the admin server panel (visitors, devices, the heat map). Written by main.siteextras.PageViewMiddleware; pruned after 90 days."""
from django.conf import settings
from django.db import models

__all__ = ['SiteVisit']


class SiteVisit(models.Model):
    KINDS = [('desktop', 'رایانه'), ('mobile', 'موبایل'), ('tablet', 'تبلت'), ('bot', 'ربات'), ('unknown', 'نامشخص')]

    ip = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    path = models.CharField(max_length=200)
    kind = models.CharField(max_length=8, choices=KINDS, default='unknown')
    device = models.CharField(max_length=120, blank=True)
    model_name = models.CharField(max_length=80, blank=True)
    at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-at', '-id']
