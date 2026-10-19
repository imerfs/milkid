"""Year-end operations: the temporary-accounts closing voucher, the closing voucher (اختتامیه), the next year's opening
voucher (افتتاحیه), and closing the fiscal year itself.

All three vouchers are built from the ledger, shown as a preview first, and issued as ordinary *temporary* vouchers that
go through ``ledger.create_voucher`` (so numbering, date and tenant rules are the same). Issuing again replaces the
previous voucher of that kind while it is still temporary; a final one must be reverted first.

* ``temp_closing`` (dated the last day of the year): zeroes the resource and use accounts against 410 (surplus/deficit).
* ``closing`` (last day): zeroes every asset, liability and equity account against 411 (اختتامیه).
* ``opening`` (first day of the next year): re-creates the balances of the previous year, as they stood before the closing
  voucher, against 111 (افتتاحیه).
"""
from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from main.accounting import backup, ledger
from main.models import Account, FiscalYear, Voucher, VoucherLine
from main.office.errors import Conflict, Forbidden, Invalid, NotFound
from main.office.roles import is_admin

OPENING_COUNTER, SURPLUS, CLOSING_COUNTER = '111', '410', '411'
BUDGET_KINDS = ('budget_resource', 'budget_use')
BALANCE_KINDS = ('asset', 'liability', 'equity')
TITLES = {'temp_closing': 'سند بستن حساب‌های موقت (منابع و مصارف)', 'closing': 'سند اختتامیه',
          'opening': 'سند افتتاحیه'}


def _account(muni, code):
    account = Account.objects.filter(municipality=muni, code=code).first()
    if account is None or not account.is_postable:
        raise Invalid(f'حساب {code} در سرفصل‌ها نیست؛ ابتدا سرفصل‌های پیش‌فرض را بسازید.')
    return account


def _balances(muni, year, kinds, *, exclude_kinds):
    """{(account, party): net debit} for accounts of ``kinds``, over every live voucher of the year except ``exclude_kinds``."""
    qs = (VoucherLine.objects.filter(voucher__municipality=muni, voucher__fiscal_year=year,
                                     voucher__deleted_at__isnull=True, account__kind__in=kinds)
          .exclude(voucher__kind__in=exclude_kinds)
          .values('account_id', 'party_id').annotate(d=Sum('debit'), c=Sum('credit')))
    return {(r['account_id'], r['party_id']): (r['d'] or 0) - (r['c'] or 0) for r in qs if (r['d'] or 0) != (r['c'] or 0)}


def _close_lines(muni, balances, counter, *, description):
    """Lines that zero each balance, plus one line on ``counter`` that keeps the voucher balanced."""
    accounts = {a.id: a for a in Account.objects.filter(municipality=muni, pk__in={k[0] for k in balances})}
    lines, debit, credit = [], Decimal(0), Decimal(0)
    for (account_id, party_id), net in sorted(balances.items(), key=lambda kv: (accounts[kv[0][0]].code, kv[0][1] or 0)):
        line = {'account': accounts[account_id], 'party_id': party_id, 'description': description,
                'debit': -net if net < 0 else Decimal(0), 'credit': net if net > 0 else Decimal(0)}
        debit += line['debit']
        credit += line['credit']
        lines.append(line)
    return lines, debit, credit, counter


def _open_lines(muni, balances, counter, *, description):
    """Lines that carry each balance forward (same side), plus the counter line."""
    accounts = {a.id: a for a in Account.objects.filter(municipality=muni, pk__in={k[0] for k in balances})}
    lines, debit, credit = [], Decimal(0), Decimal(0)
    for (account_id, party_id), net in sorted(balances.items(), key=lambda kv: (accounts[kv[0][0]].code, kv[0][1] or 0)):
        line = {'account': accounts[account_id], 'party_id': party_id, 'description': description,
                'debit': net if net > 0 else Decimal(0), 'credit': -net if net < 0 else Decimal(0)}
        debit += line['debit']
        credit += line['credit']
        lines.append(line)
    return lines, debit, credit, counter


