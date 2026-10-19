"""Line-table forms of the trade screens (invoice, stock document, formula, consignment): a form head plus a table of
product rows, drawn in a modal and read back from a POST. Presentation only.

A ``LineForm`` is told its head fields and its columns ``(name, label, kind)``. The kind of each column decides how a posted
cell is read, so a view never lists which columns are money, text or dates:

* ``product``: the id of a product of the municipality (the first column, required on every non-blank row)
* ``money``: whole rials          * ``date``: a Jalali date, blank = none
* ``text``: kept as typed         * anything else (``qty``, ``pct``): a plain number as text
"""
from django.shortcuts import render

from main.accounting import ledger
from main.accounting.parse import digits, parse_amount, parse_jalali
from main.models import Product
from main.office.errors import Invalid
from main.views.accounting_panel import PANEL


def num(text):
    """Quantity or percentage text typed by a person -> plain ASCII digits and a dot."""
    return digits(text).replace('٫', '.').replace('٬', '').replace(',', '').replace(' ', '')


def read_cell(kind, raw):
    if kind == 'text':
        return raw
    if kind == 'date':
        return parse_jalali(raw) if raw else None
    if kind == 'money':
        return parse_amount(raw)
    return num(raw)


def read_lines(post, muni, columns):
    """The filled rows of a line table as dicts (blank rows skipped); the first column is the product."""
    names = [c[0] for c in columns]
    kinds = {c[0]: c[2] for c in columns}
    products = {str(p.id): p for p in Product.objects.filter(municipality=muni)}
    posted = {n: post.getlist(n) for n in names}
    rows = []
    for i in range(max((len(v) for v in posted.values()), default=0)):
        raw = {n: (posted[n][i].strip() if i < len(posted[n]) else '') for n in names}
        if not any(raw.values()):
            continue
        if raw[names[0]] not in products:
            raise Invalid(f'ردیف {i + 1}: کالا را انتخاب کنید.')
        item = {names[0]: products[raw[names[0]]]}
        for n in names[1:]:
            item[n] = read_cell(kinds[n], raw[n])
        rows.append(item)
    return rows


def posted_rows(post, names):
    """The rows exactly as posted, to draw the form again after an error."""
    columns = {n: post.getlist(n) for n in names}
    return [{n: (columns[n][i] if i < len(columns[n]) else '') for n in names}
            for i in range(max((len(v) for v in columns.values()), default=0))]


class LineForm:
    def __init__(self, *, title, action, fields, columns, hint='', subtitle='', submit='ذخیره', price_kind='sell', show_totals=False):
        self.title, self.action, self.fields, self.columns = title, action, fields, columns
        self.hint, self.subtitle, self.submit, self.price_kind, self.show_totals = hint, subtitle, submit, price_kind, show_totals
        self.names = [c[0] for c in columns]

    def show(self, request, *, values=None, rows=None, error=None, status=200):
        muni = ledger.municipality_of(request.user)
        products = [{'id': p.id, 'label': f'{p.code} - {p.name}', 'price': int(p.sell_price), 'buy': int(p.buy_price)}
                    for p in Product.objects.filter(municipality=muni, is_active=True)]
        ctx = {'title': self.title, 'subtitle': self.subtitle, 'action': self.action, 'fields': [(f, f.options(muni)) for f in self.fields],
               'columns': self.columns, 'p': values or {}, 'rows': rows or [{}], 'error': error, 'submit': self.submit, 'products': products,
               'show_totals': self.show_totals, 'hint': self.hint, 'price_kind': self.price_kind}
        return render(request, PANEL + 'trade_form.html', ctx, status=status)

    def lines(self, request, muni):
        return read_lines(request.POST, muni, self.columns)

    def fail(self, request, exc):
        """The form again with what was posted and the error."""
        return self.show(request, values=request.POST, rows=posted_rows(request.POST, self.names), error=str(exc), status=exc.status)
