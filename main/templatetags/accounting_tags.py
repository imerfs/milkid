from django import template

register = template.Library()
_PERSIAN = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


@register.filter
def rial(value):
    """12345678 -> ۱۲٬۳۴۵٬۶۷۸ (Persian digits, thousands separators); empty and zero show ۰."""
    try:
        return f'{int(value or 0):,}'.replace(',', '٬').translate(_PERSIAN)
    except (TypeError, ValueError):
        return ''


@register.filter
def fa(value):
    """Persian digits for any text, zero included."""
    return str(value if value is not None else '').translate(_PERSIAN)
