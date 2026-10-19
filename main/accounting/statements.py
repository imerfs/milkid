"""Financial statements and the multi-level trial balance. Read-only; every figure comes from voucher lines.

Voucher kinds ``temp_closing`` and ``closing`` (see main/accounting/yearend.py) move balances around at the end of a
year, so the statements leave them out where they would hide what the year did:

* the statement of resources and uses ignores both, so it still shows the year after the temporary accounts were closed;
* the balance sheet ignores only ``closing``: closing the temporary accounts moved the surplus into account 410,
  which the balance sheet shows as equity.

Accounts 111 (opening) and 411 (closing) are clearing accounts that net to zero; they are not shown.
"""
from collections import defaultdict
from decimal import Decimal

from django.db.models import Q, Sum

from main.accounting.ledger import _own, municipality_of
from main.models import Account, BudgetLine, VoucherLine
from main.office.errors import Invalid

CLEARING_CODES = ('111', '411')
RESOURCE, USE = 'budget_resource', 'budget_use'
SHEET_ASSET, SHEET_CLAIMS = ('asset',), ('liability', 'equity')


def _lines(muni, year, *, upto=None, final_only=False, exclude_kinds=()):
    qs = VoucherLine.objects.filter(voucher__municipality=muni, voucher__fiscal_year=year, voucher__deleted_at__isnull=True)
    if upto:
        qs = qs.filter(voucher__date__lte=upto)
    if final_only:
        qs = qs.filter(voucher__status='final')
    if exclude_kinds:
        qs = qs.exclude(voucher__kind__in=exclude_kinds)
    return qs


def _net(qs):
    """{account_id: debit - credit}"""
    return {r['account_id']: (r['d'] or 0) - (r['c'] or 0)
            for r in qs.values('account_id').annotate(d=Sum('debit'), c=Sum('credit'))}


def account_tree(muni):
    """{id: Account} with ``depth`` (1 for a top-level account) set on each."""
    accounts = {a.id: a for a in Account.objects.filter(municipality=muni)}
    for account in accounts.values():
        depth, node, seen = 1, account, set()
        while node.parent_id and node.parent_id in accounts and node.id not in seen:
            seen.add(node.id)
            node = accounts[node.parent_id]
            depth += 1
        account.depth = depth
    return accounts


def _ancestors(account, accounts):
    chain, node, seen = [], account, set()
    while node.parent_id and node.parent_id in accounts and node.id not in seen:
        seen.add(node.id)
        node = accounts[node.parent_id]
        chain.append(node)
    return chain


def rollup(values, accounts, *, sign=1):
    """Rows for the accounts that have a value and all their ancestors, in code order.

    ``values`` maps account id to a number; a parent's amount is the sum of its descendants. ``sign`` flips the
    debit-minus-credit figure into the natural direction of the section (resources and liabilities are credits).
    """
    totals = defaultdict(Decimal)
    for account_id, value in values.items():
        account = accounts.get(account_id)
        if account is None or not value:
            continue
        totals[account_id] += value * sign
        for parent in _ancestors(account, accounts):
            totals[parent.id] += value * sign
    rows = [{'account_id': i, 'code': accounts[i].code, 'title': accounts[i].title, 'depth': accounts[i].depth,
             'amount': amount, 'leaf': i in values} for i, amount in totals.items()]
    return sorted(rows, key=lambda r: r['code'])


def _sum_leaves(rows):
    return sum((r['amount'] for r in rows if r['leaf']), Decimal(0))


def resources_and_uses(actor, year, *, upto=None, final_only=False):
    """Statement of resources and uses (صورت منابع و مصارف): what came in, what went out, surplus or deficit."""
    muni = municipality_of(actor)
    _own(muni, year)
    accounts = account_tree(muni)
    net = _net(_lines(muni, year, upto=upto, final_only=final_only, exclude_kinds=('temp_closing', 'closing')))
    budgets = {b.account_id: b.amount for b in BudgetLine.objects.filter(fiscal_year=year)}
    out = {}
    for key, kind, sign in (('resources', RESOURCE, -1), ('uses', USE, 1)):
        values = {i: v for i, v in net.items() if accounts.get(i) and accounts[i].kind == kind}
        planned = {i: v for i, v in budgets.items() if accounts.get(i) and accounts[i].kind == kind}
        rows = rollup({**{i: 0 for i in planned}, **values}, accounts, sign=sign)
        # budget column: roll the approved budgets up the same way
        budget_rows = {r['account_id']: r['amount'] for r in rollup(planned, accounts)}
        for row in rows:
            row['budget'] = budget_rows.get(row['account_id'], Decimal(0))
        rows = [r for r in rows if r['amount'] or r['budget']]
        out[key] = {'rows': rows, 'total': _sum_leaves(rows), 'budget': sum((r['budget'] for r in rows if r['leaf']), Decimal(0))}
    out['surplus'] = out['resources']['total'] - out['uses']['total']
    out['budget_surplus'] = out['resources']['budget'] - out['uses']['budget']
    return out