def _finish(lines, debit, credit, counter, description, *, two_sided=False):
    """Add the counter-account lines. One-sided: a single line for the difference. Two-sided (closing and opening
    vouchers): the counter account is credited with the debits and debited with the credits, as in the reference
    software, so it nets to the difference but shows both halves."""
    if not lines:
        raise Conflict('حسابی برای این سند مانده‌ای ندارد؛ چیزی برای ثبت نیست.')
    base = {'account': counter, 'party_id': None, 'description': description}
    if two_sided:
        if debit:
            lines.append({**base, 'debit': Decimal(0), 'credit': debit})
        if credit:
            lines.append({**base, 'debit': credit, 'credit': Decimal(0)})
    elif debit != credit:
        lines.append({**base, 'debit': credit - debit if credit > debit else Decimal(0),
                      'credit': debit - credit if debit > credit else Decimal(0)})
    return lines


def plan(actor, year, kind):
    """The voucher the operation would issue: ``{'kind', 'date', 'description', 'lines': [...], 'debit', 'credit', 'warnings'}``.

    Raises Conflict/Invalid when it cannot be built (nothing to close, previous year missing, budget accounts still open ...).
    """
    muni = ledger.municipality_of(actor)
    ledger._own(muni, year)
    if kind not in TITLES:
        raise Invalid('نوع عملیات نامعتبر است.')
    description = f'{TITLES[kind]} سال {year.year}'
    warnings = []
    if kind == 'temp_closing':
        balances = _balances(muni, year, BUDGET_KINDS, exclude_kinds=('temp_closing', 'closing'))
        lines = _finish(*_close_lines(muni, balances, _account(muni, SURPLUS), description=description), description) if balances else []
        on = year.end_date
    elif kind == 'closing':
        if _balances(muni, year, BUDGET_KINDS, exclude_kinds=('closing',)):
            raise Conflict('حساب‌های منابع و مصارف هنوز مانده دارند؛ ابتدا «سند بستن حساب‌های موقت» را صادر کنید.')
        balances = _balances(muni, year, BALANCE_KINDS, exclude_kinds=('closing',))
        counter = _account(muni, CLOSING_COUNTER)
        balances = {k: v for k, v in balances.items() if k[0] != counter.id}
        lines = _finish(*_close_lines(muni, balances, counter, description=description), description, two_sided=True) if balances else []
        on = year.end_date
    else:
        previous = FiscalYear.objects.filter(municipality=muni, year=year.year - 1).first()
        if previous is None:
            raise Conflict(f'سال مالی {year.year - 1} وجود ندارد؛ سند افتتاحیه از مانده‌های سال قبل ساخته می‌شود.')
        if _balances(muni, previous, BUDGET_KINDS, exclude_kinds=('closing',)):
            raise Conflict(f'حساب‌های منابع و مصارف سال {previous.year} هنوز بسته نشده‌اند؛ ابتدا در آن سال '
                           '«سند بستن حساب‌های موقت» را صادر کنید.')
        counter = _account(muni, OPENING_COUNTER)
        balances = _balances(muni, previous, BALANCE_KINDS, exclude_kinds=('closing',))
        balances = {k: v for k, v in balances.items() if k[0] != counter.id and k[0] != _account(muni, CLOSING_COUNTER).id}
        lines = _finish(*_open_lines(muni, balances, counter, description=description), description, two_sided=True) if balances else []
        on = year.start_date
        if not any(True for _ in Voucher.objects.filter(fiscal_year=previous, deleted_at__isnull=True, kind='closing')):
            warnings.append(f'برای سال {previous.year} سند اختتامیه صادر نشده است؛ مانده‌ها همچنان از روی دفتر خوانده شد.')
    if not lines:
        raise Conflict('حسابی برای این سند مانده‌ای ندارد؛ چیزی برای ثبت نیست.')
    temporary = Voucher.objects.filter(fiscal_year=year, deleted_at__isnull=True, status='temporary').exclude(kind=kind).count()
    if temporary and kind != 'opening':
        warnings.append(f'{temporary} سند موقت در این سال هست؛ مانده‌ها شامل آن‌ها هم می‌شود.')
    return {'kind': kind, 'date': on, 'description': description, 'lines': lines,
            'debit': sum((ln['debit'] for ln in lines), Decimal(0)), 'credit': sum((ln['credit'] for ln in lines), Decimal(0)),
            'warnings': warnings, 'existing': Voucher.objects.filter(fiscal_year=year, deleted_at__isnull=True, kind=kind).first()}


