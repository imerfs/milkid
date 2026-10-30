"""Construction without a permit, step 9: the package of forms and the property undertaking.

When step 8 is confirmed the system gathers everything the file holds in one place for the owner: the request form and undertaking, the health undertaking
(typeset from the file, to print and sign), the defence form, the notice, the neighbours' consent, the financial papers and the judiciary expert's record and the
notarial undertaking. The owner reads them, gives the undertaking (a tick) and then uploads the signed property undertaking («تعهدنامه‌ی ملک»). Any of the clerk /
technical expert / dehyari confirms it (or sends it back with a reason) and then the step; the file goes on to step 10.
"""
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from main.office import permit_request
from main import lifecycle
from main.models import PermitDocument
from main.notifications import notify
from main.office import permit_commit, permit_form, permit_step2, permits
from main.office.errors import Conflict, Forbidden, Invalid, NotFound
from main.office.permits import may_open

DEED_KIND = 'property_deed'
MAX_FILES = 6


def _clean(value, limit=150):
    return ' '.join(str(value or '').split())[:limit]


def _now():
    return timezone.localtime().strftime('%Y/%m/%d %H:%M')


def find(user, file_id):
    return permit_commit.find(user, file_id)


def at_step(permit):
    return permit.unlicensed and permit.stage_no == 9 and permit.state == 'done'


def documents(permit, *kinds):
    return list(permit.documents.filter(kind__in=kinds))


def items(permit):
    """The forms and papers of the file, each with its signed scans and the page where it can be seen or printed."""
    pk = permit.pk
    dues = permit.dues or {}
    return [
        {'title': 'فرم درخواست و تعهدنامه', 'docs': documents(permit, 'comm_request', 'comm_undertake'), 'link': reverse('main:permit_commission', args=[pk])},
        {'title': 'تعهد بهداشتی', 'docs': [], 'link': reverse('main:permit_pack_health', args=[pk]), 'print': True,
         'note': 'چاپ، امضای مالک و تحویل به دهیاری'},
        {'title': 'فرم دفاعیه', 'docs': documents(permit, 'defence_form'), 'link': reverse('main:permit_defence', args=[pk])},
        {'title': 'اخطاریه', 'docs': documents(permit, 'warning_notice'), 'link': reverse('main:permit_notice', args=[pk])},
        {'title': 'رضایت همسایگان', 'docs': documents(permit, 'consent_form'), 'link': reverse('main:permit_commit', args=[pk])},
        {'title': 'مدارک مالی', 'docs': documents(permit, 'fee_receipt'), 'link': reverse('main:permit_dues_sheet', args=[pk]) if permit.dues_state == 'issued' else '',
         'note': f'جمع عوارض {permit.dues_total:,} ریال، پرداخت‌شده {permit.dues_paid:,} ریال' if permit.dues_state == 'issued' else 'برگه‌ی عوارض ثبت نشده',
         'count': len([p for p in dues.get('payments') or [] if p.get('ok')])},
        {'title': 'محضر و جوابیه‌ی کارشناس دادگستری', 'docs': documents(permit, 'expert_letter', 'expert_table', 'deed_scan'), 'link': reverse('main:permit_reply', args=[pk])},
    ]


def health_payload(permit):
    owner = permit.people.first()
    request = permit.request
    return {'village': permit_step2._village(permit), 'county': request.county.name if request.county else '',          # pylint: disable=protected-access
            'owner': owner.full_name, 'father': owner.father_name, 'national_id': owner.national_id, 'address': permit.address,
            'code': permit.renewal_code, 'date': permit_step2.today()}


@transaction.atomic
def give_undertaking(user, permit, post):
    if permit.request.user_id != user.id:
        raise NotFound('پرونده پیدا نشد.')
    if not at_step(permit):
        raise Conflict('پرونده در مرحله‌ی بسته‌ی فرم‌ها نیست.')
    if permit.pack_state != '':
        raise Conflict('تعهد قبلاً ثبت شده است.')
    if post.get('confirm') != 'on':
        raise Invalid('تیک تعهد مالک لازم است.')
    permit.pack = {'undertaking': {'note': _clean(post.get('note'), 300), 'at': _now()}}
    permit.pack_state = 'committed'
    permit.save(update_fields=['pack', 'pack_state', 'updated_at'])
    sr = permit.request
    sr.add_workflow_step(action='تعهد مالک برای فرم‌های پرونده (مرحله ۹)', from_user=user, to_role='clerk')
    sr.save(update_fields=['workflow_history', 'updated_at'])
    return permit


