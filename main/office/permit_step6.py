"""Building permit, step 6 (the last part): the Social Security certificate.

With the dehyari's introduction letter the owner pays the insurance share at the Social Security Organisation and gets a
certificate («پرداخت حق بیمه کارگاههای ساختمانی») with a hologram. The owner uploads its scan and types the figures from it and
brings the original to the dehyari; the clerk / expert / dehyari compare the figures with what the file holds, look at the
hologram on the original and confirm. A confirmed certificate moves the file to step 7 (the building permit).
"""
import re

from django.db import transaction
from django.utils import timezone

from main.accounting.parse import digits, parse_amount
from main.models import PermitDocument, PermitFile
from main.notifications import notify
from main.office import permit_form, permit_step2, permit_step3, permits
from main.office.errors import Conflict, Forbidden, Invalid
from main.office.permits import may_open

EXTENSIONS = ('.pdf', '.jpg', '.jpeg', '.png')
MAX_FILES = 6
AREA_TOLERANCE_PCT = 3
OPEN_STATES = ('introduced', 'returned')


def _text(value, limit=80):
    return ' '.join(str(value or '').split())[:limit]


def clean(post):
    """``(data, errors)`` from the certificate form (the owner's and the staff's share it)."""
    data, errors = {}, {}
    for key, label in (('number', 'شماره‌ی گواهی'), ('workshop_no', 'شماره‌ی کارگاه'), ('slip_no', 'شماره‌ی برگ پرداخت')):
        data[key] = re.sub(r'\D', '', digits(post.get(key, '')))[:30]
        if not data[key] and key != 'workshop_no':
            errors[key] = f'«{label}» را وارد کنید.'
    for key, label in (('date', 'تاریخ گواهی'), ('slip_date', 'تاریخ پرداخت')):
        data[key] = permit_form._jalali(post.get(key, '')) or ''           # pylint: disable=protected-access
        if not data[key]:
            errors[key] = f'«{label}» را شمسی و درست وارد کنید، مثل ۱۴۰۴/۰۴/۰۴.'
    for key, label in (('fees_base', 'مبلغ عوارض ذکرشده'), ('premium', 'مبلغ حق بیمه')):
        try:
            data[key] = parse_amount(post.get(key, ''))
        except Invalid:
            data[key] = 0
        if not data[key]:
            errors[key] = f'«{label}» را به ریال و فقط با رقم وارد کنید.'
    raw = str(post.get('area', '')).strip()
    data['area'] = ''
    if raw:
        try:
            data['area'] = round(permit_step3._number(raw), 2)       # pylint: disable=protected-access
        except ValueError:
            errors['area'] = 'متراژ را به‌صورت عدد وارد کنید.'
    data['owner'] = _text(post.get('owner'))
    return data, errors


def checks(permit):
    """What the system compared by itself: each is ok / warn / info with a sentence."""
    cert = (permit.insurance or {}).get('cert') or {}
    letter = (permit.insurance or {}).get('letter') or {}
    out = []

    def add(status, text):
        out.append({'status': status, 'text': text})
    if letter.get('base') and cert.get('fees_base'):
        same = letter['base'] == cert['fees_base']
        add('ok' if same else 'warn', f'مبلغ عوارض گواهی ({cert["fees_base"]:,}) ' + ('با مبلغ نامه‌ی معرفی یکی است.' if same else f'با مبلغ نامه‌ی معرفی ({letter["base"]:,}) یکی نیست.'))
    area, declared = cert.get('area'), letter.get('area')
    try:
        area, declared = float(area), float(declared)
    except (TypeError, ValueError):
        area = declared = 0
    if area and declared:
        diff = abs(area - declared) / declared * 100
        add('ok' if diff <= AREA_TOLERANCE_PCT else 'warn', f'متراژ گواهی {area:g} م² و در نامه‌ی معرفی {declared:g} م² است.')
    if letter.get('date') and cert.get('date'):
        after = cert['date'] >= letter['date']
        add('ok' if after else 'warn', 'گواهی پس از نامه‌ی معرفی صادر شده است.' if after else 'تاریخ گواهی پیش از نامه‌ی معرفی است.')
    if cert.get('number'):
        clash = PermitFile.objects.filter(insurance__cert__number=cert['number']).exclude(pk=permit.pk).exists()
        add('warn' if clash else 'ok', 'این شماره‌ی گواهی در پرونده‌ی دیگری هم آمده است!' if clash else 'شماره‌ی گواهی تکراری نیست.')
    owner = cert.get('owner') or ''
    names = [p.full_name for p in permit.people.all()]
    if owner and names:
        add('ok' if any(owner.replace(' ', '') == n.replace(' ', '') for n in names) else 'warn',
            'نام مالک در گواهی با پرونده می‌خواند.' if any(owner.replace(' ', '') == n.replace(' ', '') for n in names) else f'نام مالک در گواهی ({owner}) با پرونده نمی‌خواند.')
    if not permit.documents.filter(kind='insurance_cert').exists():
        add('warn', 'تصویر گواهی بارگذاری نشده است.')
    return out


