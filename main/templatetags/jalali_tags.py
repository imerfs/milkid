"""
Template tags for Jalali/Persian date handling
"""
from django import template
from django.utils import timezone
import jdatetime
from datetime import datetime, date

register = template.Library()

# Persian month names
PERSIAN_MONTHS = [
    'فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
    'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند'
]

# Persian weekday names
PERSIAN_WEEKDAYS = [
    'شنبه', 'یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنج‌شنبه', 'جمعه'
]

def _local(value):
    """An aware datetime is shown in the site's time zone (Tehran), not in UTC."""
    from django.utils import timezone       # pylint: disable=import-outside-toplevel
    if timezone.is_aware(value):
        return timezone.localtime(value).replace(tzinfo=None)
    return value


@register.filter
def jalali_date(value, format_string='%Y/%m/%d'):
    """
    Convert Gregorian date to Jalali/Persian date (always YYYY/MM/DD with Persian digits unless another format is given)
    Usage: {{ date_field|jalali_date }}
    Usage: {{ date_field|jalali_date:"%Y/%m/%d" }}
    """
    if not value:
        return ''
    
    try:
        if isinstance(value, str):
            # Try to parse string as datetime
            try:
                value = datetime.fromisoformat(value.replace('T', ' '))
            except ValueError:
                try:
                    value = datetime.strptime(value, '%Y-%m-%d')
                except ValueError:
                    return value
        
        if isinstance(value, datetime):
            jalali_dt = jdatetime.datetime.fromgregorian(datetime=_local(value))
            return persian_numbers(jalali_dt.strftime(format_string))
        elif isinstance(value, date):
            jalali_date = jdatetime.date.fromgregorian(date=value)
            return persian_numbers(jalali_date.strftime(format_string))
        
        return value
    except Exception:
        return value

@register.filter
def jalali_datetime(value, format_string='%Y/%m/%d %H:%M'):
    """
    Convert Gregorian datetime to Jalali/Persian datetime
    Usage: {{ datetime_field|jalali_datetime }}
    Usage: {{ datetime_field|jalali_datetime:"%Y/%m/%d %H:%M:%S" }}
    """
    if not value:
        return ''
    
    try:
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace('T', ' '))
            except ValueError:
                try:
                    value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    return value
        
        if isinstance(value, datetime):
            jalali_dt = jdatetime.datetime.fromgregorian(datetime=_local(value))
            return persian_numbers(jalali_dt.strftime(format_string))

        return value
    except Exception:
        return value

@register.filter
def jalali_verbose(value):
    """
    Convert date to verbose Persian format
    Usage: {{ date_field|jalali_verbose }}
    Output: "پنج‌شنبه ۱۵ مهر ۱۴۰۳"
    """
    if not value:
        return ''
    
    try:
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace('T', ' '))
            except ValueError:
                try:
                    value = datetime.strptime(value, '%Y-%m-%d')
                except ValueError:
                    return value
        
        if isinstance(value, datetime):
            value = value.date()
        
        if isinstance(value, date):
            jalali_date = jdatetime.date.fromgregorian(date=value)
            
            # Get weekday name
            weekday = PERSIAN_WEEKDAYS[jalali_date.weekday()]
            
            # Get month name
            month = PERSIAN_MONTHS[jalali_date.month - 1]
            
            # Convert numbers to Persian
            day = persian_numbers(str(jalali_date.day))
            year = persian_numbers(str(jalali_date.year))
            
            return f"{weekday} {day} {month} {year}"
        
        return value
    except Exception:
        return value

@register.filter
def jalali_short(value):
    """
    Convert date to short Persian format
    Usage: {{ date_field|jalali_short }}
    Output: "۱۵ مهر ۱۴۰۳"
    """
    if not value:
        return ''
    
    try:
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace('T', ' '))
            except ValueError:
                try:
                    value = datetime.strptime(value, '%Y-%m-%d')
                except ValueError:
                    return value
        
        if isinstance(value, datetime):
            value = value.date()
        
        if isinstance(value, date):
            jalali_date = jdatetime.date.fromgregorian(date=value)
            
            # Get month name
            month = PERSIAN_MONTHS[jalali_date.month - 1]
            
            # Convert numbers to Persian
            day = persian_numbers(str(jalali_date.day))
            year = persian_numbers(str(jalali_date.year))
            
            return f"{day} {month} {year}"
        
        return value
    except Exception:
        return value

@register.filter
def persian_numbers(value):
    """
    Convert English numbers to Persian numbers
    Usage: {{ "123"|persian_numbers }}
    Output: "۱۲۳"
    """
    if not value:
        return value
    
    persian_digits = '۰۱۲۳۴۵۶۷۸۹'
    english_digits = '0123456789'
    
    value_str = str(value)
    for i, digit in enumerate(english_digits):
        value_str = value_str.replace(digit, persian_digits[i])
    
    return value_str

@register.filter
def english_numbers(value):
    """
    Convert Persian numbers to English numbers
    Usage: {{ "۱۲۳"|english_numbers }}
    Output: "123"
    """
    if not value:
        return value
    
    persian_digits = '۰۱۲۳۴۵۶۷۸۹'
    english_digits = '0123456789'
    
    value_str = str(value)
    for i, digit in enumerate(persian_digits):
        value_str = value_str.replace(digit, english_digits[i])
    
    return value_str

@register.filter
def time_since_jalali(value):
    """
    Show time since in Persian
    Usage: {{ datetime_field|time_since_jalali }}
    Output: "۲ ساعت پیش", "۳ روز پیش"
    """
    if not value:
        return ''
    
    try:
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace('T', ' '))
            except ValueError:
                return value
        
        if not isinstance(value, datetime):
            return value
        
        # Make timezone aware if needed
        if timezone.is_naive(value):
            value = timezone.make_aware(value)
        
        now = timezone.now()
        diff = now - value
        
        seconds = diff.total_seconds()
        
        if seconds < 60:
            return "همین الان"
        elif seconds < 3600:  # Less than 1 hour
            minutes = int(seconds // 60)
            return f"{persian_numbers(minutes)} دقیقه پیش"
        elif seconds < 86400:  # Less than 1 day
            hours = int(seconds // 3600)
            return f"{persian_numbers(hours)} ساعت پیش"
        elif seconds < 2592000:  # Less than 30 days
            days = int(seconds // 86400)
            return f"{persian_numbers(days)} روز پیش"
        elif seconds < 31536000:  # Less than 1 year
            months = int(seconds // 2592000)
            return f"{persian_numbers(months)} ماه پیش"
        else:
            years = int(seconds // 31536000)
            return f"{persian_numbers(years)} سال پیش"
    
    except Exception:
        return value

@register.simple_tag
def jalali_now(format_string='%Y/%m/%d %H:%M'):
    """
    Get current Jalali date/time
    Usage: {% jalali_now %}
    Usage: {% jalali_now "%Y/%m/%d" %}
    """
    now = timezone.localtime()
    jalali_now = jdatetime.datetime.fromgregorian(datetime=now.replace(tzinfo=None))
    return persian_numbers(jalali_now.strftime(format_string))

@register.simple_tag
def jalali_today(format_string='%Y/%m/%d'):
    """
    Get today's Jalali date
    Usage: {% jalali_today %}
    Usage: {% jalali_today "%Y/%m/%d" %}
    """
    today = timezone.localdate()
    jalali_today = jdatetime.date.fromgregorian(date=today)
    return persian_numbers(jalali_today.strftime(format_string))