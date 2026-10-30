"""The confirmation protocol every step of the construction-without-a-permit track shares.

A step is: the applicant uploads something, any of the clerk / technical expert / dehyari either confirms it (``verify``) or sends it back with a reason
(``send_back``), and when everything of the step is confirmed any of them ends the step (``finish``) and the file moves on. Each step module used to carry
its own copy of that. Here it is written once; a step module declares a ``Step`` (its stage, the state field and the words it uses) and exposes the
methods, keeping its own few special actions (the page data, the upload fields, the extra form).

Also here: the small helpers all the step modules need (``clean``, ``now``, ``documents``, ``replace_documents``, ``notify_staff``).
"""
from dataclasses import dataclass, field
from typing import Callable, Optional

from django.db import transaction
from django.utils import timezone

from main.models import PermitDocument
from main.notifications import notify
from main.office import permit_request
from main.office.errors import Conflict, Forbidden, Invalid
from main.office.permits import may_open

MAX_FILES = 6
FINISH_TICK = 'تیک «مدارک این مرحله را بررسی کردم» لازم است.'


def clean(value, limit=150):
    return ' '.join(str(value or '').split())[:limit]


def now():
    return timezone.localtime().strftime('%Y/%m/%d %H:%M')


def documents(permit, *kinds):
    return list(permit.documents.filter(kind__in=kinds))


def replace_documents(permit, kind, found, user):
    """The applicant sent new scans: they replace the old ones of this kind."""
    for old in documents(permit, kind):
        old.document.delete(save=False)
        old.delete()
    for upload in found:
        PermitDocument.objects.create(file=permit, kind=kind, document=upload, original_name=upload.name[:200], size=upload.size, uploaded_by=user)


def staff_of(permit):
    """The clerk, the technical expert and the dehyari of the file's village (the people a step's events are told to)."""
    from main.office import permit_step2, permits       # pylint: disable=import-outside-toplevel
    return list(permits._staff_to_tell(permit_step2._village(permit)))          # pylint: disable=protected-access


def notify_staff(permit, title, text):
    for staff in staff_of(permit):
        notify(staff, title, text, request=permit.request)


def _nested(permit, path):
    """The dict at ``path`` ((field,) or (field, key)) as a mutable copy, and a function that stores it back."""
    top = dict(getattr(permit, path[0]) or {})
    if len(path) == 1:
        return top, lambda value: setattr(permit, path[0], value)

    def store(value):
        top[path[1]] = value
        setattr(permit, path[0], top)
    return dict(top.get(path[1]) or {}), store


@dataclass(frozen=True)
class Step:
    stage: int
    state_field: str                      # e.g. 'reply_state'
    data_path: tuple                      # where the 'checked' stamp lives: ('commit', 'reply') or ('pack',)
    # the words (every message of the protocol, in Persian)
    not_here: str                         # "the file is not at this step"
    nothing_to_verify: str
    verify_tick: str
    verified_title: str
    verified_text: str                    # may use {pk}
    nothing_to_send_back: str
    reason_needed: str
    back_prefix: str                      # prefix of the reason shown to the applicant
    blocking_text: str
    history: str                          # workflow history line when the step is confirmed
    done_title: str
    done_text: str                        # may use {pk}
    to_stage: int = 0                     # 0 = stage + 1
    finish_tick: str = FINISH_TICK
    after: Optional[Callable] = field(default=None, compare=False)       # called with the permit after the step ended

    # --- state ---
    def at_step(self, permit):
        return permit.unlicensed and permit.stage_no == self.stage and permit.state == 'done'

    def state(self, permit):
        return getattr(permit, self.state_field)

    def blocking(self, permit):
        return [] if self.state(permit) == 'verified' else [self.blocking_text]

    # --- the three staff actions ---
    @transaction.atomic
    def verify(self, actor, permit, post):
        if not may_open(actor, permit):
            raise Forbidden('اجازه‌ی تایید را ندارید.')
        if not self.at_step(permit) or self.state(permit) != 'uploaded':
            raise Conflict(self.nothing_to_verify)
        if post.get('confirm') != 'on':
            raise Invalid(self.verify_tick)
        data, store = _nested(permit, self.data_path)
        data['checked'] = {'by': actor.get_full_name() or actor.username, 'at': now()}
        store(data)
        setattr(permit, self.state_field, 'verified')
        permit.save(update_fields=[self.data_path[0], self.state_field, 'updated_at'])
        notify(permit.request.user, self.verified_title, self.verified_text.format(pk=permit.pk), request=permit.request)
        return permit

    @transaction.atomic
    def send_back(self, actor, permit, notes):
        if not may_open(actor, permit):
            raise Forbidden('اجازه‌ی این کار را ندارید.')
        if not self.at_step(permit) or self.state(permit) != 'uploaded':
            raise Conflict(self.nothing_to_send_back)
        notes = (notes or '').strip()
        if not notes:
            raise Invalid(self.reason_needed)
        permit_request.ask_for_documents(permit, actor, f'{self.back_prefix}: {notes}')
        setattr(permit, self.state_field, 'returned')
        permit.staff_notes = notes[:2000]
        permit.save(update_fields=[self.state_field, 'staff_notes', 'updated_at'])
        return permit

    @transaction.atomic
    def finish(self, actor, permit, post):
        if not may_open(actor, permit):
            raise Forbidden('اجازه‌ی تایید این مرحله را ندارید.')
        if not self.at_step(permit):
            raise Conflict(self.not_here)
        waiting = self.blocking(permit)
        if waiting:
            raise Conflict(waiting[0])
        if post.get('confirm') != 'on':
            raise Invalid(self.finish_tick)
        permit.stage_no = self.to_stage or self.stage + 1
        permit.staff_notes = (post.get('notes') or '')[:2000]
        permit.save()
        sr = permit.request
        sr.add_workflow_step(action=self.history, from_user=actor, to_role='citizen', notes=permit.staff_notes)
        sr.save(update_fields=['workflow_history', 'updated_at'])
        notify(sr.user, self.done_title, self.done_text.format(pk=permit.pk), request=sr)
        if self.after:
            self.after(permit)
        return permit


def announce_upload(permit, user, *, was_returned, history, staff_title, staff_text, to_role='engineer'):
    """After the applicant's upload: a first upload is a history line; a re-upload after «returned» puts the request back with the staff. The staff are told."""
    sr = permit.request
    if was_returned:
        permit_request.resubmitted(sr, user)
    else:
        sr.add_workflow_step(action=history, from_user=user, to_role=to_role)
        sr.save(update_fields=['workflow_history', 'updated_at'])
    notify_staff(permit, staff_title, staff_text)