def defaults(permit):
    """The form's starting values: what the letter said (the certificate repeats them)."""
    letter = (permit.insurance or {}).get('letter') or {}
    owner = permit.people.first()
    return {'fees_base': letter.get('base', ''), 'area': letter.get('area', ''), 'owner': owner.full_name if owner else ''}


def _step(permit):
    if permit.stage_no != 6:
        raise Conflict('پرونده در مرحله‌ی تامین اجتماعی نیست.')


@transaction.atomic
def submit(user, permit, post, uploads):
    """The owner sends the certificate: the scan and the figures."""
    if permit.request.user_id != user.id:
        raise Forbidden('فقط متقاضی گواهی را می‌فرستد.')
    _step(permit)
    if permit.insurance_state not in OPEN_STATES:
        raise Conflict('الان نمی‌توانید گواهی بفرستید.')
    uploads = list(uploads)
    if not uploads:
        raise Invalid('تصویر گواهی (همه‌ی صفحه‌ها) را بارگذاری کنید.')
    if len(uploads) > MAX_FILES:
        raise Invalid(f'حداکثر {MAX_FILES} فایل.')
    for upload in uploads:
        error = permit_form._file_error(upload, EXTENSIONS, 10 * 1024 * 1024)       # pylint: disable=protected-access
        if error:
            raise Invalid(error)
    data, errors = clean(post)
    if errors:
        raise Invalid(' '.join(errors.values()))
    for old in permit.documents.filter(kind='insurance_cert'):
        old.document.delete(save=False)
        old.delete()
    for upload in uploads:
        PermitDocument.objects.create(file=permit, kind='insurance_cert', document=upload, original_name=upload.name[:200], size=upload.size, uploaded_by=user)
    insurance = dict(permit.insurance or {})
    insurance['cert'] = data
    permit.insurance, permit.insurance_state = insurance, 'uploaded'
    permit.save(update_fields=['insurance', 'insurance_state', 'updated_at'])
    sr = permit.request
    sr.add_workflow_step(action='ارسال گواهی تامین اجتماعی توسط متقاضی', from_user=user, to_role='clerk')
    sr.save(update_fields=['workflow_history', 'updated_at'])
    for staff in permits._staff_to_tell(permit_step2._village(permit)):           # pylint: disable=protected-access
        notify(staff, 'گواهی تامین اجتماعی رسید', f'متقاضی پرونده {permit.pk} گواهی تامین اجتماعی را فرستاد؛ صحت آن را بررسی کنید.', request=sr)
    return permit


@transaction.atomic
def verify(actor, permit, post):
    """The staff confirm the certificate (the hologram on the original seen, figures right): the file moves to step 7."""
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی تایید گواهی را ندارید.')
    _step(permit)
    if permit.insurance_state != 'uploaded':
        raise Conflict('گواهی‌ای برای بررسی وجود ندارد.')
    data, errors = clean(post)
    if errors:
        raise Invalid(' '.join(errors.values()))
    if post.get('confirm') != 'on':
        raise Invalid('بررسی اصل گواهی (هولوگرام و مهر) را تیک بزنید.')
    insurance = dict(permit.insurance or {})
    insurance['cert'] = {**data, 'checked_by': actor.get_full_name() or actor.username, 'checked_at': timezone.localtime().strftime('%Y/%m/%d %H:%M'),
                         'notes': _text(post.get('notes'), 500)}
    permit.insurance, permit.insurance_state, permit.stage_no = insurance, 'verified', 7
    permit.save(update_fields=['insurance', 'insurance_state', 'stage_no', 'updated_at'])
    sr = permit.request
    sr.add_workflow_step(action=f'تایید گواهی تامین اجتماعی (حق بیمه {data["premium"]:,} ریال) - پایان مرحله ۶', from_user=actor, to_role='clerk',
                         notes=insurance['cert']['notes'])
    sr.save(update_fields=['workflow_history', 'updated_at'])
    notify(sr.user, 'گواهی تامین اجتماعی تایید شد',
           'گواهی شما تایید شد؛ دهیاری پروانه‌ی ساختمان را آماده می‌کند. پروانه باید دستی توسط دهیار و مهندس ناظر امضا و مهر شود.', request=sr)
    return permit


@transaction.atomic
def send_back(actor, permit, notes):
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی این کار را ندارید.')
    _step(permit)
    if permit.insurance_state != 'uploaded':
        raise Conflict('گواهی‌ای برای برگرداندن وجود ندارد.')
    notes = _text(notes, 2000)
    if not notes:
        raise Invalid('بنویسید مشکل گواهی چیست.')
    permit.insurance_state, permit.staff_notes = 'returned', notes
    permit.save(update_fields=['insurance_state', 'staff_notes', 'updated_at'])
    notify(permit.request.user, 'گواهی تامین اجتماعی برگشت خورد', notes, request=permit.request)
    return permit
