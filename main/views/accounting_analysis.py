"""Report builder, pivot analyser and charts of the accountant workspace. Rules live in main/accounting/builder and charts."""
from django.http import HttpResponse, JsonResponse
from openpyxl import Workbook

from main.accounting import builder, charts, ledger
from main.office.errors import OfficeError
from main.views.accounting_panel import _date_param
from main.views.accounting_views import _cell, _guard

PARAM_KEYS = ('dataset', 'group', 'column', 'measure', 'date_from', 'date_to', 'final')


def _run(request, year):
    g = request.GET
    dataset = g.get('dataset') if g.get('dataset') in builder.DATASETS else 'lines'
    spec = builder.DATASETS[dataset]
    group = g.get('group') if g.get('group') in spec['dimensions'] else next(iter(spec['dimensions']))
    column = g.get('column') if g.get('column') in spec['dimensions'] and g.get('column') != group else ''
    measure = g.get('measure') if g.get('measure') in spec['measures'] else next(iter(spec['measures']))
    date_from, err_from = _date_param(request, 'date_from')
    date_to, err_to = _date_param(request, 'date_to')
    params = dict(dataset=dataset, group=group, column=column, measure=measure)
    if err_from or err_to:
        return params, None, err_from or err_to
    try:
        out = builder.build(request.user, year, dataset, group, measure=measure, column=column or None, date_from=date_from,
                            date_to=date_to, final_only=g.get('final') == '1')
    except OfficeError as exc:
        return params, None, str(exc)
    return params, out, None


def tab_builder(request, year, ctx):
    params, out, error = _run(request, year)
    ctx.update(builder_params=params, catalogue=builder.catalogue(), builder_error=error, export_query=request.GET.urlencode(),
               dimensions=builder.catalogue()[params['dataset']]['dimensions'],
               measures=builder.catalogue()[params['dataset']]['measures'])
    if out:
        out['rows'] = [[{'v': v, 'money': i in out['money']} for i, v in enumerate(r)] for r in out['rows']]
        if out['totals']:
            out['totals'] = [{'v': v, 'money': i in out['money']} for i, v in enumerate(out['totals'])]
        ctx['report'] = out


@_guard()
def acc_p_builder_export(request, year_id):
    year = ledger.get_year(request.user, year_id)
    _, out, error = _run(request, year)
    if error:
        return HttpResponse(error, status=400, content_type='text/plain; charset=utf-8')
    wb = Workbook()
    ws = wb.active
    ws.title = out['label'][:30]
    ws.sheet_view.rightToLeft = True
    ws.append([_cell(h) for h in out['columns']])
    for row in out['rows']:
        ws.append([int(v) if i in out['money'] else _cell(v) if isinstance(v, str) else int(v) if i else v for i, v in enumerate(row)])
    if out['totals']:
        ws.append([int(v) if i in out['money'] and v != '' else v for i, v in enumerate(out['totals'])])
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="builder-{year.year}.xlsx"'
    wb.save(response)
    return response


def tab_charts(request, year, ctx):
    ctx['final_only'] = request.GET.get('final') == '1'


@_guard()
def acc_p_chart_data(request, year_id):
    year = ledger.get_year(request.user, year_id)
    return JsonResponse(charts.data(request.user, year, final_only=request.GET.get('final') == '1'))


BUILDERS = {'builder': tab_builder, 'charts': tab_charts}
