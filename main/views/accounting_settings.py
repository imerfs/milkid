"""Financial settings page (تنظیمات مالی): cost centers, standard descriptions, signatories."""
from django.http import Http404
from django.views.decorators.http import require_POST

from main.accounting import formspec, ledger, lookups
from main.accounting.formspec import Field
from main.models import CostCenter, Signatory, StandardDescription
from main.office.errors import OfficeError
from main.views.accounting_finance import _form_modal, _url
from main.views.accounting_panel import _done, _failed
from main.views.accounting_views import _guard

# kind -> (title, fields, add function, delete function, queryset getter, row cells)
KINDS = {
    'center': ('مرکز هزینه', [Field('code', 'کد', 'text', size=1, maxlength=10), Field('title', 'شرح', 'text', size=3, maxlength=100)],
               lookups.add_cost_center, lookups.delete_cost_center, lookups.cost_centers, CostCenter,
               lambda o: [o.code, o.title], ['کد', 'شرح']),
    'description': ('شرح استاندارد', [Field('kind', 'نوع', 'select', choices=StandardDescription.KINDS, size=1),
                                      Field('code', 'کد', 'text', size=1, maxlength=10),
                                      Field('text', 'شرح', 'text', size=2, maxlength=300)],
                    lookups.add_description, lookups.delete_description, lookups.descriptions, StandardDescription,
                    lambda o: [o.get_kind_display(), o.code, o.text], ['نوع', 'کد', 'شرح']),
    'signatory': ('امضاکننده', [Field('name', 'نام', 'text', size=2, maxlength=150), Field('position', 'سمت', 'text', size=2, maxlength=100)],
                  lookups.add_signatory, lookups.delete_signatory, lookups.signatories, Signatory,
                  lambda o: [o.name, o.position], ['نام', 'سمت']),
}


def tab_settings(request, year, ctx):
    ctx['sections'] = [
        {'title': title + ('‌ها' if key != 'center' else 'ها'), 'new_url': _url('acc_p_setting_new', key), 'label': title,
         'columns': columns, 'rows': [{'cells': cells(o), 'delete': _url('acc_p_setting_delete', key, o.id)}
                                      for o in getter(request.user)]}
        for key, (title, _f, _a, _d, getter, _m, cells, columns) in KINDS.items()]


@_guard()
def acc_p_setting_new(request, kind):
    if kind not in KINDS:
        raise Http404()
    title, fields, add, *_ = KINDS[kind]
    kw = dict(title=f'{title} جدید', fields=fields, action=_url('acc_p_setting_new', kind))
    if request.method != 'POST':
        return _form_modal(request, **kw)
    try:
        data = formspec.parse(ledger.municipality_of(request.user), fields, request.POST)
        add(request.user, **data)
    except OfficeError as exc:
        return _form_modal(request, values=request.POST, error=str(exc), status=exc.status, **kw)
    return _done(f'{title} ثبت شد.')


@_guard()
@require_POST
def acc_p_setting_delete(request, kind, obj_id):
    if kind not in KINDS:
        raise Http404()
    _t, _f, _a, delete, _g, model, *_ = KINDS[kind]
    obj = model.objects.filter(pk=obj_id, municipality=ledger.municipality_of(request.user)).first()
    if obj is None:
        raise Http404()
    try:
        delete(request.user, obj)
    except OfficeError as exc:
        return _failed(exc)
    return _done('حذف شد.')


BUILDERS = {'settings': tab_settings}
