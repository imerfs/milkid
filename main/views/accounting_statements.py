"""Financial statements and year-end operations of the accountant workspace. Rules live in main/accounting/statements
and main/accounting/yearend; these views only read the form, call them and draw fragments."""
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from openpyxl import Workbook

from main.accounting import ledger, statements, yearend
from main.accounting.parse import jalali_str, parse_jalali
from main.models import Voucher
from main.office.errors import OfficeError
from main.views.accounting_panel import PANEL, _done, _failed
from main.views.accounting_views import _cell, _guard

STATEMENTS = (('resources_uses', 'صورت منابع و مصارف'), ('balance_sheet', 'ترازنامه (صورت وضعیت مالی)'))
OPERATIONS = (('temp_closing', 'سند بستن حساب‌های موقت', 'منابع و مصارف را در حساب مازاد/کسری (۴۱۰) می‌بندد.',
               'fa-eraser'),
              ('closing', 'سند اختتامیه', 'مانده دارایی‌ها، بدهی‌ها و حقوق صاحبان سرمایه را در حساب اختتامیه (۴۱۱) می‌بندد.',
               'fa-flag-checkered'),
              ('opening', 'سند افتتاحیه', 'مانده‌های سال قبل را در حساب افتتاحیه (۱۱۱) به این سال منتقل می‌کند.',
               'fa-door-open'))


def _upto(request):
    """(date or None, error) from ?upto= (Jalali)."""
    text = request.GET.get('upto', '').strip()
    if not text:
        return None, None
    try:
        return parse_jalali(text), None
    except OfficeError as exc:
        return None, str(exc)


def tab_statements(request, year, ctx):
    key = request.GET.get('statement') if request.GET.get('statement') in dict(STATEMENTS) else 'resources_uses'
    upto, error = _upto(request)
    final_only = request.GET.get('final') == '1'
    ctx.update(statement_key=key, statement_list=STATEMENTS, final_only=final_only, upto=request.GET.get('upto', ''),
               statement_error=error, export_query=request.GET.urlencode())
    if error:
        return
    build = statements.resources_and_uses if key == 'resources_uses' else statements.balance_sheet
    ctx['statement'] = build(request.user, year, upto=upto, final_only=final_only)


def tab_yearend(request, year, ctx):
    info = yearend.overview(request.user, year)
    ctx.update(operations=[(k, title, hint, icon, info['existing'].get(k)) for k, title, hint, icon in OPERATIONS],
               temporary_count=info['temporary'], unbalanced=info['unbalanced'], has_previous=info['has_previous'])


def _sheet(ws, rows):
    for row in rows:
        ws.append([_cell(v) if isinstance(v, str) else (int(v) if hasattr(v, 'as_tuple') else v) for v in row])


@_guard()
def acc_p_statement_export(request, year_id, key):
    year = ledger.get_year(request.user, year_id)
    upto, error = _upto(request)
    if error or key not in dict(STATEMENTS):
        return HttpResponse(error or 'گزارش نامعتبر است.', status=400, content_type='text/plain; charset=utf-8')
    final_only = request.GET.get('final') == '1'
    wb = Workbook()
    ws = wb.active
    ws.sheet_view.rightToLeft = True
    if key == 'resources_uses':
        data = statements.resources_and_uses(request.user, year, upto=upto, final_only=final_only)
        ws.title = 'منابع و مصارف'
        ws.append(['کد', 'شرح', 'بودجه مصوب', 'عملکرد'])
        for part, label in (('resources', 'منابع'), ('uses', 'مصارف')):
            ws.append(['', label, '', ''])
            _sheet(ws, [[r['code'], '  ' * (r['depth'] - 1) + r['title'], r['budget'], r['amount']] for r in data[part]['rows']])
            _sheet(ws, [['', 'جمع ' + label, data[part]['budget'], data[part]['total']]])
        _sheet(ws, [['', 'مازاد (کسری)', data['budget_surplus'], data['surplus']]])
    else:
        data = statements.balance_sheet(request.user, year, upto=upto, final_only=final_only)
        ws.title = 'ترازنامه'
        ws.append(['کد', 'شرح', 'مبلغ'])
        ws.append(['', 'دارایی‌ها', ''])
        _sheet(ws, [[r['code'], '  ' * (r['depth'] - 1) + r['title'], r['amount']] for r in data['assets']])
        _sheet(ws, [['', 'جمع دارایی‌ها', data['total_assets']], ['', 'بدهی‌ها و حقوق صاحبان سرمایه', '']])
        _sheet(ws, [[r['code'], '  ' * (r['depth'] - 1) + r['title'], r['amount']] for r in data['claims']])
        _sheet(ws, [['', 'مازاد (کسری) سال جاری', data['surplus']], ['', 'جمع بدهی‌ها و حقوق', data['total_claims']],
                    ['', 'اختلاف', data['difference']]])
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="statement-{key}-{year.year}.xlsx"'
    wb.save(response)
    return response


# ---------- year-end operations ----------

def _preview(request, year, kind, error=None, status=200):
    ctx = {'year': year, 'kind': kind, 'title': dict((k, t) for k, t, _, _ in OPERATIONS).get(kind, ''), 'error': error}
    if error is None:
        try:
            data = yearend.plan(request.user, year, kind)
        except OfficeError as exc:
            ctx['error'], status = str(exc), exc.status
        else:
            ctx.update(plan=data, date_text=jalali_str(data['date']))
    return render(request, PANEL + 'yearend_preview.html', ctx, status=status)


@_guard()
def acc_p_yearend_preview(request, year_id, kind):
    return _preview(request, ledger.get_year(request.user, year_id), kind)


@_guard()
@require_POST
def acc_p_yearend_issue(request, year_id, kind):
    year = ledger.get_year(request.user, year_id)
    try:
        voucher = yearend.issue(request.user, year, kind)
    except OfficeError as exc:
        return _failed(exc)
    return _done(f'سند شماره {voucher.number} ({Voucher(kind=kind).get_kind_display()}) به‌صورت موقت صادر شد؛ پس از بررسی آن را قطعی کنید.')


@_guard()
@require_POST
def acc_p_year_close(request, year_id):
    try:
        year = yearend.close_year(request.user, ledger.get_year(request.user, year_id))
    except OfficeError as exc:
        return _failed(exc)
    return _done(f'سال مالی {year.year} بسته شد.')


@_guard()
@require_POST
def acc_p_year_reopen(request, year_id):
    try:
        year = yearend.reopen_year(request.user, ledger.get_year(request.user, year_id))
    except OfficeError as exc:
        return _failed(exc)
    return _done(f'سال مالی {year.year} دوباره باز شد.')


BUILDERS = {'statements': tab_statements, 'yearend': tab_yearend}
