"""Global search of the accountant workspace: vouchers, parties, accounts, bills, instalment plans and contracts.

Scoped to the actor's municipality; kinds the accountant has no access to (see access_levels) are left out.
Each hit says how to open it: a modal URL, or a workspace tab with a query.
"""
from django.db.models import Q
from django.urls import reverse

from main.accounting import access_levels, ledger
from main.accounting.parse import digits, jalali_str
from main.models import Account, Bill, Contract, InstallmentPlan, Party, Voucher

LIMIT = 5
MIN_LENGTH = 2


def run(actor, query):
    """``[{'kind', 'label', 'sub', 'action': 'modal'|'tab', 'url'|'tab'+'query'}]``, at most LIMIT per kind."""
    muni = ledger.municipality_of(actor)
    text = (query or '').strip()[:60]
    if len(text) < MIN_LENGTH:
        return []
    number = digits(text)
    numeric = number.isdigit()
    out = []

    def allowed(area):
        return access_levels.level_for(actor, area) != 'none'

    if allowed('vouchers'):
        match = Q(description__icontains=text)
        if numeric:
            match |= Q(number=int(number)) | Q(ref=int(number))
        for v in Voucher.objects.filter(match, municipality=muni, deleted_at__isnull=True).select_related('fiscal_year').order_by(
                '-fiscal_year__year', '-number')[:LIMIT]:
            out.append({'kind': 'سند', 'label': f'سند {v.number} · {v.description[:50]}',
                        'sub': f'{jalali_str(v.date)} · {v.get_status_display()}', 'action': 'modal',
                        'url': reverse('main:acc_p_voucher_detail', args=[v.id])})
    if allowed('master'):
        for p in Party.objects.filter(Q(name__icontains=text) | Q(national_id__startswith=number if numeric else text)
                                      | Q(mobile__startswith=number if numeric else text), municipality=muni)[:LIMIT]:
            out.append({'kind': 'طرف حساب', 'label': p.name, 'sub': p.national_id or p.mobile or '', 'action': 'tab', 'tab': 'parties',
                        'query': f'q={p.name}'})
        for a in Account.objects.filter(Q(title__icontains=text) | Q(code__startswith=text), municipality=muni)[:LIMIT]:
            out.append({'kind': 'حساب', 'label': f'{a.code} - {a.title}', 'sub': a.get_kind_display(), 'action': 'tab', 'tab': 'accounts',
                        'query': f'q={a.code}'})
    if allowed('bills'):
        match = Q(description__icontains=text) | Q(party__name__icontains=text)
        if numeric:
            match |= Q(number=int(number))
        for b in Bill.objects.filter(match, municipality=muni).select_related('party', 'fiscal_year').order_by('-fiscal_year__year', '-number')[:LIMIT]:
            out.append({'kind': 'فیش', 'label': f'فیش {b.number} · {b.party.name}', 'sub': f'{b.amount:,} ریال', 'action': 'modal',
                        'url': reverse('main:acc_p_bill_detail', args=[b.id])})
    if allowed('income'):
        match = Q(party__name__icontains=text) | Q(property_file__icontains=text) | Q(renovation_code__icontains=text)
        if numeric:
            match |= Q(number=int(number))
        for plan in InstallmentPlan.objects.filter(match, municipality=muni).select_related('party', 'fiscal_year')[:LIMIT]:
            out.append({'kind': 'تقسیط', 'label': f'پرونده تقسیط {plan.number} · {plan.party.name}', 'sub': f'{plan.plan_amount:,} ریال',
                        'action': 'modal', 'url': reverse('main:acc_p_plan_detail', args=[plan.id])})
    if allowed('contracts'):
        match = Q(subject__icontains=text) | (Q(number=int(number)) if numeric else Q())
        for c in Contract.objects.filter(match, municipality=muni)[:LIMIT]:
            out.append({'kind': 'قرارداد', 'label': f'قرارداد {c.number} · {c.subject[:40]}', 'sub': f'{c.amount:,} ریال', 'action': 'modal',
                        'url': reverse('main:acc_p_contract_detail', args=[c.id])})
    return out