@transaction.atomic
def upload_deed(user, permit, post, files):
    if permit.request.user_id != user.id:
        raise NotFound('پرونده پیدا نشد.')
    if not at_step(permit) or permit.pack_state not in ('committed', 'returned'):
        raise Conflict('هنوز نوبت بارگذاری تعهدنامه‌ی ملک نیست؛ ابتدا تعهد مالک را ثبت کنید.')
    found, error = permit_form._uploads(files, 'deed', permit_form.ID_EXTENSIONS)         # pylint: disable=protected-access
    if error:
        raise Invalid(error)
    if not found and not documents(permit, DEED_KIND):
        raise Invalid('تصویر تعهدنامه‌ی ملک را بارگذاری کنید.')
    if len(found) > MAX_FILES:
        raise Invalid(f'حداکثر {MAX_FILES} فایل می‌توانید بفرستید.')
    if found:
        for old in documents(permit, DEED_KIND):
            old.document.delete(save=False)
            old.delete()
        for upload in found:
            PermitDocument.objects.create(file=permit, kind=DEED_KIND, document=upload, original_name=upload.name[:200], size=upload.size, uploaded_by=user)
    data = dict(permit.pack or {})
    data['deed'] = {'note': _clean(post.get('note'), 300), 'at': _now()}
    was_returned = permit.pack_state == 'returned'
    permit.pack, permit.pack_state = data, 'uploaded'
    permit.save(update_fields=['pack', 'pack_state', 'updated_at'])
    sr = permit.request
    if was_returned:
        permit_request.resubmitted(sr, user)
    else:
        sr.add_workflow_step(action='ارسال تعهدنامه‌ی ملک توسط متقاضی (مرحله ۹)', from_user=user, to_role='clerk')
        sr.save(update_fields=['workflow_history', 'updated_at'])
    for staff in permits._staff_to_tell(permit_step2._village(permit)):          # pylint: disable=protected-access
        notify(staff, 'تعهدنامه‌ی ملک رسید', f'متقاضی پرونده {permit.pk} تعهدنامه‌ی ملک را فرستاد؛ منتظر تایید است.', request=sr)
    return permit


@transaction.atomic
def verify(actor, permit, post):
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی تایید را ندارید.')
    if not at_step(permit) or permit.pack_state != 'uploaded':
        raise Conflict('تعهدنامه‌ای برای تایید نیست.')
    if post.get('confirm') != 'on':
        raise Invalid('تیک «تعهدنامه‌ی ملک را با اصل مقایسه و بررسی کردم» لازم است.')
    data = dict(permit.pack or {})
    data['checked'] = {'by': actor.get_full_name() or actor.username, 'at': _now()}
    permit.pack, permit.pack_state = data, 'verified'
    permit.save(update_fields=['pack', 'pack_state', 'updated_at'])
    notify(permit.request.user, 'تعهدنامه‌ی ملک تایید شد', f'تعهدنامه‌ی ملک پرونده {permit.pk} تایید شد.', request=permit.request)
    return permit


@transaction.atomic
def send_back(actor, permit, notes):
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی این کار را ندارید.')
    if not at_step(permit) or permit.pack_state != 'uploaded':
        raise Conflict('تعهدنامه‌ای برای برگرداندن نیست.')
    notes = (notes or '').strip()
    if not notes:
        raise Invalid('بنویسید مشکل تعهدنامه چیست.')
    permit_request.ask_for_documents(permit, actor, f'تعهدنامه‌ی ملک: {notes}')
    permit.pack_state, permit.staff_notes = 'returned', notes[:2000]
    permit.save(update_fields=['pack_state', 'staff_notes', 'updated_at'])
    return permit


def blocking(permit):
    return [] if permit.pack_state == 'verified' else ['تعهدنامه‌ی ملک هنوز تایید نشده است.']


@transaction.atomic
def finish(actor, permit, post):
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی تایید این مرحله را ندارید.')
    if not at_step(permit):
        raise Conflict('پرونده در مرحله‌ی بسته‌ی فرم‌ها نیست.')
    waiting = blocking(permit)
    if waiting:
        raise Conflict(waiting[0])
    if post.get('confirm') != 'on':
        raise Invalid('تیک «فرم‌ها و تعهدنامه‌ی ملک را بررسی کردم» لازم است.')
    permit.stage_no = 10
    permit.staff_notes = (post.get('notes') or '')[:2000]
    permit.save()
    sr = permit.request
    sr.add_workflow_step(action='تایید مرحله ۹ (بسته‌ی فرم‌ها و تعهدنامه‌ی ملک)', from_user=actor, to_role='clerk', notes=permit.staff_notes)
    sr.save(update_fields=['workflow_history', 'updated_at'])
    notify(sr.user, 'مرحله‌ی ۹ تایید شد', f'تعهدنامه‌ی ملک پرونده {permit.pk} تایید شد؛ دهیاری فرم ۱۶ را تنظیم و به امضای بخشدار می‌رساند (مرحله‌ی ۱۰).', request=sr)
    return permit
