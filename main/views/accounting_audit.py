"""Audit trail and access-level screens of the accountant workspace (mayor and admins only).
Rules live in main/audit.py and main/accounting/access_levels.py."""
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from openpyxl import Workbook

from main.accounting import access_levels, ledger
from main.accounting.parse import jalali_str
from main.models import AuditEvent
from main.office.errors import OfficeError
from main.office.roles import is_admin
from main.views.accounting_panel import _date_param, _done, _failed
from main.views.accounting_views import _cell, _guard

PAGE = 50
EXPORT_MAX = 5000


def is_mayor(user):
    return is_admin(user) or ledger.role_of(user) == 'dehyari'


def tab_access(request, year, ctx):
    ctx['access_allowed'] = is_mayor(request.user)
    if not ctx['access_allowed']:
        return
    levels = access_levels.rules_for(ctx['muni'])
    ctx['access_rows'] = [(key, label, levels[key]) for key, label, _ in access_levels.AREAS]
    ctx['level_options'] = [('none', 'بدون دسترسی'), ('view', 'فقط مشاهده'), ('edit', 'مشاهده و ویرایش')]


def _events(request, muni):
    g = request.GET
    qs = AuditEvent.objects.filter(municipality=muni)
    if g.get('user', '').strip():
        qs = qs.filter(username__icontains=g['user'].strip())
    if g.get('model', '').strip():
        qs = qs.filter(model=g['model'].strip())
    if g.get('action') in dict(AuditEvent.ACTIONS):
        qs = qs.filter(action=g['action'])
    if g.get('q', '').strip():
        qs = qs.filter(summary__icontains=g['q'].strip())
    date_from, err_from = _date_param(request, 'date_from')
    date_to, err_to = _date_param(request, 'date_to')
    if date_from:
        qs = qs.filter(at__date__gte=date_from)
    if date_to:
        qs = qs.filter(at__date__lte=date_to)
    return qs.select_related('user'), err_from or err_to


def tab_audit(request, year, ctx):
    ctx['audit_allowed'] = is_mayor(request.user)
    if not ctx['audit_allowed']:
        return
    events, error = _events(request, ctx['muni'])
    ctx.update(audit_error=error, audit_actions=AuditEvent.ACTIONS, export_query=request.GET.urlencode(),
               audit_models=sorted(set(AuditEvent.objects.filter(municipality=ctx['muni']).exclude(model='').values_list('model', flat=True))),
               page=Paginator(events, PAGE).get_page(request.GET.get('page')))


@_guard()
def acc_p_audit_export(request):
    if not is_mayor(request.user):
        return HttpResponse('فقط دهیار', status=403, content_type='text/plain; charset=utf-8')
    events, error = _events(request, ledger.municipality_of(request.user))
    if error:
        return HttpResponse(error, status=400, content_type='text/plain; charset=utf-8')
    wb = Workbook()
    ws = wb.active
    ws.title = 'audit'
    ws.sheet_view.rightToLeft = True
    ws.append(['زمان', 'کاربر', 'عملیات', 'نوع رکورد', 'شناسه', 'شرح', 'تغییرات', 'نشانی'])
    for e in events[:EXPORT_MAX]:
        ws.append([jalali_str(e.at.date()) + ' ' + e.at.strftime('%H:%M'), _cell(e.username), e.get_action_display(), e.model,
                   e.object_id, _cell(e.summary), _cell('; '.join(f'{k}: {a} ← {b}' for k, (b, a) in e.changes.items())), e.ip or ''])
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="audit-log.xlsx"'
    wb.save(response)
    return response


@_guard()
@require_POST
def acc_p_access_save(request):
    levels = {key: request.POST.get(f'area_{key}', 'edit') for key in access_levels.AREA_KEYS}
    try:
        access_levels.save_rules(request.user, levels)
    except OfficeError as exc:
        return _failed(exc)
    return _done('سطوح دسترسی حسابدار ذخیره شد.')


BUILDERS = {'access': tab_access, 'audit': tab_audit}
