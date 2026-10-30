"""Construction without a permit, step 4, after the visit report: the electricity office's answer, the materials in the street, the end.

- **An overhang over the street** (the report's column «پیش‌آمدگی به معبر»): the owner must ask the electricity distribution office for
  its opinion. The system fills the owner's request and the dehyari's letter to the office (built or not built overhang, the passages'
  width, the balcony depth, the distance from the network) from the report; the owner prints them, gets the dehyari's signature, takes
  the letter to the office, brings the answer back to the dehyari and uploads its scan here with the answer's figures.
- **Materials in the street:** the owner must clear them and upload photos of the cleared street; the file does not go on until the staff
  confirm the photos.
- **Ending the step** (any of the clerk / technical expert / dehyari): when the report is filed and neither of the above is outstanding,
  the staff confirm the step and the file goes on to step 5.
Every part is confirmed, or sent back with a reason, by any of the three staff (``permit.open``).
"""
from django.db import transaction
from django.utils import timezone

from main.office import permit_request
from main import lifecycle
from main.models import PermitDocument
from main.notifications import notify
from main.office import permit_form, permit_report, permit_step2, permits
from main.office.errors import Conflict, Forbidden, Invalid, NotFound
from main.office.permits import may_open

POWER_KIND, PHOTO_KIND = 'power_reply', 'materials_photo'
VERDICTS = {'approved': 'اداره برق موافقت کرد', 'denied': 'اداره برق موافقت نکرد'}
MAX_FILES = 8


def _staff(permit):
    return permits._staff_to_tell(permit_step2._village(permit))       # pylint: disable=protected-access


def _clean(value, limit=150):
    return ' '.join(str(value or '').split())[:limit]


def documents(permit, kind):
    return list(permit.documents.filter(kind=kind))


def _replace(permit, kind, found, user):
    for old in documents(permit, kind):
        old.document.delete(save=False)
        old.delete()
    for upload in found:
        PermitDocument.objects.create(file=permit, kind=kind, document=upload, original_name=upload.name[:200], size=upload.size, uploaded_by=user)


def blocking(permit):
    """What still stops the step from being confirmed: a list of sentences (empty when nothing does)."""
    out = []
    if permit.report_state != 'filed':
        out.append('گزارش بازدید هنوز در پرونده نیست.')
    if permit.overhang_state not in ('', 'verified'):
        out.append('پاسخ اداره برق درباره‌ی پیش‌آمدگی هنوز تایید نشده است.')
    if permit.materials_state not in ('', 'verified'):
        out.append('جمع‌آوری مصالح از معبر هنوز تایید نشده است.')
    return out


def _owner_check(user, permit):
    if permit.request.user_id != user.id:
        raise NotFound('پرونده پیدا نشد.')
    if not permit_report.at_step(permit):
        raise Conflict('پرونده در مرحله‌ی گزارش بازدید نیست.')


# ---------- the electricity office ----------

def power_payload(permit):
    """What the two letters need, from the report (the owner's request and the dehyari's letter to the electricity distribution office)."""
    values = permit_report.data(permit)
    rows = []
    for side, label in permit_report.SIDES:
        row = values['overhang_rows'][side]
        limit = values['limits'][side]
        if row.get('balcony') or row.get('passage') or (limit.get('adjacent') == 'معبر'):
            rows.append({'side': label, 'passage': row.get('passage') or limit.get('passage') or '', 'sidewalk': row.get('sidewalk') or '',
                         'balcony': row.get('balcony') or '', 'network': row.get('network') or ''})
    return {'built': values['overhang_built'], 'rows': rows, 'owner': values['name'], 'father': values['father'], 'address': values['address'],
            'utm': (f'UTM: {values["utm_x"]}, {values["utm_y"]}' if values['utm_x'] and values['utm_y'] else ''),
            'phone': values['phone'], 'national_id': values['national_id'], 'village': permit_step2._village(permit)}        # pylint: disable=protected-access


