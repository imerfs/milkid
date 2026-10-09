from django import template
from django.utils.safestring import mark_safe
import jdatetime

register = template.Library()

@register.filter
def persian_date(value, format_str="Y/m/d"):
    """تبدیل تاریخ میلادی به شمسی"""
    if not value:
        return ""
    
    try:
        # تبدیل به jdatetime
        if hasattr(value, 'date'):
            # اگر datetime object باشد
            jalali_date = jdatetime.datetime.fromgregorian(datetime=value)
        else:
            # اگر date object باشد
            jalali_date = jdatetime.date.fromgregorian(date=value)
        
        # فرمت کردن
        if format_str == "Y/m/d":
            return f"{jalali_date.year}/{jalali_date.month:02d}/{jalali_date.day:02d}"
        elif format_str == "H:i":
            if hasattr(jalali_date, 'hour'):
                return f"{jalali_date.hour:02d}:{jalali_date.minute:02d}"
            else:
                return ""
        elif format_str == "Y/m/d - H:i":
            if hasattr(jalali_date, 'hour'):
                return f"{jalali_date.year}/{jalali_date.month:02d}/{jalali_date.day:02d} - {jalali_date.hour:02d}:{jalali_date.minute:02d}"
            else:
                return f"{jalali_date.year}/{jalali_date.month:02d}/{jalali_date.day:02d}"
        elif format_str == "Y/m/d H:i":
            if hasattr(jalali_date, 'hour'):
                return f"{jalali_date.year}/{jalali_date.month:02d}/{jalali_date.day:02d} {jalali_date.hour:02d}:{jalali_date.minute:02d}"
            else:
                return f"{jalali_date.year}/{jalali_date.month:02d}/{jalali_date.day:02d}"
        else:
            # سایر فرمت‌ها را به صورت پیش‌فرض می‌گیریم
            return f"{jalali_date.year}/{jalali_date.month:02d}/{jalali_date.day:02d}"
    except:
        return str(value)

@register.filter  
def persian_date_verbose(value):
    """تاریخ شمسی به صورت کامل با نام ماه"""
    if not value:
        return ""
    
    try:
        if hasattr(value, 'date'):
            jalali_date = jdatetime.datetime.fromgregorian(datetime=value)
        else:
            jalali_date = jdatetime.date.fromgregorian(date=value)
        
        month_names = {
            1: "فروردین", 2: "اردیبهشت", 3: "خرداد", 4: "تیر",
            5: "مرداد", 6: "شهریور", 7: "مهر", 8: "آبان", 
            9: "آذر", 10: "دی", 11: "بهمن", 12: "اسفند"
        }
        
        return f"{jalali_date.day} {month_names[jalali_date.month]} {jalali_date.year}"
    except:
        return str(value)

@register.filter
def dict_get(mapping, key):
    """{{ mapping|dict_get:key }} for dict lookups with a variable key."""
    return mapping.get(key, '') if mapping else ''
