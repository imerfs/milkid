"""Construction without a permit, step 3: the warning notice (اخطاریه به مالک, form 14) the owner already received.

The dehyari warns the owner of a building put up without a permit (form 14: the building without a permit, its breaches, inside or outside the
village master plan, handed to the owner or his relatives, or posted on the building). The owner uploads the scan of that notice and types its
figures (number, date, plan position, how it was delivered, the name on it). Any of the clerk / technical expert / dehyari (``permit.open``)
compares them with the paper (and with the file: the owner's name, a number already used in another file) and confirms, or sends it back with a
reason; confirming moves the file to step 4.
"""
from django.db import transaction
from django.utils import timezone

from main import lifecycle
from main.models import PermitDocument, PermitFile
from main.notifications import notify
from main.office import permit_form, permit_step2, permits
from main.office.errors import Conflict, Forbidden, Invalid, NotFound
from main.office.permits import may_open

POSITIONS = {'inside': 'داخل طرح هادی', 'outside': 'خارج از طرح هادی'}
DELIVERIES = {'handed': 'تحویل مالک / بستگان گردید', 'posted': 'در محل الصاق شد'}
OPEN_STATES = ('', 'returned')
MAX_SCANS = 6
KIND = 'warning_notice'


def _clean(value, limit=150):
    return ' '.join(str(value or '').split())[:limit]


def at_step(permit):
    return permit.unlicensed and permit.stage_no == 3 and permit.state == 'done'


def find(user, file_id):
    permit = permits.find(user, file_id, any_track=True)
    return permit if permit is not None and permit.unlicensed else None


def defaults(permit):
    return {'number': '', 'date': '', 'position': '', 'delivery': '', 'addressee': permit.people.first().full_name}


def data(permit):
    return {**defaults(permit), **{k: v for k, v in (permit.notice or {}).items() if k in defaults(permit)}}


def documents(permit):
    return list(permit.documents.filter(kind=KIND))


def clean(post):
    """The figures of the notice as typed; returns (values, errors)."""
    errors = {}
    values = {'number': _clean(post.get('number'), 40), 'addressee': _clean(post.get('addressee'), 120),
              'position': post.get('position', ''), 'delivery': post.get('delivery', '')}
    if not values['number']:
        errors['number'] = 'شماره‌ی اخطاریه را وارد کنید.'
    date = permit_form._jalali(post.get('date', ''))               # pylint: disable=protected-access
    if not date:
        errors['date'] = 'تاریخ اخطاریه را به شکل ۱۴۰۲/۱۰/۱۸ وارد کنید.'
    elif date > permit_step2.today():
        errors['date'] = 'تاریخ اخطاریه نمی‌تواند در آینده باشد.'
    values['date'] = date or ''
    if values['position'] not in POSITIONS:
        errors['position'] = 'داخل یا خارج از طرح هادی بودن را انتخاب کنید.'
    if values['delivery'] not in DELIVERIES:
        errors['delivery'] = 'نحوه‌ی ابلاغ اخطاریه را انتخاب کنید.'
    if not values['addressee']:
        errors['addressee'] = 'نامی را که روی اخطاریه آمده وارد کنید.'
    return values, errors


def checks(permit):
    """What the staff should look at beside the scan: [(level, text)] with level ok / warn."""
    out, values = [], data(permit)
    owner = permit.people.first()
    if owner and owner.last_name and owner.last_name in values['addressee']:
        out.append(('ok', 'نام روی اخطاریه با مالک پرونده می‌خواند.'))
    else:
        out.append(('warn', f'نام روی اخطاریه («{values["addressee"]}») با مالک پرونده («{owner.full_name if owner else ""}») نمی‌خواند.'))
    clash = PermitFile.objects.filter(track='unlicensed', notice__number=values['number']).exclude(pk=permit.pk).exists() if values['number'] else False
    out.append(('warn', 'همین شماره‌ی اخطاریه در پرونده‌ی دیگری هم ثبت شده است.') if clash else ('ok', 'شماره‌ی اخطاریه در پرونده‌ی دیگری نیست.'))
    out.append(('ok' if documents(permit) else 'warn', 'تصویر اخطاریه بارگذاری شده است.' if documents(permit) else 'تصویر اخطاریه بارگذاری نشده است.'))
    return out


def _staff(permit):
    return permits._staff_to_tell(permit_step2._village(permit))       # pylint: disable=protected-access


