"""Budget lines and the budget-vs-actual report. Actuals are read from voucher lines, never stored."""
from django.db import transaction
from django.db.models import Sum

from main.accounting.ledger import _amount, _lines, _own, municipality_of
from main.models import Account, Bill, BudgetLine
from main.office.errors import Invalid

BUDGET_KINDS = ('budget_resource', 'budget_use')


def set_budget(actor, year, account, amount):
    """Create or replace the approved budget of one account. Zero keeps the row (explicitly no budget)."""
    muni = municipality_of(actor)
    _own(muni, year)
    _own(muni, account)
    amount = _amount(amount)
    if year.is_closed:
        raise Invalid('سال مالی بسته است.')
    if account.kind not in BUDGET_KINDS or not account.is_postable:
        raise Invalid('بودجه فقط برای حساب‌های منابع و مصارف قابل ثبت تعریف می‌شود.')
    with transaction.atomic():
        line, _ = BudgetLine.objects.update_or_create(fiscal_year=year, account=account, defaults={'amount': amount})
    return line


def report(actor, year, include_temporary=True):
    """Rows per budget account that has a budget or any movement; totals split into resources and uses.

    Resources: actual = credit - debit. Uses: actual = debit - credit. remaining = budget - actual (negative = over).
    """
    muni = municipality_of(actor)
    _own(muni, year)
    budgets = {b.account_id: b.amount for b in BudgetLine.objects.filter(fiscal_year=year)}
    moves = {r['account_id']: (r['d'], r['c']) for r in _lines(muni, year, include_temporary)
             .filter(account__kind__in=BUDGET_KINDS).values('account_id').annotate(d=Sum('debit'), c=Sum('credit'))}
    # Income is booked when the money arrives, so a bill that is issued but not paid yet shows here only as a receivable
    # (what the village is still owed on that income account); it never enters the ledger or «actual».
    owed = {}
    for bill in Bill.objects.filter(fiscal_year=year, canceled_at__isnull=True).annotate(paid=Sum('payments__amount')):
        left = bill.amount - (bill.paid or 0)
        if left > 0:
            owed[bill.income_account_id] = owed.get(bill.income_account_id, 0) + left
    accounts = Account.objects.filter(municipality=muni, pk__in=set(budgets) | set(moves) | set(owed)).order_by('code')
    rows = []
    totals = {'resource': {'budget': 0, 'actual': 0, 'receivable': 0}, 'use': {'budget': 0, 'actual': 0, 'receivable': 0}}
    for acc in accounts:
        d, c = moves.get(acc.id, (0, 0))
        resource = acc.kind == 'budget_resource'
        actual = (c - d) if resource else (d - c)
        planned = budgets.get(acc.id, 0)
        rows.append({
            'account_id': acc.id, 'code': acc.code, 'title': acc.title, 'kind': 'resource' if resource else 'use',
            'budget': planned, 'actual': actual, 'remaining': planned - actual, 'receivable': owed.get(acc.id, 0),
            'percent': round(actual * 100 / planned) if planned else None,
            'over': actual > planned})
        bucket = totals['resource' if resource else 'use']
        bucket['budget'] += planned
        bucket['actual'] += actual
        bucket['receivable'] += owed.get(acc.id, 0)
    return rows, totals
