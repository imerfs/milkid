"""Official letters: sending rules, mailboxes, numbering, attachments."""
import os
import uuid

import jdatetime
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Max, Q
from django.utils import timezone
from datetime import timedelta

from main.models import Letter, LetterAttachment, LetterRecipient
from main.notifications import notify
from main.office.directory import STAFF_ROLES, allowed_recipients, org_of, village_of    # noqa: F401  (re-exported: other modules import them from here)
from main.office.errors import Forbidden, Invalid, NotFound, RateLimited
from main.validators import validate_file_content, validate_file_extension, validate_file_size

HOURLY_CAP = 30
MAX_RECIPIENTS = 20
MAX_ATTACHMENTS = 5
PRIORITIES = {value for value, _ in Letter.PRIORITIES}


def _recipients(sender, ids, kind):
    ids = [int(i) for i in ids if str(i).isdigit()]
    if sender.pk in ids:
        raise Invalid('نامه را نمی‌توان برای خودتان فرستاد.')
    if len(set(ids)) != len(ids):
        ids = list(dict.fromkeys(ids))
    users = {u.pk: u for u in allowed_recipients(sender).filter(pk__in=ids)}
    if len(users) != len(ids):
        raise Forbidden('یکی از گیرنده‌ها برای شما مجاز نیست.')
    return [(users[i], kind) for i in ids]


def _check_files(files):
    if len(files) > MAX_ATTACHMENTS:
        raise Invalid(f'حداکثر {MAX_ATTACHMENTS} پیوست مجاز است.')
    for f in files:
        try:
            validate_file_extension(f)
            validate_file_size(f)
            validate_file_content(f)
        except ValidationError as exc:
            raise Invalid(f'پیوست «{f.name}» پذیرفته نشد: {" ".join(exc.messages)}')


def _next_sequence(village, year):
    return (Letter.objects.filter(village=village, year=year).aggregate(m=Max('sequence'))['m'] or 0) + 1


def _publish(letter):
    """Give the draft its number and mark it sent; retries if two letters raced for the same number."""
    year = jdatetime.datetime.fromgregorian(datetime=timezone.now()).year
    for _ in range(5):
        try:
            with transaction.atomic():
                letter.year, letter.sequence = year, _next_sequence(letter.village, year)
                letter.status, letter.sent_at = 'sent', timezone.now()
                letter.save(update_fields=['year', 'sequence', 'status', 'sent_at'])
            return
        except IntegrityError:
            continue
    raise Invalid('شماره‌گذاری نامه ممکن نشد؛ دوباره تلاش کنید.')


def _notify(letter):
    title = 'نامه‌ی محرمانه‌ی جدید' if letter.confidential else f'نامه‌ی جدید: {letter.subject[:60]}'
    sender = letter.sender.get_full_name() or letter.sender.username
    for row in letter.recipients.select_related('user'):
        notify(row.user, title, f'از طرف {sender}، شماره {letter.number}', kind='new_message')


def _clean(subject, body, priority):
    subject, body = (subject or '').strip(), (body or '').strip()
    if not subject or len(subject) > 200:
        raise Invalid('موضوع نامه الزامی است و باید حداکثر ۲۰۰ نویسه باشد.')
    if not body or len(body) > 20000:
        raise Invalid('متن نامه الزامی است و باید حداکثر ۲۰٬۰۰۰ نویسه باشد.')
    if priority not in PRIORITIES:
        raise Invalid('اولویت نامعتبر است.')
    return subject, body


