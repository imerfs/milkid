"""Name the device behind a User-Agent header: kind (mobile / tablet / desktop / bot), browser, operating system and, when the header says so, the model."""
import re

BOTS = re.compile(r'bot|crawl|spider|slurp|bingpreview|facebookexternalhit|curl|wget|python-requests|httpclient|monitor|uptime|headless|lighthouse', re.I)
BROWSERS = (('Edge', r'Edg(?:e|A|iOS)?/'), ('Opera', r'OPR/|Opera'), ('Samsung Internet', r'SamsungBrowser/'), ('Firefox', r'Firefox/|FxiOS/'),
            ('Chrome', r'Chrome/|CriOS/'), ('Safari', r'Safari/'))
ANDROID_MODEL = re.compile(r'Android [\d.]+; ([^;)]+?)(?: Build|\)|;)')


def parse(ua):
    """Return {'kind', 'browser', 'os', 'model', 'label'} for one User-Agent string."""
    ua = (ua or '')[:400]
    if not ua:
        return {'kind': 'unknown', 'browser': '', 'os': '', 'model': '', 'label': 'نامشخص'}
    if BOTS.search(ua):
        return {'kind': 'bot', 'browser': '', 'os': '', 'model': '', 'label': 'ربات / ابزار خودکار'}
    model = ''
    if 'iPad' in ua:
        os_name, kind, model = 'iPadOS', 'tablet', 'iPad'
    elif 'iPhone' in ua:
        os_name, kind, model = 'iOS', 'mobile', 'iPhone'
    elif 'Android' in ua:
        os_name = 'Android'
        kind = 'mobile' if 'Mobile' in ua else 'tablet'
        found = ANDROID_MODEL.search(ua)
        model = found.group(1).strip() if found else ''
        if model in ('K', 'Linux'):
            model = ''
    elif 'Windows' in ua:
        os_name, kind = 'Windows', 'desktop'
    elif 'Mac OS X' in ua or 'Macintosh' in ua:
        os_name, kind = 'macOS', 'desktop'
    elif 'CrOS' in ua:
        os_name, kind = 'ChromeOS', 'desktop'
    elif 'Linux' in ua or 'X11' in ua:
        os_name, kind = 'Linux', 'desktop'
    else:
        os_name, kind = '', 'desktop'
    browser = next((name for name, pattern in BROWSERS if re.search(pattern, ua)), '')
    parts = [browser, os_name]
    label = ' · '.join(p for p in parts if p) or 'نامشخص'
    if model:
        label = f'{model} — {label}'
    return {'kind': kind, 'browser': browser, 'os': os_name, 'model': model, 'label': label}
