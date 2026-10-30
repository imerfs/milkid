"""Numbers for the server panel's visitors, sign-ins and heat-map tabs, from ``SiteVisit`` (page views) and ``AuditEvent`` (sign-ins)."""
import re
from collections import Counter
from datetime import timedelta

from django.db.models import Count, Max
from django.utils import timezone

from main.models import AuditEvent, SiteVisit

DAYS = ('شنبه', 'یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنجشنبه', 'جمعه')
SECTIONS = {'': 'صفحه‌ی اصلی', 'dashboard': 'داشبوردها', 'properties': 'املاک', 'property': 'ملک', 'services': 'خدمات', 'permits': 'پرونده‌های پروانه',
            'accounting': 'حسابداری', 'news': 'اخبار', 'login': 'ورود', 'register': 'ثبت‌نام', 'profile': 'پروفایل', 'chat': 'گفتگو', 'letters': 'نامه‌ها'}
LIMIT_ROWS = 50_000


def _since(days):
    return timezone.now() - timedelta(days=days)


def _human(qs):
    return qs.exclude(kind='bot')


def _alpha(count, top):
    return round(0.08 + 0.92 * (count / top), 2) if top else 0.08


def _pattern(path):
    """``/permits/12/pack/`` and ``/permits/97/pack/`` are the same page."""
    return re.sub(r'/\d+(?=/|$)', '/#', path)


def heatmap(days=30):
    """A week-by-hour grid of visits, the sections people use most and the busiest pages (bots left out)."""
    times = list(_human(SiteVisit.objects.filter(at__gte=_since(days))).values_list('at', 'path')[:LIMIT_ROWS])
    grid = [[0] * 24 for _ in DAYS]
    sections, pages = Counter(), Counter()
    for at, path in times:
        local = timezone.localtime(at)
        grid[(local.weekday() + 2) % 7][local.hour] += 1
        pattern = _pattern(path)
        pages[pattern] += 1
        sections[pattern.strip('/').split('/')[0]] += 1
    top = max((c for row in grid for c in row), default=0)
    rows = [{'day': DAYS[i], 'total': sum(row), 'cells': [{'hour': h, 'count': c, 'alpha': _alpha(c, top) if c else 0} for h, c in enumerate(row)]} for i, row in enumerate(grid)]
    total = sum(sections.values())
    top_section = max(sections.values(), default=0)
    top_page = max(pages.values(), default=0)
    return {
        'rows': rows, 'total': total, 'days': days,
        'sections': [{'name': SECTIONS.get(k, k or SECTIONS['']), 'key': k, 'count': c, 'pct': round(100 * c / total, 1) if total else 0, 'alpha': _alpha(c, top_section)}
                     for k, c in sections.most_common(24)],
        'pages': [{'path': p, 'count': c, 'width': round(100 * c / top_page), 'alpha': _alpha(c, top_page)} for p, c in pages.most_common(40)],
    }


def visitors(days=30):
    """The addresses and devices that came to the site, with what each did last."""
    qs = SiteVisit.objects.filter(at__gte=_since(days))
    ips = list(qs.values('ip').annotate(hits=Count('id'), last=Max('at')).order_by('-hits')[:60])
    seen = {}
    for row in qs.exclude(ip=None).order_by('-at').values('ip', 'device', 'user__username')[:LIMIT_ROWS]:
        entry = seen.setdefault(row['ip'], {'devices': Counter(), 'users': set()})
        entry['devices'][row['device']] += 1
        if row['user__username']:
            entry['users'].add(row['user__username'])
    for row in ips:
        info = seen.get(row['ip'], {'devices': Counter(), 'users': set()})
        row['devices'] = [d for d, _ in info['devices'].most_common(3)]
        row['users'] = sorted(info['users'])[:5]
    devices = list(_human(qs).exclude(device='').values('device', 'kind').annotate(hits=Count('id'), ips=Count('ip', distinct=True)).order_by('-hits')[:40])
    kinds = {row['kind']: row['hits'] for row in qs.values('kind').annotate(hits=Count('id'))}
    return {'ips': ips, 'devices': devices, 'kinds': kinds, 'total': qs.count(), 'unique_ips': qs.exclude(ip=None).values('ip').distinct().count(),
            'recent': list(qs.select_related('user')[:80]), 'days': days}


def logins(limit=200):
    """Who signed in (or failed to) from which address and device."""
    events = list(AuditEvent.objects.filter(action__in=('login', 'login_failed')).order_by('-at')[:limit])
    by_ip = {}
    for ev in events:
        row = by_ip.setdefault(ev.ip or '—', {'ip': ev.ip or '—', 'ok': 0, 'failed': 0, 'users': set(), 'last': ev.at})
        row['ok' if ev.action == 'login' else 'failed'] += 1
        if ev.username:
            row['users'].add(ev.username)
    summary = sorted(({**r, 'users': sorted(r['users'])[:6]} for r in by_ip.values()), key=lambda r: -(r['ok'] + r['failed']))[:40]
    return {'events': [{'at': e.at, 'username': e.username, 'ip': e.ip, 'ok': e.action == 'login', 'device': e.summary.partition(' | ')[2]} for e in events], 'summary': summary}
