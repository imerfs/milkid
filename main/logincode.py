"""Password-less login by a one-time code sent to the user's email.

A code lives 10 minutes, works once and survives 5 wrong guesses. Only an HMAC of it is stored.
Accounts are matched by email only when exactly one active user owns it, so a shared address
never lets one person sign in as another. Request/verify POSTs are throttled per IP by
``main.ratelimit`` (the URLs sit under ``/login/``).
"""
import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.utils import timezone

from main.models import LoginCode

TTL = timedelta(minutes=10)
COOLDOWN = timedelta(seconds=60)
MAX_ATTEMPTS = 5
DIGITS = 6


def _hash(user_id, code):
    return hmac.new(settings.SECRET_KEY.encode(), f'{user_id}:{code}'.encode(), hashlib.sha256).hexdigest()


def user_for_email(email):
    email = (email or '').strip()
    if not email or len(email) > 254:
        return None
    users = list(User.objects.filter(email__iexact=email, is_active=True)[:2])
    return users[0] if len(users) == 1 else None


def issue(email):
    """Email a fresh code if the address belongs to exactly one active user. Returns True when sent.
    Callers show the same answer either way so addresses cannot be enumerated."""
    user = user_for_email(email)
    if user is None:
        return False
    now = timezone.now()
    if LoginCode.objects.filter(user=user, created_at__gt=now - COOLDOWN).exists():
        return False
    LoginCode.objects.filter(user=user, used_at__isnull=True).update(used_at=now)   # older codes die
    code = str(secrets.randbelow(10 ** DIGITS)).zfill(DIGITS)
    LoginCode.objects.create(user=user, code_hash=_hash(user.id, code), expires_at=now + TTL)
    send_mail('کد ورود به ملک آیدی',
              f'کد ورود شما: {code}\nاین کد ۱۰ دقیقه معتبر است و فقط یک بار کار می‌کند. '
              'اگر شما درخواست نداده‌اید، این ایمیل را نادیده بگیرید.',
              None, [user.email], fail_silently=True)
    return True


def verify(email, code):
    """The user for a correct, unused, unexpired code, else None. Counts wrong guesses."""
    user = user_for_email(email)
    code = (code or '').strip()
    if user is None or len(code) != DIGITS or not code.isdigit():
        return None
    now = timezone.now()
    entry = LoginCode.objects.filter(user=user, used_at__isnull=True, expires_at__gt=now).first()
    if entry is None or entry.attempts >= MAX_ATTEMPTS:
        return None
    if not hmac.compare_digest(entry.code_hash, _hash(user.id, code)):
        LoginCode.objects.filter(pk=entry.pk).update(attempts=entry.attempts + 1)
        return None
    if LoginCode.objects.filter(pk=entry.pk, used_at__isnull=True).update(used_at=now) != 1:
        return None   # lost a race with a parallel request: single use
    return user
