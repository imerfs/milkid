"""Construction without a permit, step 1: the shamim sketch (کروکی شمیم) for an owner who has no shamim file.

Without a shamim file the owner asks the dehyari's technical expert for a sketch of the property. It costs money, so the flow is:
the owner asks (at filing, or later in step 1) → the technical expert (or the dehyari) sets the fee → the owner pays it at the
dehyari's bank account and records the slip (number, Jalali date, amount, optional scan) → the technical expert / dehyari confirm the
payment and deliver the sketch file, which becomes the file's shamim file (read like any other, so the plot of the village map is
suggested). Fees are not posted to the books here; the dehyari's accountant records the bank deposit as for any other slip.
"""
from django.db import transaction
from django.utils import timezone

from main.access import can
from main.accounting.parse import digits
from main.models import PermitDocument
from main.notifications import notify
from main.office import permit_form, permit_step2, permits
from main.office.errors import Conflict, Forbidden, Invalid, NotFound

OPEN_FILE_STATES = ('submitted', 'needs_docs')
MAX_FEE = 10_000_000_000


def _now():
    return timezone.now().strftime('%Y-%m-%d %H:%M')


def find(user, file_id):
    permit = permits.find(user, file_id, any_track=True)
    return permit if permit is not None and permit.unlicensed else None


def may_work(user, permit):
    """The technical expert and the dehyari of the file's village price, confirm and deliver the sketch."""
    return can(user, 'permit.sketch') and permits.files_for(user).filter(pk=permit.pk).exists()


def at_step(permit):
    return permit.unlicensed and permit.stage_no == 1 and permit.state in OPEN_FILE_STATES


def slips(permit):
    return list(permit.documents.filter(kind='sketch_slip'))


def sketch_files(permit):
    return list(permit.documents.filter(kind='shamim'))


def _staff(permit):
    return permits._staff_to_tell(permit_step2._village(permit))        # pylint: disable=protected-access


@transaction.atomic
def request(user, permit):
    """The owner (no shamim file) asks for the sketch."""
    if permit.request.user_id != user.id:
        raise NotFound('پرونده پیدا نشد.')
    if not at_step(permit):
        raise Conflict('پرونده در مرحله‌ی اول نیست.')
    if permit.sketch_state:
        raise Conflict('درخواست کروکی قبلاً ثبت شده است.')
    if sketch_files(permit):
        raise Conflict('فایل شمیم دارید؛ نیازی به کروکی نیست.')
    permit.sketch_state, permit.sketch, permit.sketch_at = 'requested', {'requested_at': _now()}, timezone.now()
    permit.save(update_fields=['sketch', 'sketch_state', 'sketch_at', 'updated_at'])
    for staff in _staff(permit):
        notify(staff, 'درخواست کروکی شمیم', f'متقاضی پرونده {permit.pk} فایل شمیم ندارد و کروکی می‌خواهد؛ هزینه‌اش را تعیین کنید.', request=permit.request)
    return permit


def _fee(value):
    text = digits(value).replace(',', '').replace('٬', '')
    if not text.isdigit() or not 0 < int(text) <= MAX_FEE:
        raise Invalid('هزینه را به ریال و به‌صورت عدد وارد کنید.')
    return int(text)


@transaction.atomic
def set_fee(actor, permit, post):
    """The technical expert (or the dehyari) sets the fee; it can be changed until the owner pays."""
    if not may_work(actor, permit):
        raise Forbidden('اجازه‌ی تعیین هزینه را ندارید.')
    if not at_step(permit) or permit.sketch_state not in ('requested', 'priced'):
        raise Conflict('کروکی در مرحله‌ی تعیین هزینه نیست.')
    fee = _fee(post.get('fee', ''))
    data = dict(permit.sketch or {})
    data.update({'fee': fee, 'priced_by': actor.get_full_name() or actor.username, 'priced_at': _now(), 'note': ' '.join(str(post.get('note', '')).split())[:300]})
    permit.sketch, permit.sketch_state = data, 'priced'
    permit.save(update_fields=['sketch', 'sketch_state', 'updated_at'])
    notify(permit.request.user, 'هزینه‌ی کروکی شمیم', f'هزینه‌ی کروکی شمیم پرونده {permit.pk} {fee:,} ریال تعیین شد؛ پرداخت کنید و فیش را ثبت کنید.', request=permit.request)
    return permit


