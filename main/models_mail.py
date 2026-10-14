"""Email login codes, the SMS gateway settings and the admin mailbox (see main.logincode, main.sms, main.mailbox)."""
from django.contrib.auth.models import User
from django.db import models

__all__ = ['LoginCode', 'SmsConfig', 'MailMessage']


class LoginCode(models.Model):
    """One-time code emailed to a user for password-less login. Only an HMAC of the code is stored."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='login_codes')
    code_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']


class SmsConfig(models.Model):
    """Single-row settings of the SMS provider's HTTP API. The API key is stored encrypted (main.sms)."""
    base_url = models.URLField(max_length=300, blank=True, verbose_name='نشانی API')
    api_key_enc = models.TextField(blank=True)
    sender = models.CharField(max_length=40, blank=True, verbose_name='شمارهٔ فرستنده')
    auth_header = models.CharField(max_length=40, default='Authorization')
    auth_prefix = models.CharField(max_length=20, blank=True, default='Bearer ')
    to_field = models.CharField(max_length=30, default='to')
    text_field = models.CharField(max_length=30, default='message')
    sender_field = models.CharField(max_length=30, default='from')
    enabled = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)


class MailMessage(models.Model):
    """A message in the admin mailbox: received (site support form or IMAP), sent, or in the trash."""
    FOLDERS = [('inbox', 'صندوق ورودی'), ('sent', 'ارسال‌شده'), ('trash', 'زباله‌دان')]
    SOURCES = [('support', 'پشتیبانی سایت'), ('imap', 'دریافت از سرور'), ('compose', 'نوشته‌شده')]

    folder = models.CharField(max_length=10, choices=FOLDERS, default='inbox', db_index=True)
    prev_folder = models.CharField(max_length=10, blank=True)
    source = models.CharField(max_length=10, choices=SOURCES, default='compose')
    sender = models.CharField(max_length=320, blank=True)
    recipients = models.TextField(blank=True)
    subject = models.CharField(max_length=200, blank=True)
    body = models.TextField(blank=True)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='mail_messages')
    message_id = models.CharField(max_length=255, blank=True, db_index=True)
    is_read = models.BooleanField(default=False)
    failed = models.BooleanField(default=False)
    error = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at', '-id']