@transaction.atomic
def upload_power_reply(user, permit, post, files):
    """The owner uploads the electricity office's answer (scan) and types its number, date and sense."""
    _owner_check(user, permit)
    if permit.overhang_state not in ('required', 'returned'):
        raise Conflict('پاسخ اداره برق لازم نیست یا قبلاً فرستاده شده است.')
    found, error = permit_form._uploads(files, 'scan', permit_form.ID_EXTENSIONS)        # pylint: disable=protected-access
    if error:
        raise Invalid(error)
    if not found and not documents(permit, POWER_KIND):
        raise Invalid('تصویر نامه‌ی پاسخ اداره برق را بارگذاری کنید.')
    if len(found) > MAX_FILES:
        raise Invalid(f'حداکثر {MAX_FILES} فایل می‌توانید بفرستید.')
    number = _clean(post.get('letter_no'), 40)
    date = permit_form._jalali(post.get('letter_date', ''))                      # pylint: disable=protected-access
    verdict = post.get('verdict', '')
    if not number:
        raise Invalid('شماره‌ی نامه‌ی اداره برق را وارد کنید.')
    if not date or date > permit_step2.today():
        raise Invalid('تاریخ نامه را به شکل ۱۴۰۵/۰۶/۲۲ وارد کنید (نمی‌تواند در آینده باشد).')
    if verdict not in VERDICTS:
        raise Invalid('نظر اداره برق (موافقت یا عدم موافقت) را انتخاب کنید.')
    if found:
        _replace(permit, POWER_KIND, found, user)
    permit.overhang = {**(permit.overhang or {}), 'letter_no': number, 'letter_date': date, 'verdict': verdict, 'at': timezone.now().strftime('%Y-%m-%d %H:%M')}
    was_returned = permit.overhang_state == 'returned'
    permit.overhang_state = 'replied'
    permit.save(update_fields=['overhang', 'overhang_state', 'updated_at'])
    sr = permit.request
    if was_returned:
        permit_request.resubmitted(sr, user)
    else:
        sr.add_workflow_step(action='ارسال پاسخ اداره برق توسط متقاضی (مرحله ۴)', from_user=user, to_role='engineer')
        sr.save(update_fields=['workflow_history', 'updated_at'])
    for staff in _staff(permit):
        notify(staff, 'پاسخ اداره برق رسید', f'متقاضی پاسخ اداره برق پرونده {permit.pk} را فرستاد؛ منتظر تایید است.', request=sr)
    return permit


@transaction.atomic
def verify_power(actor, permit, post):
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی تایید را ندارید.')
    if not permit_report.at_step(permit) or permit.overhang_state != 'replied':
        raise Conflict('پاسخی برای تایید نیست.')
    if post.get('confirm') != 'on':
        raise Invalid('تیک «پاسخ اداره برق را با اصل نامه مقایسه و بررسی کردم» لازم است.')
    data_ = dict(permit.overhang or {})
    data_['checked'] = {'by': actor.get_full_name() or actor.username, 'at': timezone.now().strftime('%Y-%m-%d %H:%M')}
    permit.overhang, permit.overhang_state = data_, 'verified'
    permit.save(update_fields=['overhang', 'overhang_state', 'updated_at'])
    notify(permit.request.user, 'پاسخ اداره برق تایید شد', f'پاسخ اداره برق پرونده {permit.pk} تایید شد.', request=permit.request)
    return permit


@transaction.atomic
def return_power(actor, permit, notes):
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی این کار را ندارید.')
    if not permit_report.at_step(permit) or permit.overhang_state != 'replied':
        raise Conflict('پاسخی برای برگرداندن نیست.')
    notes = (notes or '').strip()
    if not notes:
        raise Invalid('بنویسید مشکل پاسخ چیست.')
    permit_request.ask_for_documents(permit, actor, f'پاسخ اداره برق: {notes}')
    permit.overhang_state, permit.staff_notes = 'returned', notes[:2000]
    permit.save(update_fields=['overhang_state', 'staff_notes', 'updated_at'])
    return permit


# ---------- the materials in the street ----------