def balance_sheet(actor, year, *, upto=None, final_only=False):
    """Statement of financial position (ترازنامه). ``difference`` is assets minus claims; it is zero unless the
    clearing accounts 111/411 were posted to by hand or a voucher is unbalanced."""
    muni = municipality_of(actor)
    _own(muni, year)
    accounts = account_tree(muni)
    net = _net(_lines(muni, year, upto=upto, final_only=final_only, exclude_kinds=('closing',)))
    clearing = {i: v for i, v in net.items() if accounts.get(i) and accounts[i].code in CLEARING_CODES and v}
    assets = {i: v for i, v in net.items() if accounts.get(i) and accounts[i].kind in SHEET_ASSET
              and accounts[i].code not in CLEARING_CODES}
    claims = {i: v for i, v in net.items() if accounts.get(i) and accounts[i].kind in SHEET_CLAIMS
              and accounts[i].code not in CLEARING_CODES}
    surplus = -sum((v for i, v in net.items() if accounts.get(i) and accounts[i].kind in (RESOURCE, USE)), Decimal(0))
    asset_rows, claim_rows = rollup(assets, accounts), rollup(claims, accounts, sign=-1)
    total_assets, total_claims = _sum_leaves(asset_rows), _sum_leaves(claim_rows)
    return {'assets': asset_rows, 'claims': claim_rows, 'surplus': surplus,
            'total_assets': total_assets, 'total_claims': total_claims + surplus,
            'difference': total_assets - (total_claims + surplus),
            'clearing': [{'code': accounts[i].code, 'title': accounts[i].title, 'amount': v} for i, v in clearing.items()]}


LEVELS = ('all', '1', '2', '3', '4')


def trial_by_level(actor, year, *, level='all', date_from=None, date_to=None, final_only=False, with_closing=False):
    """Trial balance with opening, turnover and ending columns, rolled up to a level of the chart (1 = main groups).

    Opening = the opening voucher plus everything dated before ``date_from``; turnover = ``date_from..date_to``.
    Closing vouchers (``temp_closing`` / ``closing``) are left out unless ``with_closing``.
    """
    if level not in LEVELS:
        raise Invalid('سطح تراز نامعتبر است.')
    muni = municipality_of(actor)
    _own(muni, year)
    accounts = account_tree(muni)
    qs = _lines(muni, year, final_only=final_only, exclude_kinds=() if with_closing else ('temp_closing', 'closing'))
    if date_to:
        qs = qs.filter(Q(voucher__kind='opening') | Q(voucher__date__lte=date_to))
    before = Q(voucher__kind='opening')
    if date_from:
        before |= Q(voucher__date__lt=date_from)
    rows = qs.values('account_id').annotate(
        od=Sum('debit', filter=before), oc=Sum('credit', filter=before),
        td=Sum('debit', filter=~before), tc=Sum('credit', filter=~before))
    grouped = defaultdict(lambda: [Decimal(0)] * 4)
    for r in rows:
        account = accounts.get(r['account_id'])
        if account is None:
            continue
        target = account
        if level != 'all':
            chain = [account] + _ancestors(account, accounts)
            wanted = int(level)
            target = next((a for a in reversed(chain) if a.depth == wanted), account)
        slot = grouped[target.id]
        for k, key in enumerate(('od', 'oc', 'td', 'tc')):
            slot[k] += r[key] or 0
    out, totals = [], {key: Decimal(0) for key in ('open_d', 'open_c', 'turn_d', 'turn_c', 'end_d', 'end_c')}
    for account_id, (od, oc, td, tc) in grouped.items():
        account = accounts[account_id]
        open_net, end_net = od - oc, od - oc + td - tc
        row = {'account_id': account_id, 'code': account.code, 'title': account.title, 'depth': account.depth,
               'open_d': max(open_net, 0), 'open_c': max(-open_net, 0), 'turn_d': td, 'turn_c': tc,
               'end_d': max(end_net, 0), 'end_c': max(-end_net, 0)}
        out.append(row)
        for key in totals:
            totals[key] += row[key]
    out.sort(key=lambda r: r['code'])
    totals['debit'] = totals['open_d'] + totals['turn_d']          # same meaning as ledger.trial_balance
    totals['credit'] = totals['open_c'] + totals['turn_c']
    return out, totals
