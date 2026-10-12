"""Read-only checks for the server panel "services" tab: outgoing email, domain DNS/SSL, runtime limits.

Nothing here changes the server. DNS lookups go to the system resolver with a minimal
standard-library client (A, MX and TXT only), so no new dependency is needed.
"""
import ipaddress
import os
import random
import socket
import ssl
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

import django
from django.conf import settings
from django.db import connection

TYPES = {'A': 1, 'MX': 15, 'TXT': 16}
DEV_HOSTS = {'localhost', '127.0.0.1', '0.0.0.0', 'testserver', '[::1]'}


# ---- email ----

def email_settings():
    """Outgoing mail settings with the password hidden."""
    return {
        'backend': settings.EMAIL_BACKEND.rsplit('.', 2)[-2],
        'host': settings.EMAIL_HOST, 'port': settings.EMAIL_PORT,
        'user': settings.EMAIL_HOST_USER or '—', 'password_set': bool(settings.EMAIL_HOST_PASSWORD),
        'security': 'SSL' if settings.EMAIL_USE_SSL else 'STARTTLS' if settings.EMAIL_USE_TLS else 'none',
        'from': settings.DEFAULT_FROM_EMAIL,
        'configured': settings.EMAIL_HOST not in ('', 'localhost', '127.0.0.1'),
    }


# ---- domains ----

def site_domains():
    """Public domains the site answers on (ALLOWED_HOSTS and SITE_URL), without dev hosts or bare IPs."""
    names = set()
    for host in list(settings.ALLOWED_HOSTS) + [settings.SITE_URL.split('://')[-1].split('/')[0]]:
        host = host.lstrip('.').split(':')[0].lower()
        if not host or host in DEV_HOSTS or '*' in host:
            continue
        try:
            ipaddress.ip_address(host)
        except ValueError:
            names.add(host)
    return sorted(names)


def _nameserver():
    try:
        with open('/etc/resolv.conf') as handle:
            for line in handle:
                parts = line.split()
                if len(parts) >= 2 and parts[0] == 'nameserver':
                    return parts[1]
    except OSError:
        pass
    return '127.0.0.53'


def _read_name(data, offset):
    labels, jumped, end = [], False, offset
    for _ in range(64):                         # bounded: a malformed packet cannot loop forever
        length = data[offset]
        if length & 0xC0 == 0xC0:
            if not jumped:
                end = offset + 2
            offset, jumped = struct.unpack('>H', data[offset:offset + 2])[0] & 0x3FFF, True
            continue
        if length == 0:
            return '.'.join(labels), (end if jumped else offset + 1)
        labels.append(data[offset + 1:offset + 1 + length].decode('ascii', 'replace'))
        offset += length + 1
    raise ValueError('name too long')


def dns_query(name, rtype, timeout=3.0, server=None):
    """Answers for ``name`` (A: IPs, MX: 'prio host', TXT: strings). Raises OSError/ValueError on failure."""
    qid = random.randint(0, 0xFFFF)
    question = b''.join(bytes([len(p)]) + p.encode('idna') for p in name.rstrip('.').split('.')) + b'\0'
    edns = b'\0' + struct.pack('>HHIH', 41, 4096, 0, 0)     # EDNS0: allow 4 KB UDP replies (long TXT records)
    packet = struct.pack('>HHHHHH', qid, 0x0100, 1, 0, 0, 1) + question + struct.pack('>HH', TYPES[rtype], 1) + edns
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(packet, (server or _nameserver(), 53))
        data = sock.recv(4096)
    rid, flags, qd, an = struct.unpack('>HHHH', data[:8])
    if rid != qid:
        raise ValueError('mismatched DNS reply')
    if flags & 0x000F == 3:
        return []                                # NXDOMAIN
    if flags & 0x0200 and not an:
        raise ValueError('truncated DNS reply')
    offset = 12
    for _ in range(qd):
        _, offset = _read_name(data, offset)
        offset += 4
    answers = []
    for _ in range(an):
        _, offset = _read_name(data, offset)
        atype, _, _, rdlength = struct.unpack('>HHIH', data[offset:offset + 10])
        offset += 10
        rdata = data[offset:offset + rdlength]
        if atype == TYPES[rtype] == 1 and rdlength == 4:
            answers.append(socket.inet_ntoa(rdata))
        elif atype == TYPES[rtype] == 15:
            answers.append(f'{struct.unpack(">H", rdata[:2])[0]} {_read_name(data, offset + 2)[0]}')
        elif atype == TYPES[rtype] == 16:
            parts, i = [], 0
            while i < len(rdata):
                parts.append(rdata[i + 1:i + 1 + rdata[i]].decode('utf-8', 'replace'))
                i += 1 + rdata[i]
            answers.append(''.join(parts))
        offset += rdlength
    return answers


