"""Construction without a permit, step 2: the owner's request form and undertaking, signed on paper and uploaded.

After the staff confirm step 1 (the initial file), the owner fills two forms the village keeps for the Article 99 commission file:
the «فرم درخواست» (asks the dehyari to form the commission file and to take the village's fees and the commission's fine in
instalments) and the «تعهدنامه» (the owner's undertakings about sewage, the street, the pavement, the facade, parking, the
neighbours' consent, the village's fees, the materials in the street and its safety). The system fills both from what the file holds;
the owner prints them, signs and leaves a fingerprint, and uploads the scans. Any of the clerk / technical expert / dehyari
(``permit.open``) confirms that both papers arrived signed, or sends them back with a reason; confirming moves the file to step 3.
"""
from django.db import transaction
from django.utils import timezone

from main import lifecycle
from main.models import PermitDocument
from main.notifications import notify
from main.office import permit_form, permit_step2, permits
from main.office.errors import Conflict, Forbidden, Invalid, NotFound
from main.office.permits import may_open

KINDS = {'request': 'comm_request', 'undertaking': 'comm_undertake'}
LABELS = {'request': 'فرم درخواست', 'undertaking': 'تعهدنامه'}
FIELDS = ('name', 'father', 'id_number', 'national_id', 'street', 'phone', 'date', 'subject', 'addressee')
ADDRESSEES = {'council': 'شورای اسلامی روستا', 'dehyari': 'دهیار روستا'}
DEFAULT_SUBJECT = 'تشکیل پرونده کمیسیون و تقسیط هزینه‌های دهیاری و جریمه کمیسیون'
OPEN_STATES = ('', 'returned')
MAX_SCANS = 6


def _clean(value, limit=150):
    return ' '.join(str(value or '').split())[:limit]


def find(user, file_id):
    permit = permits.find(user, file_id, any_track=True)
    return permit if permit is not None and permit.unlicensed else None


def at_step(permit):
    return permit.unlicensed and permit.stage_no == 2 and permit.state == 'done'


def defaults(permit):
    """What the file already knows, for the two forms."""
    owner = permit.people.first()
    return {'name': owner.full_name, 'father': owner.father_name, 'id_number': owner.id_number, 'national_id': owner.national_id,
            'street': permit.address, 'phone': owner.phone, 'date': permit_step2.today(), 'subject': DEFAULT_SUBJECT, 'addressee': 'council'}


def payload(permit):
    form = {**defaults(permit), **{k: v for k, v in ((permit.commission or {}).get('form') or {}).items() if k in FIELDS}}
    return {'form': form, 'village': permit_step2._village(permit), 'file': permit.pk, 'addressees': ADDRESSEES,         # pylint: disable=protected-access
            'checked': (permit.commission or {}).get('checked') or {}}


def scans(permit):
    return {key: list(permit.documents.filter(kind=kind)) for key, kind in KINDS.items()}


def _may_edit(actor, permit):
    owner_open = permit.request.user_id == actor.id and permit.commission_state in OPEN_STATES
    return owner_open or (may_open(actor, permit) and permit.commission_state != 'verified')


def _require_step(permit):
    if not at_step(permit):
        raise Conflict('پرونده در مرحله‌ی فرم درخواست و تعهدنامه نیست.')


@transaction.atomic
def save_form(actor, permit, post):
    """The values printed on both forms (the owner corrects them; the staff may for a walk-in owner)."""
    _require_step(permit)
    if not _may_edit(actor, permit):
        raise Forbidden('اجازه‌ی ویرایش این فرم‌ها را ندارید.')
    values = {key: _clean(post.get(key, ''), 150) for key in FIELDS}
    national, problem = permit_form._national_id(values['national_id'])          # pylint: disable=protected-access
    if problem:
        raise Invalid(problem)
    values['national_id'] = national
    values['subject'] = _clean(post.get('subject', ''), 150) or DEFAULT_SUBJECT          # blank: the usual request
    if values['addressee'] not in ADDRESSEES:
        values['addressee'] = 'council'
    values['id_number'] = permit_form.digits(values['id_number'])[:15]
    values['phone'] = permit_form.digits(values['phone'])[:11]
    if values['phone'] and not permit_form._PHONE.match(values['phone']):          # pylint: disable=protected-access
        raise Invalid('شماره تماس را به شکل ۰۹۱۲۳۴۵۶۷۸۹ وارد کنید.')
    if not values['name']:
        raise Invalid('نام و نام خانوادگی را وارد کنید.')
    date = permit_form._jalali(values['date'])              # pylint: disable=protected-access
    if not date:
        raise Invalid('تاریخ را به شکل ۱۴۰۵/۰۶/۲۲ وارد کنید.')
    values['date'] = date
    data = dict(permit.commission or {})
    data['form'] = values
    permit.commission = data
    permit.save(update_fields=['commission', 'updated_at'])
    return permit