def compose(sender, *, to, cc=(), subject, body, priority='normal', confidential=False, files=(),
            parent=None, token=None, send=True):
    """Create a draft or send a letter. Repeating the same ``token`` returns the first letter."""
    if token:
        existing = Letter.objects.filter(sender=sender, client_token=token).first()
        if existing:
            return existing
    subject, body = _clean(subject, body, priority)
    people = _recipients(sender, to, 'to') + [p for p in _recipients(sender, cc, 'cc') if p[0].pk not in {int(i) for i in to if str(i).isdigit()}]
    if send and not people:
        raise Invalid('دست‌کم یک گیرنده انتخاب کنید.')
    if len(people) > MAX_RECIPIENTS:
        raise Invalid(f'حداکثر {MAX_RECIPIENTS} گیرنده مجاز است.')
    if send:
        since = timezone.now() - timedelta(hours=1)
        if Letter.objects.filter(sender=sender, sent_at__gte=since).count() >= HOURLY_CAP:
            raise RateLimited(f'در هر ساعت حداکثر {HOURLY_CAP} نامه می‌توانید بفرستید.')
    files = list(files)
    _check_files(files)
    try:
        with transaction.atomic():
            letter = Letter.objects.create(
                sender=sender, village=village_of(sender), sender_org=org_of(sender), subject=subject, body=body, priority=priority,
                confidential=bool(confidential), parent=parent, client_token=token or None)
            LetterRecipient.objects.bulk_create([LetterRecipient(letter=letter, user=u, kind=k) for u, k in people])
            for f in files:
                LetterAttachment.objects.create(letter=letter, file=f, original_name=os.path.basename(f.name)[:255], size=f.size)
            if send:
                _publish(letter)
    except IntegrityError:        # same token arrived twice at the same moment
        existing = Letter.objects.filter(sender=sender, client_token=token).first()
        if existing:
            return existing
        raise
    if send:
        _notify(letter)
    return letter


def send_draft(sender, letter_id):
    with transaction.atomic():
        letter = Letter.objects.select_related('sender').filter(pk=letter_id, sender=sender).first()
        if letter is None:
            raise NotFound('نامه پیدا نشد.')
        if letter.status == 'sent':
            return letter, False
        if not letter.recipients.exists():
            raise Invalid('برای ارسال، دست‌کم یک گیرنده لازم است.')
        since = timezone.now() - timedelta(hours=1)
        if Letter.objects.filter(sender=sender, sent_at__gte=since).count() >= HOURLY_CAP:
            raise RateLimited(f'در هر ساعت حداکثر {HOURLY_CAP} نامه می‌توانید بفرستید.')
        _publish(letter)
    _notify(letter)
    return letter, True


def visible_to(user):
    """Letters the user may open: their own (any status) and sent letters addressed to them."""
    return Letter.objects.filter(Q(sender=user) | Q(recipients__user=user, status='sent')).distinct()


def get_for(user, letter_id):
    letter = visible_to(user).select_related('sender', 'sender__profile', 'parent').filter(pk=letter_id).first()
    if letter is None:
        raise NotFound('نامه پیدا نشد.')
    return letter


def open_letter(user, letter):
    """Mark as read for a recipient (never for the sender looking at their own letter)."""
    LetterRecipient.objects.filter(letter=letter, user=user, read_at__isnull=True).update(read_at=timezone.now())


def toggle_archive(user, letter_id):
    row = LetterRecipient.objects.filter(letter_id=letter_id, user=user, letter__status='sent').first()
    if row is None:
        raise NotFound('نامه پیدا نشد.')
    row.archived = not row.archived
    row.save(update_fields=['archived'])
    return row.archived


def mailbox(user, box, *, q='', unread=False):
    if box == 'sent':
        qs = Letter.objects.filter(sender=user, status='sent')
    elif box == 'drafts':
        qs = Letter.objects.filter(sender=user, status='draft')
    else:
        qs = Letter.objects.filter(status='sent', recipients__user=user, recipients__archived=(box == 'archive'))
        if unread:
            qs = qs.filter(recipients__read_at__isnull=True)
    q = (q or '').strip()
    if q:
        qs = qs.filter(Q(subject__icontains=q) | Q(sender__first_name__icontains=q) | Q(sender__last_name__icontains=q))
    return qs.select_related('sender').order_by('-sent_at', '-created_at').distinct()


def unread_count(user):
    return LetterRecipient.objects.filter(user=user, read_at__isnull=True, archived=False, letter__status='sent').count()


def new_token():
    return str(uuid.uuid4())