def ssl_expiry(host, timeout=5.0):
    """Days until the certificate served on host:443 expires, and its expiry date."""
    context = ssl.create_default_context()
    with socket.create_connection((host, 443), timeout=timeout) as raw:
        with context.wrap_socket(raw, server_hostname=host) as tls:
            not_after = tls.getpeercert()['notAfter']
    expires = datetime.fromtimestamp(ssl.cert_time_to_seconds(not_after), tz=timezone.utc)
    return (expires - datetime.now(timezone.utc)).days, expires


def _safe(func, *args):
    try:
        return func(*args), None
    except (OSError, ValueError, KeyError, IndexError, struct.error, ssl.SSLError) as error:
        return None, str(error) or error.__class__.__name__


def domain_report(domain):
    """DNS and certificate facts for one domain, with Persian hints for what is missing."""
    a, a_err = _safe(dns_query, domain, 'A')
    mx, mx_err = _safe(dns_query, domain, 'MX')
    txt, _ = _safe(dns_query, domain, 'TXT')
    dmarc, _ = _safe(dns_query, f'_dmarc.{domain}', 'TXT')
    cert, cert_err = _safe(ssl_expiry, domain)
    spf = [t for t in (txt or []) if t.lower().startswith('v=spf1')]
    dmarc = [t for t in (dmarc or []) if t.lower().startswith('v=dmarc1')]
    hints = []
    if a_err or mx_err:
        hints.append('پرس‌وجوی DNS از سرور ناموفق بود.')
    if not mx:
        hints.append('رکورد MX ندارد؛ ایمیل به این دامنه نمی‌رسد.')
    if mx and not spf:
        hints.append('رکورد SPF ندارد؛ ایمیل‌های ارسالی ممکن است اسپم شوند.')
    if mx and not dmarc:
        hints.append('رکورد DMARC ندارد.')
    if cert and cert[0] < 15:
        hints.append('گواهی SSL کمتر از ۱۵ روز دیگر منقضی می‌شود؛ تمدید خودکار certbot را بررسی کنید.')
    return {'domain': domain, 'a': a or [], 'mx': mx or [], 'spf': spf, 'dmarc': dmarc,
            'cert_days': cert[0] if cert else None, 'cert_expires': cert[1] if cert else None,
            'cert_error': cert_err, 'dns_error': a_err or mx_err, 'hints': hints}


# ---- runtime and limits ----

def _read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def _gunicorn_processes():
    count, rss = 0, 0
    proc = Path('/proc')
    if not proc.is_dir():
        return None, None
    for pid in proc.iterdir():
        if not pid.name.isdigit():
            continue
        cmd = _read(pid / 'cmdline')
        if cmd and 'gunicorn' in cmd:
            count += 1
            for line in (_read(pid / 'status') or '').splitlines():
                if line.startswith('VmRSS:'):
                    rss += int(line.split()[1]) * 1024
    return count, rss


def runtime():
    memory_max = _read('/sys/fs/cgroup/memory.max')
    cpu_max = _read('/sys/fs/cgroup/cpu.max')
    workers, workers_rss = _gunicorn_processes()
    try:
        import resource                         # Unix only; the dev machine may be Windows
        soft_files = resource.getrlimit(resource.RLIMIT_NOFILE)[0]
    except ImportError:
        soft_files = None
    from main.ratelimit import LIMITS
    return {
        'python': sys.version.split()[0], 'django': django.get_version(),
        'debug': settings.DEBUG, 'database': connection.vendor,
        'cache': settings.CACHES['default']['BACKEND'].rsplit('.', 1)[-1],
        'docker': os.path.exists('/.dockerenv'),
        'memory_limit': None if memory_max in (None, 'max') else int(memory_max),
        'cpu_limit': None if not cpu_max or cpu_max.startswith('max') else
        round(int(cpu_max.split()[0]) / int(cpu_max.split()[1]), 2),
        'gunicorn_processes': workers, 'gunicorn_rss': workers_rss,
        'open_files_limit': soft_files,
        'max_upload': getattr(settings, 'MAX_FILE_SIZE', None) or settings.FILE_UPLOAD_MAX_MEMORY_SIZE,
        'throttles': [(prefix, limit, window) for prefix, (limit, window) in LIMITS.items()],
    }
