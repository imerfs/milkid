"""Reports page of the accountant workspace and its Excel export. Rules and queries live in main/accounting/reports."""
from django.http import HttpResponse
from openpyxl import Workbook

from main.accounting import ledger, reports
from main.models import (Contract, CostCenter, Guarantee, InstallmentPlan, Party, PayableDocument, Voucher)
from main.office.errors import OfficeError
from main.views.accounting_views import _cell, _guard

BILL_STATES = [('پرداخت‌شده', 'پرداخت‌شده'), ('قسمتی', 'قسمتی'), ('پرداخت‌نشده', 'پرداخت‌نشده'), ('ابطال', 'ابطال‌شده')]
STATUS_OPTIONS = {'status_voucher': Voucher.STATUSES, 'status_bill': BILL_STATES, 'status_plan': InstallmentPlan.STATUSES,
                  'status_guarantee': Guarantee.STATUSES, 'status_payable': PayableDocument.STATUSES,
                  'status_contract': Contract.STATUSES}
FILTER_KEYS = ('date_from', 'date_to', 'number_from', 'number_to', 'status', 'kind', 'q', 'party', 'cost_center', 'final')


def tab_reports(request, year, ctx):
    key = request.GET.get('report') if request.GET.get('report') in reports.REPORTS else 'vouchers'
    filters = reports.REPORTS[key][2]
    params = {k: request.GET.get(k, '') for k in FILTER_KEYS}
    ctx.update(report_key=key, report_list=[(k, v[0]) for k, v in reports.REPORTS.items()], f_date='date' in filters,
               f_number='number' in filters, f_kind='kind' in filters, f_q='q' in filters, f_final='final' in filters,
               f_party='party' in filters, f_center='cost_center' in filters,
               f_status=next((STATUS_OPTIONS[f] for f in filters if f in STATUS_OPTIONS), None),
               kinds=Voucher.KINDS, export_query=request.GET.urlencode())
    if ctx['f_party']:
        ctx['party_choices'] = Party.objects.filter(municipality=ctx['muni'])
    if ctx['f_center']:
        ctx['center_choices'] = CostCenter.objects.filter(municipality=ctx['muni'])
    try:
        ctx['report'] = reports.run(request.user, year, key, params)
        ctx['report']['rows'] = [[{'v': v, 'money': i in ctx['report']['money']} for i, v in enumerate(r)]
                                 for r in ctx['report']['rows']]
        if ctx['report']['totals']:
            ctx['report']['totals'] = [{'v': v, 'money': i in ctx['report']['money']}
                                       for i, v in enumerate(ctx['report']['totals'])]
    except OfficeError as exc:
        ctx['report_error'] = str(exc)


@_guard()
def acc_p_report_export(request, year_id, key):
    year = ledger.get_year(request.user, year_id)
    params = {k: request.GET.get(k, '') for k in FILTER_KEYS}
    try:
        out = reports.run(request.user, year, key, params)
    except OfficeError as exc:
        return HttpResponse(str(exc), status=exc.status, content_type='text/plain; charset=utf-8')
    wb = Workbook()
    ws = wb.active
    ws.title = out['label'][:30]
    ws.sheet_view.rightToLeft = True
    ws.append(out['columns'])
    for row in out['rows']:
        ws.append([int(v) if i in out['money'] else _cell(v) if isinstance(v, str) else v for i, v in enumerate(row)])
    if out['totals']:
        ws.append([int(v) if i in out['money'] and v != '' else v for i, v in enumerate(out['totals'])])
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="report-{key}-{year.year}.xlsx"'
    wb.save(response)
    return response


BUILDERS = {'reports': tab_reports}
