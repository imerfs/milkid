"""Construction without a permit, step 8: the Bonyad-e Maskan's visit list and the Bonyad's letter.

The owner asks to be put on the Bonyad's visit list. When the visit is done the technical expert (or the dehyari) records it, which shows the owner the
package that goes with the dehyari's letter to the Bonyad: the shamim sketch, the judiciary expert's reply, the technical expert's report, the payments and the
letter itself (typeset from the file). The owner is told by SMS and a notification. The owner then uploads the letter received from the Bonyad with its number
and date; any of the clerk / technical expert / dehyari confirms it (or sends it back with a reason) and then the step; the file goes on to step 9.
"""
from django.db import transaction
from django.utils import timezone

from main.office import permit_request
from main import lifecycle, sms
from main.access import can
from main.models import PermitDocument
from main.notifications import notify
from main.office import permit_commit, permit_form, permit_step2, permits
from main.office.errors import Conflict, Forbidden, Invalid, NotFound
from main.office.permits import may_open

LETTER_KIND = 'bonyad_letter'
MAX_FILES = 6


def _clean(value, limit=150):
    return ' '.join(str(value or '').split())[:limit]


def _now():
    return timezone.localtime().strftime('%Y/%m/%d %H:%M')


def find(user, file_id):
    return permit_commit.find(user, file_id)


def at_step(permit):
    return permit.unlicensed and permit.stage_no == 8 and permit.state == 'done'


def may_visit(user, permit):
    """The technical expert and the dehyari record that the Bonyad's visit was done (policy ``permit.report``)."""
    return can(user, 'permit.report') and permits.files_for(user).filter(pk=permit.pk).exists()


def documents(permit, kind):
    return list(permit.documents.filter(kind=kind))


def package(permit):
    """What goes with the dehyari's letter to the Bonyad: the sketch, the expert's reply, the report, the payments."""
    dues = permit.dues or {}
    return {
        'sketch': documents(permit, 'shamim'),
        'expert_letter': documents(permit, 'expert_letter'), 'expert_table': documents(permit, 'expert_table'),
        'report': permit.report_state == 'filed',
        'sheet': permit.dues_state == 'issued', 'paid': permit.dues_paid, 'total': permit.dues_total,
        'payments': [p for p in dues.get('payments') or [] if p.get('ok')],
        'cheques': ((dues.get('plan') or {}).get('cheques') or []) if permit.plan_state == 'confirmed' else [],
    }


def letter_payload(permit):
    owner = permit.people.first()
    request = permit.request
    return {'village': permit_step2._village(permit), 'county': request.county.name if request.county else '',          # pylint: disable=protected-access
            'owner': owner.full_name, 'father': owner.father_name, 'national_id': owner.national_id, 'address': permit.address,
            'code': permit.renewal_code, 'date': permit_step2.today(), 'visit': (permit.bonyad_list or {}).get('visit', {})}


@transaction.atomic
def request_visit(user, permit, post):
    if permit.request.user_id != user.id:
        raise NotFound('پرونده پیدا نشد.')
    if not at_step(permit):
        raise Conflict('پرونده در مرحله‌ی لیست بازدید بنیاد نیست.')
    if permit.bonyad_list_state != '':
        raise Conflict('درخواست قبلاً ثبت شده است.')
    if post.get('confirm') != 'on':
        raise Invalid('تیک «درخواست قرار گرفتن در لیست بازدید بنیاد را دارم» لازم است.')
    permit.bonyad_list = {'requested': {'note': _clean(post.get('note'), 300), 'at': _now()}}
    permit.bonyad_list_state = 'requested'
    permit.save(update_fields=['bonyad_list', 'bonyad_list_state', 'updated_at'])
    sr = permit.request
    sr.add_workflow_step(action='درخواست قرار گرفتن در لیست بازدید بنیاد مسکن (مرحله ۸)', from_user=user, to_role='engineer')
    sr.save(update_fields=['workflow_history', 'updated_at'])
    for staff in permits._staff_to_tell(permit_step2._village(permit)):          # pylint: disable=protected-access
        notify(staff, 'لیست بازدید بنیاد', f'متقاضی پرونده {permit.pk} درخواست قرار گرفتن در لیست بازدید بنیاد را داد.', request=sr)
    return permit


