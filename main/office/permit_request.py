"""The one place where a permit file's steps are mirrored onto its ServiceRequest.

A request that has a permit file has two states: the file's (stage, step states) and the request's (status, workflow stage, history shown in the old
panels). The file drives; every step module changes the request only through this module, so the two cannot drift apart. The generic ``main.lifecycle``
knows nothing about permits: this module registers a guard there that refuses the old panels' approve / reject / refer / status actions for a request that
has a file (they would close or re-route the request while the file stays at its step).
"""
from main import lifecycle
from main.models import PermitFile
from main.notifications import notify


def _has_file(sr):
    return PermitFile.objects.filter(request=sr).exists()


def guard(sr):
    if _has_file(sr):
        raise lifecycle.TransitionError('این درخواست پرونده‌ی ساختمانی است؛ مراحل آن را از صفحه‌ی خود پرونده انجام دهید.')


lifecycle.register_guard(guard)


def opened(sr, actor, *, code, notes=''):
    """Step 1 of a building permit (افتتاح پرونده) is done: the file has its renewal code and moves on."""
    lifecycle.ensure_open(sr)
    sr.parcel_number = code
    lifecycle.ensure_not_locked(sr)
    lifecycle.finish(sr, actor, status='in_review', stage='expert_review',
                     action=f'افتتاح پرونده پروانه و ثبت کد نوسازی {code}', notes=notes, to_role='engineer')
    what = 'ساخت‌وساز بدون پروانه' if sr.request_type == 'no_permit' else 'پروانه ساختمان'
    notify(sr.user, f'پرونده شما تایید شد: {sr.title}' if sr.request_type == 'no_permit' else f'پرونده شما افتتاح شد: {sr.title}',
           f'مرحله‌ی ۱ پرونده‌ی {what} شما تایید شد و کد نوسازی ملک شما {code} است. مرحله‌ی بعد را در پرونده ببینید.', request=sr)


def resubmitted(sr, actor):
    """The applicant added the missing papers: the file is waiting for the staff again."""
    lifecycle.ensure_open(sr)
    lifecycle.finish(sr, actor, status='pending', stage='expert_review', action='ارسال مجدد مدارک توسط متقاضی', to_role='engineer')


def ask_for_documents(permit, actor, notes):
    """The staff sent a step back to the applicant with a reason."""
    with lifecycle.unguarded():
        lifecycle.request_documents(permit.request, actor, notes)


def reject(permit, actor, reason):
    """The file is refused: the request is rejected with it."""
    with lifecycle.unguarded():
        lifecycle.reject(permit.request, actor, reason)