def _unbalanced(year):
    return [v for v in Voucher.objects.filter(fiscal_year=year, deleted_at__isnull=True)
            .annotate(d=Sum('lines__debit'), c=Sum('lines__credit')) if (v.d or 0) != (v.c or 0)]


def issue(actor, year, kind):
    """Issue (or re-issue) the year-end voucher of ``kind`` as a temporary voucher and return it."""
    muni = ledger.municipality_of(actor)
    ledger._own(muni, year)
    if year.is_closed:
        raise Conflict('سال مالی بسته شده است.')
    bad = _unbalanced(year)
    if bad:
        raise Conflict('اسناد بی‌حساب در این سال هست (' + '، '.join(str(v.number) for v in bad[:5]) + ')؛ ابتدا آن‌ها را اصلاح کنید.')
    plan(actor, year, kind)                                   # fail early, before the safety backup is written
    backup.create_for(muni, kind='before_yearend', note=f'پیش از صدور {TITLES[kind]} سال {year.year}', actor=actor)
    with transaction.atomic():
        data = plan(actor, year, kind)
        existing = data['existing']
        if existing is not None:
            if existing.status == 'final':
                raise Conflict('این سند قطعی شده است؛ برای صدور دوباره ابتدا آن را به موقت برگردانید.')
            ledger.delete_voucher(actor, existing)
        lines = [{'account': ln['account'], 'party': ln['party_id'] and muni.parties.get(pk=ln['party_id']),
                  'description': ln['description'], 'debit': ln['debit'], 'credit': ln['credit']} for ln in data['lines']]
        return ledger.create_voucher(actor, year, data['date'], kind, data['description'], lines)


def close_year(actor, year):
    """Lock the year: no voucher is added or changed afterwards. Needs every voucher final."""
    muni = ledger.municipality_of(actor)
    ledger._own(muni, year)
    if year.is_closed:
        raise Conflict('این سال قبلاً بسته شده است.')
    if Voucher.objects.filter(fiscal_year=year, deleted_at__isnull=True, status='temporary').exists():
        raise Conflict('هنوز سند موقت وجود دارد؛ همه اسناد باید قطعی شوند.')
    backup.create_for(muni, kind='before_yearend', note=f'پیش از بستن سال {year.year}', actor=actor)
    year.is_closed = True
    year.save(update_fields=['is_closed'])
    return year


def reopen_year(actor, year):
    muni = ledger.municipality_of(actor)
    ledger._own(muni, year)
    if not is_admin(actor) and ledger.role_of(actor) != 'dehyari':
        raise Forbidden('فقط دهیار می‌تواند سال بسته را باز کند.')
    if not year.is_closed:
        raise Conflict('این سال بسته نیست.')
    if Voucher.objects.filter(fiscal_year__municipality=muni, fiscal_year__year=year.year + 1, kind='opening',
                              status='final', deleted_at__isnull=True).exists():
        raise Conflict('سند افتتاحیه قطعی سال بعد از این سال ساخته شده است؛ ابتدا آن را به موقت برگردانید.')
    year.is_closed = False
    year.save(update_fields=['is_closed'])
    return year


def overview(actor, year):
    """What the operations screen needs: the current vouchers of each kind and whether the year can be closed."""
    muni = ledger.municipality_of(actor)
    ledger._own(muni, year)
    existing = {v.kind: v for v in Voucher.objects.filter(fiscal_year=year, deleted_at__isnull=True,
                                                          kind__in=list(TITLES))}
    return {'existing': existing, 'temporary': Voucher.objects.filter(fiscal_year=year, deleted_at__isnull=True,
                                                                       status='temporary').count(),
            'unbalanced': _unbalanced(year), 'has_previous': FiscalYear.objects.filter(
                municipality=muni, year=year.year - 1).exists()}
