"""Template helpers of the messenger."""
import jdatetime
from django import template
from django.utils import timezone

register = template.Library()
_FA = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


@register.filter
def mg_when(value):
    """Time for today, Jalali date otherwise (as chat apps do), in Persian digits."""
    if not value:
        return ''
    local = timezone.localtime(value)
    if local.date() == timezone.localdate():
        return local.strftime('%H:%M').translate(_FA)
    return jdatetime.date.fromgregorian(date=local.date()).strftime('%Y/%m/%d').translate(_FA)


@register.filter
def mg_day(value):
    """'۳۰ مهر ۱۴۰۵' for the date separators."""
    local = timezone.localtime(value)
    j = jdatetime.date.fromgregorian(date=local.date())
    return f'{j.day} {j.j_months_fa[j.month - 1]} {j.year}'.translate(_FA)


@register.filter
def mg_clock(value):
    return timezone.localtime(value).strftime('%H:%M').translate(_FA)


@register.filter
def mg_color(name):
    """One of six avatar colours, stable per name."""
    return sum(ord(c) for c in (name or '؟')) % 6
