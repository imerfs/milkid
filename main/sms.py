"""SMS through a provider's HTTP API, configured by an admin (``SmsConfig``).

Provider-agnostic: one POST (JSON) with the recipient, text and sender in field names the admin
sets, and the key in an auth header. Other code calls ``send_sms(phone, text)``. The API key is
encrypted at rest with a key derived from SECRET_KEY and is never rendered back.
"""
import base64
import hashlib
import ipaddress
import json
import re
import socket
import urllib.request
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

from main.models import SmsConfig

TIMEOUT = 10
MOBILE = re.compile(r'^(?:\+98|0098|98|0)?(9\d{9})$')
PERSIAN_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def _fernet():
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(('sms|' + settings.SECRET_KEY).encode()).digest()))


def get_config():
    return SmsConfig.objects.first() or SmsConfig()


def set_api_key(config, key):
    config.api_key_enc = _fernet().encrypt(key.encode()).decode() if key else ''


def api_key(config):
    try:
        return _fernet().decrypt(config.api_key_enc.encode()).decode() if config.api_key_enc else ''
    except InvalidToken:   # SECRET_KEY changed: the key must be entered again
        return ''


def normalize_mobile(phone):
    """Iranian mobile as 09xxxxxxxxx, or None."""
    match = MOBILE.match((phone or '').translate(PERSIAN_DIGITS).replace(' ', '').replace('-', ''))
    return '0' + match.group(1) if match else None


def check_url(url):
    """Error text if the URL is not a public https endpoint (stops pointing the gateway at internal services)."""
    parsed = urlparse(url or '')
    if parsed.scheme != 'https' or not parsed.hostname:
        return 'نشانی API باید با https شروع شود.'
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(parsed.hostname, parsed.port or 443)}
    except OSError:
        return 'نام دامنهٔ نشانی API پیدا نشد.'
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return 'نشانی API نباید به شبکهٔ داخلی اشاره کند.'
    return ''


def _post(url, headers, payload):
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method='POST')
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.status


def send_sms(phone, text):
    """(ok, detail). Never raises: a gateway failure must not break the caller's flow."""
    config = get_config()
    if not (config.enabled and config.base_url and api_key(config)):
        return False, 'پنل پیامک تنظیم یا فعال نشده است.'
    mobile = normalize_mobile(phone)
    if not mobile:
        return False, 'شمارهٔ موبایل معتبر نیست.'
    text = (text or '').strip()
    if not text or len(text) > 600:
        return False, 'متن پیامک خالی یا بیش از حد طولانی است.'
    error = check_url(config.base_url)
    if error:
        return False, error
    headers = {'Content-Type': 'application/json', config.auth_header: f'{config.auth_prefix}{api_key(config)}'}
    payload = {config.to_field: mobile, config.text_field: text}
    if config.sender:
        payload[config.sender_field] = config.sender
    try:
        status = _post(config.base_url, headers, payload)
    except Exception as error:   # HTTP/DNS/timeout errors are reported, not raised
        return False, f'ارسال ناموفق بود: {error}'
    return (True, 'ارسال شد.') if 200 <= status < 300 else (False, f'پاسخ نامعتبر از پنل پیامک: {status}')
