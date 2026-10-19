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


@register.filter
def get(mapping, key):
    """mapping[key] for dicts and QueryDicts, '' when absent (used by the generic modal form)."""
    try:
        value = mapping.get(key, '')
    except AttributeError:
        return ''
    return '' if value is None else value


@register.filter
def words(value):
    """12345 -> the amount in Persian words (for cheques and receipts); empty when it is not a whole number."""
    from main.accounting import tools
    try:
        return tools.number_to_words(int(value))
    except (TypeError, ValueError, Exception):
        return ''


@register.simple_tag
def acc_menu():
    """The workspace menu (sidebar groups and phone chips), from the tab registry."""
    from main.accounting import tabs
    return tabs.menu()
