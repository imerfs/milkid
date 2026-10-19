"""Accounting controls: the date lock and bank/cash reconciliation (مغایرت‌گیری)."""
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from main.accounting import ledger
from main.models import Account, AccountingLock, ReconMark, VoucherLine
from main.office.errors import Forbidden, Invalid
from main.office.roles import is_admin

MAX_ROWS = 2000


def get_lock(actor):
    """The municipality's lock row (created empty on first use)."""
    muni = ledger.municipality_of(actor)
    lock, _ = AccountingLock.objects.get_or_create(municipality=muni)
    return lock


def set_lock(actor, lock_date):
    """Lock every voucher dated on or before ``lock_date`` (None lifts the lock). Mayor and admins only."""
    muni = ledger.municipality_of(actor)
    if not is_admin(actor) and ledger.role_of(actor) != 'dehyari':
        raise Forbidden('فقط دهیار می‌تواند قفل تاریخ را تغییر دهد.')
    lock, _ = AccountingLock.objects.get_or_create(municipality=muni)
    lock.lock_date, lock.set_by = lock_date, actor
    lock.save()
    return lock


def _bank_account(muni, account):
    ledger._own(muni, account)
    if account.kind != 'asset' or not account.is_postable:
        raise Invalid('مغایرت‌گیری فقط برای حساب‌های بانک و صندوق (دارایی قابل ثبت) ممکن است.')
    return account


def bank_accounts(actor):
    muni = ledger.municipality_of(actor)
    return Account.objects.filter(municipality=muni, kind='asset', is_postable=True).order_by('code')


def reconciliation(actor, year, account, *, date_from=None, date_to=None, statement_balance=None):
    """Lines of ``account`` in the range with their tick, and the totals the accountant compares with the bank.

    ``book`` is the ledger balance up to ``date_to``; ``cleared`` the balance of the ticked lines up to ``date_to``;
    ``difference`` = bank statement balance (if given) minus ``cleared``: zero means the books agree with the bank.
    """
    muni = ledger.municipality_of(actor)
    ledger._own(muni, year)
    _bank_account(muni, account)
    base = VoucherLine.objects.filter(voucher__municipality=muni, voucher__fiscal_year=year, voucher__deleted_at__isnull=True,
                                      account=account)
    upto = base.filter(voucher__date__lte=date_to) if date_to else base
    marked_ids = set(ReconMark.objects.filter(line__in=upto).values_list('line_id', flat=True))

    def balance(qs):
        t = qs.aggregate(d=Sum('debit'), c=Sum('credit'))
        return (t['d'] or Decimal(0)) - (t['c'] or Decimal(0))

    shown = base
    if date_from:
        shown = shown.filter(voucher__date__gte=date_from)
    if date_to:
        shown = shown.filter(voucher__date__lte=date_to)
    lines = list(shown.select_related('voucher').order_by('voucher__date', 'voucher__number', 'row')[:MAX_ROWS])
    rows = [{'line': ln, 'marked': ln.id in marked_ids} for ln in lines]
    book, cleared = balance(upto), balance(upto.filter(pk__in=marked_ids))
    out = {'rows': rows, 'book': book, 'cleared': cleared, 'uncleared': book - cleared, 'truncated': len(lines) == MAX_ROWS,
           'difference': None}
    if statement_balance is not None:
        out['difference'] = statement_balance - cleared
    return out


def save_marks(actor, year, account, shown_ids, checked_ids):
    """Tick the lines in ``checked_ids`` and untick the other lines that were on screen (``shown_ids``)."""
    muni = ledger.municipality_of(actor)
    ledger._own(muni, year)
    _bank_account(muni, account)
    shown = set(shown_ids)
    checked = set(checked_ids) & shown
    valid = set(VoucherLine.objects.filter(pk__in=shown, account=account, voucher__municipality=muni,
                                           voucher__fiscal_year=year, voucher__deleted_at__isnull=True).values_list('pk', flat=True))
    if shown - valid:
        raise Invalid('ردیفی که انتخاب شده متعلق به این حساب و سال نیست.')
    with transaction.atomic():
        ReconMark.objects.filter(line_id__in=shown - checked).delete()
        have = set(ReconMark.objects.filter(line_id__in=checked).values_list('line_id', flat=True))
        ReconMark.objects.bulk_create([ReconMark(municipality=muni, line_id=i, marked_by=actor) for i in checked - have])
    return len(checked)