def _staff(permit):
    return permits._staff_to_tell(permit_step2._village(permit))       # pylint: disable=protected-access


@transaction.atomic
def upload(user, permit, post, files):
    """The owner uploads the scans of both signed papers and sends them to the staff."""
    if permit.request.user_id != user.id:
        raise NotFound('پرونده پیدا نشد.')
    _require_step(permit)
    if permit.commission_state not in OPEN_STATES:
        raise Conflict('فرم‌ها قبلاً فرستاده شده است.')
    if post.get('signed') != 'on':
        raise Invalid('تیک «هر دو برگه را امضا کرده و اثر انگشت زده‌ام» لازم است.')
    new = {}
    for key in KINDS:
        found, error = permit_form._uploads(files, f'{key}_scan', permit_form.ID_EXTENSIONS)        # pylint: disable=protected-access
        if error:
            raise Invalid(error)
        if not found and not permit.documents.filter(kind=KINDS[key]).exists():
            raise Invalid(f'تصویر «{LABELS[key]}» امضاشده را بارگذاری کنید.')
        if len(found) > MAX_SCANS:
            raise Invalid(f'حداکثر {MAX_SCANS} فایل برای هر برگه.')
        new[key] = found
    was_returned = permit.commission_state == 'returned'
    for key, found in new.items():
        if not found:
            continue
        for old in permit.documents.filter(kind=KINDS[key]):         # a new scan replaces the one the staff sent back
            old.document.delete(save=False)
            old.delete()
        for upload_file in found:
            PermitDocument.objects.create(file=permit, kind=KINDS[key], document=upload_file, original_name=upload_file.name[:200],
                                          size=upload_file.size, uploaded_by=user)
    permit.commission_state, permit.commission_at = 'uploaded', timezone.now()
    permit.save(update_fields=['commission_state', 'commission_at', 'updated_at'])
    sr = permit.request
    if was_returned:
        lifecycle.permit_resubmitted(sr, user)
    else:
        sr.add_workflow_step(action='ارسال فرم درخواست و تعهدنامه‌ی امضاشده توسط متقاضی (مرحله ۲)', from_user=user, to_role='engineer')
        sr.save(update_fields=['workflow_history', 'updated_at'])
    for staff in _staff(permit):
        notify(staff, 'فرم‌های امضاشده رسید', f'متقاضی فرم درخواست و تعهدنامه‌ی پرونده {permit.pk} را فرستاد؛ منتظر تایید است.', request=sr)
    return permit


@transaction.atomic
def verify(actor, permit, post):
    """Any of the clerk / technical expert / dehyari: both papers arrived signed, the file goes on to step 3."""
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی تایید این فرم‌ها را ندارید.')
    _require_step(permit)
    if permit.commission_state != 'uploaded':
        raise Conflict('فرمی برای تایید وجود ندارد.')
    if post.get('confirm') != 'on':
        raise Invalid('تیک «هر دو برگه با امضا و اثر انگشت متقاضی رسید» لازم است.')
    data = dict(permit.commission or {})
    data['checked'] = {'by': actor.get_full_name() or actor.username, 'at': timezone.now().strftime('%Y-%m-%d %H:%M')}
    permit.commission, permit.commission_state, permit.stage_no = data, 'verified', 3
    permit.staff_notes = (post.get('notes') or '')[:2000]
    permit.save()
    sr = permit.request
    sr.add_workflow_step(action='تایید فرم درخواست و تعهدنامه - پایان مرحله ۲', from_user=actor, to_role='engineer', notes=permit.staff_notes)
    sr.save(update_fields=['workflow_history', 'updated_at'])
    notify(sr.user, 'فرم‌های شما تایید شد', f'دهیاری فرم درخواست و تعهدنامه‌ی پرونده {permit.pk} را تایید کرد؛ پرونده به مرحله‌ی ۳ رفت.', request=sr)
    return permit


@transaction.atomic
def send_back(actor, permit, notes):
    """A paper is unreadable, unsigned or does not match: the owner uploads it again."""
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی این کار را ندارید.')
    _require_step(permit)
    if permit.commission_state != 'uploaded':
        raise Conflict('فرمی برای برگرداندن وجود ندارد.')
    notes = (notes or '').strip()
    if not notes:
        raise Invalid('بنویسید مشکل فرم‌ها چیست.')
    lifecycle.request_documents(permit.request, actor, f'فرم درخواست و تعهدنامه: {notes}')
    permit.commission_state, permit.staff_notes = 'returned', notes[:2000]
    permit.save(update_fields=['commission_state', 'staff_notes', 'updated_at'])
    return permit
