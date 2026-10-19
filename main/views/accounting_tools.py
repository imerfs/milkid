"""Tools of the accountant workspace: calculators, global search and printable cheques / deposit slips.
Rules live in main/accounting/tools and search; the print pages are standalone documents meant for the printer."""
from datetime import date

from django.http import JsonResponse
from django.shortcuts import render

from main.accounting import instalments, ledger, search, tools, treasury
from main.office.errors import OfficeError
from main.views.accounting_panel import PANEL
from main.views.accounting_views import _guard


def tab_tools(request, year, ctx):
    ctx['today'] = date.today().isoformat()


@_guard()
def acc_p_calculator(request):
    return render(request, PANEL + 'calculator.html')


@_guard()
def acc_p_shortcuts(request):
    return render(request, PANEL + 'shortcuts.html')


def _json(build):
    try:
        return JsonResponse(build())
    except OfficeError as exc:
        return JsonResponse({'error': str(exc)}, status=exc.status)


@_guard()
def acc_p_tools_words(request):
    def build():
        text = request.GET.get('n', '').translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٬,', '0123456789  ')).replace(' ', '').strip()
        try:
            number = int(text)
        except ValueError:
            return {'error': 'یک عدد صحیح وارد کنید.'}
        return {'words': tools.number_to_words(number), 'rial': tools.amount_in_words(number)}
    return _json(build)


@_guard()
def acc_p_tools_date(request):
    return _json(lambda: tools.convert_date(jalali=request.GET.get('jalali'), gregorian=request.GET.get('gregorian')))


@_guard()
def acc_p_tools_loan(request):
    def build():
        digits = str.maketrans('۰۱۲۳۴۵۶۷۸۹٬,', '0123456789  ')
        return tools.loan(request.GET.get('amount', '').translate(digits).replace(' ', ''), request.GET.get('rate', '0').translate(digits),
                          request.GET.get('months', '').translate(digits), rows=int(request.GET.get('rows', '12') or 12))
    return _json(build)


@_guard()
def acc_p_search(request):
    return JsonResponse({'results': search.run(request.user, request.GET.get('q', ''))})


# ---------- printing ----------

def _paper(request, default):
    key = request.GET.get('paper') if request.GET.get('paper') in tools.PAPERS else default
    return key, tools.PAPERS[key][1], [(k, v[0]) for k, v in tools.PAPERS.items()]


@_guard()
def acc_p_print_cheque(request, doc_id):
    """The cheque the municipality issues (a payable document), laid out for the printer."""
    doc = treasury.get_document(request.user, doc_id)
    key, size, papers = _paper(request, 'cheque')
    return render(request, 'main/accounting/print_cheque.html', {
        'doc': doc, 'muni': ledger.municipality_of(request.user), 'paper': key, 'paper_size': size, 'papers': papers})


@_guard()
def acc_p_print_slip(request, installment_id):
    """Deposit slip (فیش خوابانده) for a cheque received in an instalment plan."""
    inst = instalments.get_installment(request.user, installment_id)
    if inst is None:
        from django.http import Http404
        raise Http404()
    key, size, papers = _paper(request, 'a5')
    return render(request, 'main/accounting/print_slip.html', {
        'i': inst, 'muni': ledger.municipality_of(request.user), 'paper': key, 'paper_size': size, 'papers': papers})


BUILDERS = {'tools': tab_tools}