@transaction.atomic
def release(actor, permit, post):
    """The technical expert records the Bonyad's visit; the owner sees the package and gets an SMS."""
    if not may_visit(actor, permit):
        raise Forbidden('تایید انجام بازدید با کارشناس فنی و دهیار است.')
    if not at_step(permit) or permit.bonyad_list_state != 'requested':
        raise Conflict('درخواستی برای تایید نیست.')
    date = permit_form._jalali(post.get('date', ''))                     # pylint: disable=protected-access
    if not date or date > permit_step2.today():
        raise Invalid('تاریخ بازدید بنیاد را به شکل ۱۴۰۵/۰۷/۲۶ وارد کنید (نمی‌تواند در آینده باشد).')
    if post.get('confirm') != 'on':
        raise Invalid('تیک «بازدید بنیاد انجام شد و مدارک را بررسی کردم» لازم است.')
    data = dict(permit.bonyad_list or {})
    owner = permit.people.first()
    text = f'ملک آیدی: بازدید بنیاد مسکن از ملک شما انجام شد. مدارک پرونده {permit.pk} را از سامانه ببینید، نامه‌ی دهیاری را چاپ کنید و نامه‌ی بنیاد را بارگذاری کنید.'
    sent, detail = sms.send_sms(owner.phone, text)
    data['visit'] = {'date': date, 'by': actor.get_full_name() or actor.username, 'at': _now(), 'sms': bool(sent), 'sms_detail': detail}
    permit.bonyad_list, permit.bonyad_list_state = data, 'released'
    permit.save(update_fields=['bonyad_list', 'bonyad_list_state', 'updated_at'])
    sr = permit.request
    sr.add_workflow_step(action=f'تایید انجام بازدید بنیاد در {date} و نمایش مدارک به متقاضی (مرحله ۸)', from_user=actor, to_role='citizen')
    sr.save(update_fields=['workflow_history', 'updated_at'])
    notify(sr.user, 'بازدید بنیاد انجام شد', f'بازدید بنیاد از ملک پرونده {permit.pk} انجام شد؛ مدارک را ببینید و نامه‌ی بنیاد را بارگذاری کنید.', request=sr)
    return permit


@transaction.atomic
def upload_letter(user, permit, post, files):
    if permit.request.user_id != user.id:
        raise NotFound('پرونده پیدا نشد.')
    if not at_step(permit) or permit.bonyad_list_state not in ('released', 'returned'):
        raise Conflict('هنوز نوبت بارگذاری نامه‌ی بنیاد نیست.')
    found, error = permit_form._uploads(files, 'letter', permit_form.ID_EXTENSIONS)         # pylint: disable=protected-access
    if error:
        raise Invalid(error)
    if not found and not documents(permit, LETTER_KIND):
        raise Invalid('تصویر نامه‌ی بنیاد را بارگذاری کنید.')
    if len(found) > MAX_FILES:
        raise Invalid(f'حداکثر {MAX_FILES} فایل می‌توانید بفرستید.')
    number = _clean(post.get('letter_no'), 40)
    date = permit_form._jalali(post.get('letter_date', ''))              # pylint: disable=protected-access
    if not number:
        raise Invalid('شماره‌ی نامه‌ی بنیاد را وارد کنید.')
    if not date or date > permit_step2.today():
        raise Invalid('تاریخ نامه را به شکل ۱۴۰۵/۰۷/۲۶ وارد کنید (نمی‌تواند در آینده باشد).')
    if found:
        for old in documents(permit, LETTER_KIND):
            old.document.delete(save=False)
            old.delete()
        for upload in found:
            PermitDocument.objects.create(file=permit, kind=LETTER_KIND, document=upload, original_name=upload.name[:200], size=upload.size, uploaded_by=user)
    data = dict(permit.bonyad_list or {})
    data['letter'] = {'number': number, 'date': date, 'note': _clean(post.get('note'), 300), 'at': _now()}
    was_returned = permit.bonyad_list_state == 'returned'
    permit.bonyad_list, permit.bonyad_list_state = data, 'uploaded'
    permit.save(update_fields=['bonyad_list', 'bonyad_list_state', 'updated_at'])
    sr = permit.request
    if was_returned:
        permit_request.resubmitted(sr, user)
    else:
        sr.add_workflow_step(action='ارسال نامه‌ی بنیاد مسکن توسط متقاضی (مرحله ۸)', from_user=user, to_role='engineer')
        sr.save(update_fields=['workflow_history', 'updated_at'])
    for staff in permits._staff_to_tell(permit_step2._village(permit)):          # pylint: disable=protected-access
        notify(staff, 'نامه‌ی بنیاد رسید', f'متقاضی پرونده {permit.pk} نامه‌ی بنیاد را فرستاد؛ منتظر تایید است.', request=sr)
    return permit


