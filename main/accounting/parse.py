"""Turn what people type (Persian digits, separators, Jalali dates) into clean values; raise Invalid otherwise."""
import re
from datetime import date

import jdatetime

from main.office.errors import Invalid

_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
_SEPARATORS = str.maketrans('', '', ',٬ ‌ ')


def digits(text):
    """Latin digits, whatever script the user typed in."""
    return str(text or '').translate(_DIGITS).strip()


def parse_amount(text):
    """Whole non-negative rials; blank means 0. Sign, decimals and exponents are refused."""
    clean = digits(text).translate(_SEPARATORS)
    if not clean:
        return 0
    if not clean.isdigit():
        raise Invalid('مبلغ باید فقط رقم باشد.')
    return int(clean)


def parse_jalali(text):
    match = re.fullmatch(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', digits(text))
    if not match:
        raise Invalid('تاریخ را به صورت شمسی وارد کنید، مثل ۱۴۰۴/۰۲/۱۱.')
    try:
        return jdatetime.date(*map(int, match.groups())).togregorian()
    except ValueError:
        raise Invalid('تاریخ نامعتبر است.')


def parse_int_or_none(text):
    text = digits(text)
    return int(text) if text.isdigit() else None


def jalali_str(value):
    return jdatetime.date.fromgregorian(date=value).strftime('%Y/%m/%d') if isinstance(value, date) else ''