@transaction.atomic
def upload_materials(user, permit, post, files):
    """The owner uploads photos of the street after clearing the materials."""
    _owner_check(user, permit)
    if permit.materials_state not in ('required', 'returned'):
        raise Conflict('جمع‌آوری مصالح لازم نیست یا عکس‌ها قبلاً فرستاده شده است.')
    if post.get('cleared') != 'on':
        raise Invalid('تیک «مصالح را از معبر جمع کرده‌ام» لازم است.')
    found, error = permit_form._uploads(files, 'photo', ('.jpg', '.jpeg', '.png'))          # pylint: disable=protected-access
    if error:
        raise Invalid(error)
    if not found and not documents(permit, PHOTO_KIND):
        raise Invalid('دست‌کم یک عکس از معبر پس از جمع‌آوری مصالح بارگذاری کنید.')
    if len(found) > MAX_FILES:
        raise Invalid(f'حداکثر {MAX_FILES} عکس می‌توانید بفرستید.')
    if found:
        _replace(permit, PHOTO_KIND, found, user)
    permit.materials = {**(permit.materials or {}), 'at': timezone.now().strftime('%Y-%m-%d %H:%M'), 'note': _clean(post.get('note'), 300)}
    was_returned = permit.materials_state == 'returned'
    permit.materials_state = 'uploaded'
    permit.save(update_fields=['materials', 'materials_state', 'updated_at'])
    sr = permit.request
    if was_returned:
        permit_request.resubmitted(sr, user)
    else:
        sr.add_workflow_step(action='ارسال عکس جمع‌آوری مصالح توسط متقاضی (مرحله ۴)', from_user=user, to_role='engineer')
        sr.save(update_fields=['workflow_history', 'updated_at'])
    for staff in _staff(permit):
        notify(staff, 'عکس جمع‌آوری مصالح', f'متقاضی پرونده {permit.pk} عکس جمع‌آوری مصالح را فرستاد؛ منتظر تایید است.', request=sr)
    return permit


@transaction.atomic
def verify_materials(actor, permit, post):
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی تایید را ندارید.')
    if not permit_report.at_step(permit) or permit.materials_state != 'uploaded':
        raise Conflict('عکسی برای تایید نیست.')
    if post.get('confirm') != 'on':
        raise Invalid('تیک «در عکس‌ها معبر از مصالح خالی است» لازم است.')
    data_ = dict(permit.materials or {})
    data_['checked'] = {'by': actor.get_full_name() or actor.username, 'at': timezone.now().strftime('%Y-%m-%d %H:%M')}
    permit.materials, permit.materials_state = data_, 'verified'
    permit.save(update_fields=['materials', 'materials_state', 'updated_at'])
    notify(permit.request.user, 'جمع‌آوری مصالح تایید شد', f'عکس‌های جمع‌آوری مصالح پرونده {permit.pk} تایید شد.', request=permit.request)
    return permit


@transaction.atomic
def return_materials(actor, permit, notes):
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی این کار را ندارید.')
    if not permit_report.at_step(permit) or permit.materials_state != 'uploaded':
        raise Conflict('عکسی برای برگرداندن نیست.')
    notes = (notes or '').strip()
    if not notes:
        raise Invalid('بنویسید مشکل عکس‌ها چیست.')
    permit_request.ask_for_documents(permit, actor, f'جمع‌آوری مصالح: {notes}')
    permit.materials_state, permit.staff_notes = 'returned', notes[:2000]
    permit.save(update_fields=['materials_state', 'staff_notes', 'updated_at'])
    return permit


# ---------- the end of the step ----------

@transaction.atomic
def finish(actor, permit, post):
    """Any of the three staff: the report is in the file and nothing is outstanding; the file goes on to step 5."""
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی تایید این مرحله را ندارید.')
    if not permit_report.at_step(permit):
        raise Conflict('پرونده در مرحله‌ی گزارش بازدید نیست.')
    waiting = blocking(permit)
    if waiting:
        raise Conflict(waiting[0])
    if post.get('confirm') != 'on':
        raise Invalid('تیک «گزارش و مدارک این مرحله را بررسی کردم» لازم است.')
    permit.stage_no = 5
    permit.staff_notes = (post.get('notes') or '')[:2000]
    permit.save()
    sr = permit.request
    sr.add_workflow_step(action='تایید مرحله ۴ (گزارش بازدید، پیش‌آمدگی و مصالح)', from_user=actor, to_role='citizen', notes=permit.staff_notes)
    sr.save(update_fields=['workflow_history', 'updated_at'])
    notify(sr.user, 'مرحله‌ی ۴ تایید شد', f'مرحله‌ی گزارش بازدید پرونده {permit.pk} تایید شد؛ پرونده به مرحله‌ی ۵ رفت.', request=sr)
    return permit
