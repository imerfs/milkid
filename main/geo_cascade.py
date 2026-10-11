"""Province -> county -> district -> settlement dropdowns.

The forms ask `/geo/options/` when a select changes; the answer is the select elements below it, swapped in by
HTMX. The same module sets the form querysets, so what the page offers is exactly what the form accepts.
"""
from django import forms
from django.http import Http404, HttpResponse
from django.urls import reverse
from django.views.decorators.http import require_GET

ORDER = ('province', 'county', 'district', 'dehestan', 'city_village')
FORM_SUFFIX = {'citizen': '_citizen', 'role': '_role'}
FORM_LEVELS = {                       # the selects each form has, top to bottom
    'citizen': ('province', 'county', 'district', 'city_village'),
    'role': ('province', 'county', 'district', 'dehestan', 'city_village'),
}
PARENT = {'county': 'province', 'district': 'county', 'dehestan': 'district', 'city_village': 'district'}
EMPTY_LABEL = {
    'county': 'ابتدا استان را انتخاب کنید',
    'district': 'ابتدا شهرستان را انتخاب کنید',
    'dehestan': 'ابتدا بخش را انتخاب کنید',
    'city_village': 'ابتدا بخش را انتخاب کنید',
}
FILLED_LABEL = {
    'county': 'شهرستان را انتخاب کنید',
    'district': 'بخش را انتخاب کنید',
    'dehestan': 'دهستان را انتخاب کنید',
    'city_village': 'شهر یا روستا را انتخاب کنید',
}
TYPE_LABEL = {'city': 'شهر', 'village': 'روستا'}


def to_int(value):
    value = str(value or '').strip()
    return int(value) if value.isdigit() else None


def children(level, parent_id):
    """Rows of ``level`` under ``parent_id`` (nothing when the parent is unknown)."""
    from main.models import CityVillage, County, Dehestan, District
    if parent_id is None:
        return []
    if level == 'county':
        return County.objects.filter(province_id=parent_id).order_by('name')
    if level == 'district':
        return District.objects.filter(county_id=parent_id).order_by('name')
    if level == 'dehestan':
        return Dehestan.objects.filter(district_id=parent_id).order_by('name')
    if level == 'city_village':
        return CityVillage.objects.filter(district_id=parent_id).order_by('settlement_type', 'name')
    return []


def label(row):
    kind = getattr(row, 'settlement_type', None)
    return f'{row.name} ({TYPE_LABEL[kind]})' if kind in TYPE_LABEL else row.name


def ancestors(level):
    """The chain above ``level`` (top first), ending with ``level`` itself."""
    chain = [level]
    while chain[0] in PARENT:
        chain.insert(0, PARENT[chain[0]])
    return chain


def select_attrs(form_key, level):
    """id plus the HTMX wiring: a change in this select refreshes the selects below it."""
    suffix = FORM_SUFFIX[form_key]
    attrs = {'id': f'id_{level}{suffix}'}
    if level in PARENT.values():                       # only selects that have something below them
        attrs.update({
            'hx-get': f"{reverse('main:geo_options')}?form={form_key}&changed={level}",
            'hx-trigger': 'change',
            'hx-swap': 'none',
            'hx-include': ', '.join(f'#id_{name}{suffix}' for name in ancestors(level)),
        })
    return attrs


def apply_to_form(form, form_key):
    """Wire a registration form: HTMX attributes, and querysets limited to the places the user already chose."""
    from main.models import Province
    levels = FORM_LEVELS[form_key]
    for level in levels:
        form.fields[level].widget.attrs.update(select_attrs(form_key, level))

    data = form.data if form.is_bound else {}
    chosen = {name: to_int(data.get(name)) for name in ('province', 'county', 'district')}
    form.fields['province'].queryset = Province.objects.order_by('name')
    for level in levels[1:]:
        parent = chosen[PARENT[level]]
        form.fields[level].queryset = children(level, parent) if parent is not None else children(level, -1)
        widget = form.fields[level].widget
        if parent is None:
            widget.attrs['disabled'] = 'disabled'
        else:
            widget.attrs.pop('disabled', None)


def _form_class(form_key):
    from main.forms import CitizenRegistrationForm, CustomUserCreationForm
    return {'citizen': CitizenRegistrationForm, 'role': CustomUserCreationForm}[form_key]


@require_GET
def geo_options(request):
    """The selects below the one that changed, as out-of-band HTMX swaps."""
    form_key, changed = request.GET.get('form'), request.GET.get('changed')
    if form_key not in FORM_SUFFIX or changed not in PARENT.values():
        raise Http404
    value = to_int(request.GET.get(changed))
    base_form = _form_class(form_key)()

    html = []
    for level in FORM_LEVELS[form_key]:
        if changed not in ancestors(level)[:-1]:
            continue                                   # not below the select that changed
        rows = list(children(level, value)) if PARENT[level] == changed else []
        attrs = {k: v for k, v in base_form.fields[level].widget.attrs.items() if k != 'disabled'}
        attrs.update(select_attrs(form_key, level))
        attrs['hx-swap-oob'] = 'true'
        if not rows:
            attrs['disabled'] = 'disabled'
        choices = [('', FILLED_LABEL[level] if rows else EMPTY_LABEL[level])] + [(row.pk, label(row)) for row in rows]
        html.append(forms.Select(attrs=attrs, choices=choices).render(level, ''))
    return HttpResponse('\n'.join(html))