@transaction.atomic
def upload(user, permit, post, files):
    """The owner uploads the notice's scan and types its figures."""
    if permit.request.user_id != user.id:
        raise NotFound('پرونده پیدا نشد.')
    if not at_step(permit):
        raise Conflict('پرونده در مرحله‌ی اخطاریه نیست.')
    if permit.notice_state not in OPEN_STATES:
        raise Conflict('اخطاریه قبلاً فرستاده شده است.')
    found, error = permit_form._uploads(files, 'scan', permit_form.ID_EXTENSIONS)          # pylint: disable=protected-access
    if error:
        raise Invalid(error)
    if not found and not documents(permit):
        raise Invalid('تصویر اخطاریه (همه‌ی صفحه‌ها) را بارگذاری کنید.')
    if len(found) > MAX_SCANS:
        raise Invalid(f'حداکثر {MAX_SCANS} فایل می‌توانید بفرستید.')
    values, errors = clean(post)
    if errors:
        raise Invalid(next(iter(errors.values())))
    was_returned = permit.notice_state == 'returned'
    if found:
        for old in documents(permit):                      # new scans replace the ones the staff sent back
            old.document.delete(save=False)
            old.delete()
        for scan in found:
            PermitDocument.objects.create(file=permit, kind=KIND, document=scan, original_name=scan.name[:200], size=scan.size, uploaded_by=user)
    permit.notice, permit.notice_state, permit.notice_at = values, 'uploaded', timezone.now()
    permit.save(update_fields=['notice', 'notice_state', 'notice_at', 'updated_at'])
    sr = permit.request
    if was_returned:
        lifecycle.permit_resubmitted(sr, user)
    else:
        sr.add_workflow_step(action='ارسال اخطاریه‌ی دریافتی توسط متقاضی (مرحله ۳)', from_user=user, to_role='engineer')
        sr.save(update_fields=['workflow_history', 'updated_at'])
    for staff in _staff(permit):
        notify(staff, 'اخطاریه‌ی مالک رسید', f'متقاضی اخطاریه‌ی پرونده {permit.pk} را فرستاد؛ منتظر تایید است.', request=sr)
    return permit


@transaction.atomic
def verify(actor, permit, post):
    """Any of the clerk / technical expert / dehyari: the notice is genuine and matches the file; the figures may be corrected."""
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی تایید این اخطاریه را ندارید.')
    if not at_step(permit) or permit.notice_state != 'uploaded':
        raise Conflict('اخطاریه‌ای برای تایید وجود ندارد.')
    if post.get('confirm') != 'on':
        raise Invalid('تیک «اخطاریه را با اصل آن مقایسه و صحت مشخصاتش را بررسی کردم» لازم است.')
    values, errors = clean(post)
    if errors:
        raise Invalid(next(iter(errors.values())))
    values['checked'] = {'by': actor.get_full_name() or actor.username, 'at': timezone.now().strftime('%Y-%m-%d %H:%M')}
    permit.notice, permit.notice_state, permit.stage_no = values, 'verified', 4
    permit.staff_notes = (post.get('notes') or '')[:2000]
    permit.save()
    sr = permit.request
    sr.add_workflow_step(action=f'تایید اخطاریه‌ی مالک (شماره {values["number"]}) - پایان مرحله ۳', from_user=actor, to_role='engineer', notes=permit.staff_notes)
    sr.save(update_fields=['workflow_history', 'updated_at'])
    notify(sr.user, 'اخطاریه‌ی شما تایید شد', f'دهیاری اخطاریه‌ی پرونده {permit.pk} (شماره {values["number"]}) را تایید کرد؛ پرونده به مرحله‌ی ۴ رفت.', request=sr)
    return permit


@transaction.atomic
def send_back(actor, permit, notes):
    """The scan is unreadable or does not match the figures: the owner uploads it again."""
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی این کار را ندارید.')
    if not at_step(permit) or permit.notice_state != 'uploaded':
        raise Conflict('اخطاریه‌ای برای برگرداندن وجود ندارد.')
    notes = (notes or '').strip()
    if not notes:
        raise Invalid('بنویسید مشکل اخطاریه چیست.')
    lifecycle.request_documents(permit.request, actor, f'اخطاریه‌ی مالک: {notes}')
    permit.notice_state, permit.staff_notes = 'returned', notes[:2000]
    permit.save(update_fields=['notice_state', 'staff_notes', 'updated_at'])
    return permit
