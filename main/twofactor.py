"""Time-based one-time passwords (RFC 6238, the Google Authenticator kind) for admin logins.

Standard library only. ``TwoFactorMiddleware`` keeps a user who has confirmed 2FA on the
verify page until the current session has passed a code.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from django.shortcuts import redirect

STEP = 30
DIGITS = 6
SESSION_KEY = 'two_factor_ok'


def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode()


def code_at(secret, step):
    digest = hmac.new(base64.b32decode(secret), struct.pack('>Q', step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10 ** DIGITS).zfill(DIGITS)


def matching_step(secret, code, now=None, last_step=None):
    """Time step the code belongs to (±1 step for clock drift), or None. Steps at or before
    ``last_step`` are refused so a code cannot be replayed."""
    code = (code or '').strip().replace(' ', '')
    if len(code) != DIGITS or not code.isdigit():
        return None
    current = int((now if now is not None else time.time()) // STEP)
    for step in (current - 1, current, current + 1):
        if (last_step is None or step > last_step) and hmac.compare_digest(code_at(secret, step), code):
            return step
    return None


def provisioning_uri(secret, username, issuer='MelkID'):
    return f'otpauth://totp/{quote(issuer)}:{quote(username)}?secret={secret}&issuer={quote(issuer)}'


def confirmed_device(user):
    from main.models import TwoFactorDevice
    return TwoFactorDevice.objects.filter(user=user, confirmed=True).first()


class TwoFactorMiddleware:
    ALLOWED = ('/2fa/verify/', '/logout/', '/static/', '/media/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if (user is not None and user.is_authenticated and not request.session.get(SESSION_KEY)
                and not request.path.startswith(self.ALLOWED) and confirmed_device(user)):
            return redirect('main:two_factor_verify')
        return self.get_response(request)
