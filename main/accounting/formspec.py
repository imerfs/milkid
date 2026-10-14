"""Tiny declarative forms for the accountant workspace: render a field list in a modal, parse what was posted.

The service layer stays the only place with business rules; this only turns posted text into typed values
(Persian digits, Jalali dates, whole rials, ids of rows of the same municipality) and names the field on failure.
"""
from main.accounting.parse import jalali_str, parse_amount, parse_int_or_none, parse_jalali
from main.office.errors import Invalid


class Field:
    """kind: text, textarea, date, amount, pct, select, fk, bool. `size` is the grid span (1, 2 or 4)."""

    def __init__(self, name, label, kind='text', *, required=True, choices=None, model=None, where=None, size=2,
                 placeholder='', maxlength=200, label_of=None):
        self.name, self.label, self.kind, self.required = name, label, kind, required
        self.choices, self.model, self.where, self.size = choices, model, where or {}, size
        self.placeholder, self.maxlength, self.label_of = placeholder, maxlength, label_of

    def options(self, muni):
        if self.kind == 'select':
            return list(self.choices)
        if self.kind == 'fk':
            qs = self.model.objects.filter(municipality=muni, **self.where)
            return [(o.pk, self.label_of(o) if self.label_of else str(o)) for o in qs]
        return []


def parse(muni, fields, post):
    """Typed values by field name. Raises Invalid naming the first bad field."""
    out = {}
    for f in fields:
        raw = (post.get(f.name) or '').strip()
        if f.kind == 'bool':
            out[f.name] = post.get(f.name) in ('on', '1', 'true')
            continue
        if not raw:
            if f.required:
                raise Invalid(f'{f.label} را وارد کنید.')
            out[f.name] = None if f.kind in ('date', 'fk') else ('' if f.kind in ('text', 'textarea', 'select') else 0)
            continue
        try:
            if f.kind == 'date':
                out[f.name] = parse_jalali(raw)
            elif f.kind == 'amount':
                out[f.name] = parse_amount(raw)
            elif f.kind == 'fk':
                pk = parse_int_or_none(raw)
                obj = f.model.objects.filter(municipality=muni, pk=pk, **f.where).first() if pk else None
                if obj is None:
                    raise Invalid('مقدار انتخاب‌شده معتبر نیست.')
                out[f.name] = obj
            elif f.kind == 'select':
                if raw not in dict(f.choices):
                    raise Invalid('مقدار انتخاب‌شده معتبر نیست.')
                out[f.name] = raw
            elif f.kind == 'pct':
                out[f.name] = raw
            else:
                out[f.name] = raw[:f.maxlength if f.kind == 'text' else 500]
        except Invalid as exc:
            raise Invalid(f'{f.label}: {exc}')
    return out


def initial(fields, obj):
    """Posted-style strings for editing an existing object."""
    values = {}
    for f in fields:
        v = getattr(obj, f.name, '')
        if f.kind == 'date':
            v = jalali_str(v)
        elif f.kind == 'fk':
            v = v.pk if v else ''
        values[f.name] = '' if v is None else v
    return values
