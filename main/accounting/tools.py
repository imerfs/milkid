"""Small calculators of the accountant workspace: a number in words, Jalali/Gregorian dates and a loan instalment table.

Pure functions, no database: the screens call them through tiny JSON endpoints so there is one tested implementation.
"""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import jdatetime

from main.office.errors import Invalid

ONES = ['', 'یک', 'دو', 'سه', 'چهار', 'پنج', 'شش', 'هفت', 'هشت', 'نه', 'ده', 'یازده', 'دوازده', 'سیزده', 'چهارده', 'پانزده',
        'شانزده', 'هفده', 'هجده', 'نوزده']
TENS = ['', '', 'بیست', 'سی', 'چهل', 'پنجاه', 'شصت', 'هفتاد', 'هشتاد', 'نود']
HUNDREDS = ['', 'صد', 'دویست', 'سیصد', 'چهارصد', 'پانصد', 'ششصد', 'هفتصد', 'هشتصد', 'نهصد']
SCALES = ['', 'هزار', 'میلیون', 'میلیارد', 'تریلیون', 'کوادریلیون']
MAX_WORDS = 10 ** 18 - 1
MAX_MONTHS = 360


def _below_thousand(n):
    parts = []
    if n >= 100:
        parts.append(HUNDREDS[n // 100])
        n %= 100
    if n >= 20:
        parts.append(TENS[n // 10])
        n %= 10
    if n:
        parts.append(ONES[n])
    return ' و '.join(parts)


def number_to_words(n):
    """12345 -> «دوازده هزار و سیصد و چهل و پنج». Whole numbers up to 10^18 - 1, negatives get «منفی»."""
    if isinstance(n, bool) or n != int(n):
        raise Invalid('فقط عدد صحیح را می‌توان به حروف نوشت.')
    n = int(n)
    if abs(n) > MAX_WORDS:
        raise Invalid('عدد از ۱۰ به توان ۱۸ بزرگ‌تر است.')
    if n == 0:
        return 'صفر'
    sign, n = ('منفی ', -n) if n < 0 else ('', n)
    groups = []
    while n:
        groups.append(n % 1000)
        n //= 1000
    parts = []
    for index in range(len(groups) - 1, -1, -1):
        if groups[index]:
            words = _below_thousand(groups[index])
            parts.append(f'{words} {SCALES[index]}'.strip())
    return sign + ' و '.join(parts)


def amount_in_words(n):
    return f'{number_to_words(n)} ریال'


def convert_date(*, jalali=None, gregorian=None):
    """Both spellings of one day: ``{'jalali': '1404/05/01', 'gregorian': '2025-07-23', 'weekday': 'چهارشنبه'}``."""
    try:
        if jalali:
            y, m, d = (int(x) for x in str(jalali).translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')).replace('-', '/').split('/'))
            day = jdatetime.date(y, m, d)
        elif gregorian:
            day = jdatetime.date.fromgregorian(date=date.fromisoformat(str(gregorian).strip()))
        else:
            raise Invalid('یک تاریخ وارد کنید.')
    except (ValueError, TypeError):
        raise Invalid('تاریخ نامعتبر است.')
    return {'jalali': day.strftime('%Y/%m/%d'), 'gregorian': day.togregorian().isoformat(), 'weekday': day.j_weekdays_fa[day.weekday()]
            if hasattr(day, 'j_weekdays_fa') else day.strftime('%A')}


def _rial(value):
    return int(Decimal(value).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def loan(amount, annual_rate, months, *, rows=None):
    """Equal monthly instalments (annuity). ``annual_rate`` is a percent (18 for 18%). Whole rials; the last instalment
    absorbs the rounding so the balance ends at zero.

    Returns ``{'payment', 'total', 'interest', 'schedule': [{'n', 'payment', 'interest', 'principal', 'balance'}]}``.
    """
    try:
        principal, rate, n = Decimal(str(amount)), Decimal(str(annual_rate)), int(months)
    except Exception:
        raise Invalid('مبلغ، نرخ و تعداد اقساط را درست وارد کنید.')
    if principal <= 0 or principal >= Decimal(10) ** 16 or principal != principal.to_integral_value():
        raise Invalid('مبلغ وام باید عدد صحیح مثبت (ریال) باشد.')
    if rate < 0 or rate > 1000:
        raise Invalid('نرخ سود باید بین ۰ تا ۱۰۰۰ درصد باشد.')
    if not 1 <= n <= MAX_MONTHS:
        raise Invalid(f'تعداد اقساط باید بین ۱ تا {MAX_MONTHS} باشد.')
    monthly = rate / 12 / 100
    payment = principal / n if monthly == 0 else principal * monthly / (1 - (1 + monthly) ** -n)
    payment = Decimal(_rial(payment))
    balance, schedule, total = principal, [], Decimal(0)
    for i in range(1, n + 1):
        interest = Decimal(_rial(balance * monthly))
        due = payment if i < n else balance + interest
        principal_part = due - interest
        balance -= principal_part
        total += due
        schedule.append({'n': i, 'payment': int(due), 'interest': int(interest), 'principal': int(principal_part),
                         'balance': int(balance)})
    shown = schedule if rows is None else schedule[:rows]
    return {'payment': int(payment), 'total': int(total), 'interest': int(total - principal), 'schedule': shown,
            'count': n}


PAPERS = {
    'a4': ('A4', '210mm 297mm'),
    'a5': ('A5', '148mm 210mm'),
    'cheque': ('چک (۱۷۵×۸۰ میلی‌متر)', '175mm 80mm'),
    'pos80': ('رسید ۸۰ میلی‌متری', '80mm 200mm'),
}