@transaction.atomic
def verify(actor, permit, post):
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی تایید را ندارید.')
    if not at_step(permit) or permit.bonyad_list_state != 'uploaded':
        raise Conflict('نامه‌ای برای تایید نیست.')
    if post.get('confirm') != 'on':
        raise Invalid('تیک «نامه‌ی بنیاد را با اصل مقایسه و بررسی کردم» لازم است.')
    data = dict(permit.bonyad_list or {})
    data['checked'] = {'by': actor.get_full_name() or actor.username, 'at': _now()}
    permit.bonyad_list, permit.bonyad_list_state = data, 'verified'
    permit.save(update_fields=['bonyad_list', 'bonyad_list_state', 'updated_at'])
    notify(permit.request.user, 'نامه‌ی بنیاد تایید شد', f'نامه‌ی بنیاد پرونده {permit.pk} تایید شد.', request=permit.request)
    return permit


@transaction.atomic
def send_back(actor, permit, notes):
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی این کار را ندارید.')
    if not at_step(permit) or permit.bonyad_list_state != 'uploaded':
        raise Conflict('نامه‌ای برای برگرداندن نیست.')
    notes = (notes or '').strip()
    if not notes:
        raise Invalid('بنویسید مشکل نامه چیست.')
    permit_request.ask_for_documents(permit, actor, f'نامه‌ی بنیاد: {notes}')
    permit.bonyad_list_state, permit.staff_notes = 'returned', notes[:2000]
    permit.save(update_fields=['bonyad_list_state', 'staff_notes', 'updated_at'])
    return permit


def blocking(permit):
    return [] if permit.bonyad_list_state == 'verified' else ['نامه‌ی بنیاد هنوز تایید نشده است.']


@transaction.atomic
def finish(actor, permit, post):
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی تایید این مرحله را ندارید.')
    if not at_step(permit):
        raise Conflict('پرونده در مرحله‌ی لیست بازدید بنیاد نیست.')
    waiting = blocking(permit)
    if waiting:
        raise Conflict(waiting[0])
    if post.get('confirm') != 'on':
        raise Invalid('تیک «مدارک این مرحله را بررسی کردم» لازم است.')
    permit.stage_no = 9
    permit.staff_notes = (post.get('notes') or '')[:2000]
    permit.save()
    sr = permit.request
    sr.add_workflow_step(action='تایید مرحله ۸ (لیست بازدید و نامه‌ی بنیاد)', from_user=actor, to_role='citizen', notes=permit.staff_notes)
    sr.save(update_fields=['workflow_history', 'updated_at'])
    notify(sr.user, 'مرحله‌ی ۸ تایید شد', f'نامه‌ی بنیاد پرونده {permit.pk} تایید و مرحله‌ی ۸ تمام شد؛ پرونده به مرحله‌ی ۹ رفت.', request=sr)
    return permit
