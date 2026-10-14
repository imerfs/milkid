"""Admin mailbox: sending through SMTP, storing messages, and optional IMAP fetching.

Sending uses Django's EMAIL_* settings. Fetching needs IMAP_HOST (plus IMAP_USER, IMAP_PASSWORD,
IMAP_PORT=993) in .env; without it the inbox only holds messages from the site's support form.
"""
import imaplib
import logging
from email import message_from_bytes, policy
from email.utils import parseaddr

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.core.validators import validate_email

from main.models import MailMessage

log = logging.getLogger('django.security.serverpanel')
MAX_BODY = 20000
MAX_FETCH = 50


def imap_configured():
    return bool(getattr(settings, 'IMAP_HOST', ''))


def parse_recipients(text):
    """Valid addresses from a comma/semicolon/space separated string; ValueError on a bad one."""
    items = [part.strip() for part in (text or '').replace(';', ',').replace('\n', ',').split(',') if part.strip()]
    if not items or len(items) > 10:
        raise ValueError('بین ۱ تا ۱۰ گیرنده وارد کنید.')
    for item in items:
        try:
            validate_email(item)
        except ValidationError:
            raise ValueError(f'نشانی ایمیل معتبر نیست: {item[:80]}') from None
    return items


def send(to_text, subject, body, user=None):
    """Send and record in the sent folder (failures are kept, flagged). Returns the MailMessage."""
    recipients = parse_recipients(to_text)
    subject, body = (subject or '').strip()[:200], (body or '').strip()
    if not subject or not body or len(body) > MAX_BODY:
        raise ValueError('موضوع و متن پیام لازم است (حداکثر ۲۰٬۰۰۰ نویسه).')
    record = MailMessage(folder='sent', source='compose', sender=settings.DEFAULT_FROM_EMAIL,
                         recipients=', '.join(recipients), subject=subject, body=body, user=user, is_read=True)
    try:
        EmailMessage(subject, body, None, recipients).send(fail_silently=False)
    except Exception as error:   # SMTP/socket failure: keep the text so the admin can retry
        record.failed, record.error = True, str(error)[:300]
        log.warning('mailbox: sending to %s failed: %s', record.recipients, error)
    record.save()
    return record


def store_raw(raw):
    """Store one RFC 822 message in the inbox unless its Message-ID is already known. Returns it or None."""
    msg = message_from_bytes(raw, policy=policy.default)
    message_id = (msg['Message-ID'] or '').strip()[:255]
    if message_id and MailMessage.objects.filter(message_id=message_id).exists():
        return None
    part = msg.get_body(preferencelist=('plain', 'html'))
    body = part.get_content() if part is not None else ''
    return MailMessage.objects.create(
        folder='inbox', source='imap', sender=parseaddr(str(msg['From'] or ''))[1][:320],
        recipients=str(msg['To'] or '')[:1000], subject=str(msg['Subject'] or '')[:200],
        body=str(body)[:MAX_BODY], message_id=message_id)


def fetch_imap():
    """Pull unseen messages from the configured IMAP mailbox. Returns how many were new."""
    if not imap_configured():
        raise ValueError('دریافت ایمیل تنظیم نشده است (IMAP_HOST در فایل .env).')
    new = 0
    try:
        box = imaplib.IMAP4_SSL(settings.IMAP_HOST, settings.IMAP_PORT, timeout=15)
        try:
            box.login(settings.IMAP_USER, settings.IMAP_PASSWORD)
            box.select('INBOX')
            _, data = box.search(None, 'UNSEEN')
            for number in data[0].split()[:MAX_FETCH]:
                _, parts = box.fetch(number, '(BODY.PEEK[])')
                if store_raw(parts[0][1]):
                    new += 1
                box.store(number, '+FLAGS', '\\Seen')
        finally:
            try:
                box.logout()
            except Exception:
                pass
    except (imaplib.IMAP4.error, OSError) as error:
        raise ValueError(f'اتصال به سرور ایمیل ناموفق بود: {error}') from None
    return new