@transaction.atomic
def pay(user, permit, post, files):
    """The owner records the bank slip of the fee."""
    if permit.request.user_id != user.id:
        raise NotFound('پرونده پیدا نشد.')
    if not at_step(permit) or permit.sketch_state != 'priced':
        raise Conflict('هزینه‌ای برای پرداخت تعیین نشده است.')
    data = dict(permit.sketch or {})
    amount = _fee(post.get('amount', ''))
    if amount != data.get('fee'):
        raise Invalid(f'مبلغ فیش باید دقیقاً {data.get("fee", 0):,} ریال باشد.')
    number = ' '.join(str(post.get('number', '')).split())[:40]
    if not number:
        raise Invalid('شماره‌ی فیش را وارد کنید.')
    date = permit_form._jalali(post.get('date', ''))                  # pylint: disable=protected-access
    if not date or date > permit_step2.today():
        raise Invalid('تاریخ فیش را به شکل ۱۴۰۵/۰۶/۲۲ وارد کنید (نمی‌تواند در آینده باشد).')
    found, error = permit_form._uploads(files, 'slip', permit_form.ID_EXTENSIONS)        # pylint: disable=protected-access
    if error:
        raise Invalid(error)
    if found:
        for old in slips(permit):
            old.document.delete(save=False)
            old.delete()
        for scan in found[:3]:
            PermitDocument.objects.create(file=permit, kind='sketch_slip', document=scan, original_name=scan.name[:200], size=scan.size, uploaded_by=user)
    data['payment'] = {'number': number, 'date': date, 'amount': amount, 'at': _now()}
    permit.sketch, permit.sketch_state = data, 'paid'
    permit.save(update_fields=['sketch', 'sketch_state', 'updated_at'])
    for staff in _staff(permit):
        notify(staff, 'فیش هزینه‌ی کروکی', f'متقاضی پرونده {permit.pk} فیش هزینه‌ی کروکی را ثبت کرد؛ پرداخت را تایید و کروکی را تحویل دهید.', request=permit.request)
    return permit


@transaction.atomic
def deliver(actor, permit, post, files):
    """The technical expert / dehyari confirm the payment and hand over the sketch: it becomes the file's shamim file."""
    if not may_work(actor, permit):
        raise Forbidden('اجازه‌ی تحویل کروکی را ندارید.')
    if not at_step(permit) or permit.sketch_state != 'paid':
        raise Conflict('پرداختی برای تایید وجود ندارد.')
    if post.get('confirm') != 'on':
        raise Invalid('تیک «فیش پرداخت را بررسی و تایید کردم» لازم است.')
    found, error = permit_form._uploads(files, 'sketch', permit_form.SHAMIM_EXTENSIONS)        # pylint: disable=protected-access
    if error:
        raise Invalid(error)
    if len(found) != 1:
        raise Invalid('فایل کروکی شمیم را (یک فایل؛ چند فایل را zip کنید) بارگذاری کنید.')
    upload = found[0]
    PermitDocument.objects.create(file=permit, kind='shamim', document=upload, original_name=upload.name[:200], size=upload.size, uploaded_by=actor)
    data = dict(permit.sketch or {})
    data['delivered'] = {'by': actor.get_full_name() or actor.username, 'at': _now()}
    permit.sketch, permit.sketch_state = data, 'delivered'
    permit.save(update_fields=['sketch', 'sketch_state', 'updated_at'])
    try:
        permit_step2.refresh_shamim(permit)
    except Exception:             # pylint: disable=broad-except   # reading the drawing must never lose the delivery
        pass
    notify(permit.request.user, 'کروکی شمیم تحویل شد', f'کروکی شمیم پرونده {permit.pk} تایید و در پرونده‌ی شما ثبت شد.', request=permit.request)
    return permit
