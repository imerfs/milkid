"""Letters attached to accounting records (a voucher, a contract or an instalment plan).

Only a letter the user can open (their own, or one sent to them) can be attached; the link itself is visible to everybody
who may see the record, but the letter opens only for people the office module lets read it.
"""
from django.db import IntegrityError, transaction

from main.accounting import ledger
from main.models import LetterLink
from main.office import letters as office_letters
from main.office.errors import Conflict, Invalid

SHOWN_LETTERS = 100


def _target(muni, voucher, contract, plan):
    given = [t for t in (voucher, contract, plan) if t is not None]
    if len(given) != 1:
        raise Invalid('نامه به یک سند، قرارداد یا پرونده تقسیط پیوست می‌شود.')
    target = given[0]
    if target.municipality_id != muni.id:
        raise Invalid('مقصد نامعتبر است.')
    return target


def links_for(actor, *, voucher=None, contract=None, plan=None):
    muni = ledger.municipality_of(actor)
    _target(muni, voucher, contract, plan)
    return LetterLink.objects.filter(municipality=muni, voucher=voucher, contract=contract, plan=plan).select_related('letter', 'linked_by')


def choices(actor):
    """Letters the user may attach: newest first."""
    return office_letters.visible_to(actor).exclude(status='draft').order_by('-sent_at')[:SHOWN_LETTERS]


def link(actor, letter_id, *, voucher=None, contract=None, plan=None):
    muni = ledger.municipality_of(actor)
    _target(muni, voucher, contract, plan)
    letter = office_letters.get_for(actor, letter_id)          # NotFound unless the user can open it
    if letter.status != 'sent':
        raise Invalid('فقط نامه‌ی ارسال‌شده پیوست می‌شود.')
    try:
        with transaction.atomic():
            return LetterLink.objects.create(municipality=muni, letter=letter, voucher=voucher, contract=contract, plan=plan,
                                             linked_by=actor)
    except IntegrityError:
        raise Conflict('این نامه قبلاً پیوست شده است.')


def unlink(actor, link_id):
    muni = ledger.municipality_of(actor)
    row = ledger._own(muni, LetterLink.objects.filter(pk=link_id).first())
    row.delete()
