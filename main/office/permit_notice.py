"""Construction without a permit, step 3: the warning notice (اخطاریه به مالک, form 14) and the technical expert's visit.

The dehyari warns the owner of a building put up without a permit (form 14: the building without a permit, its breaches, inside or outside the
village master plan, handed to the owner or his relatives, or posted on the building). The owner uploads the scan of that notice and types its
figures (number, date, plan position, how it was delivered, the name on it). Any of the clerk / technical expert / dehyari (``permit.open``)
compares them with the paper (and with the file: the owner's name, a number already used in another file) and confirms, or sends it back with a
reason; confirming moves the file to step 4.
"""
from django.db import transaction
from django.utils import timezone

from main.office import permit_request, step_flow
from main import lifecycle
from main.models import PermitDocument, PermitFile
from main.notifications import notify
from main.office import permit_form, permit_step2, permits
from main.office.errors import Conflict, Forbidden, Invalid, NotFound
from main.office.permits import may_open

POSITIONS = {'inside': 'داخل طرح هادی', 'outside': 'خارج از طرح هادی'}
DELIVERIES = {'handed': 'تحویل مالک / بستگان گردید', 'posted': 'در محل الصاق شد'}
OPEN_STATES = ('', 'returned')
UPLOAD_STATES = ('', 'requested', 'issued', 'returned')        # the owner may upload the signed notice
ISSUE_STATES = ('', 'requested', 'issued')                        # the staff may fill and print a notice for the owner
TICKS = (('rules', 'رعایت ضوابط'), ('permit', 'پروانه ساختمانی'), ('plans', 'رعایت نقشه‌های مصوب'), ('technical', 'رعایت اصول فنی'),
         ('extra', 'رعایت عدم اضافه بنا'))
SLOTS = {'morning': 'صبح (۸ تا ۱۲)', 'afternoon': 'بعدازظهر (۱۴ تا ۱۷)'}
MAX_SCANS = 6
KIND = 'warning_notice'


_clean = step_flow.clean


def at_step(permit):
    return permit.unlicensed and permit.stage_no == 3 and permit.state == 'done'


def find(user, file_id):
    permit = permits.find(user, file_id, any_track=True)
    return permit if permit is not None and permit.unlicensed else None


def defaults(permit):
    return {'number': '', 'date': '', 'position': '', 'delivery': '', 'addressee': permit.people.first().full_name}


def data(permit):
    base = defaults(permit)
    notice = permit.notice or {}
    return {**base, **{k: v for k, v in (notice.get('form') or {}).items() if k in base and v}, **{k: v for k, v in notice.items() if k in base}}


def form_defaults(permit):
    """What the system can fill on the notice from the file, to save the staff's typing (they change anything)."""
    owner = permit.people.first()
    village = permit_step2._village(permit)                # pylint: disable=protected-access
    defence = permit.defence or {}
    return {'number': '', 'date': permit_step2.today(), 'addressee': owner.full_name,
            'address': f'روستای {village}' + (f'، {permit.address}' if permit.address else ''),
            'ticks': {'rules': True, 'permit': True, 'plans': True, 'technical': False, 'extra': defence.get('status') == 'over'},
            'position': 'inside' if permit.parcel_id else '', 'delivery': ''}


def form_data(permit):
    saved = (permit.notice or {}).get('form') or {}
    base = form_defaults(permit)
    return {**base, **{k: v for k, v in saved.items() if k in base}, 'ticks': {**base['ticks'], **(saved.get('ticks') or {})}}


def payload(permit):
    return {'form': form_data(permit), 'village': permit_step2._village(permit), 'file': permit.pk,           # pylint: disable=protected-access
            'ticks': [{'key': k, 'label': label} for k, label in TICKS]}


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
    return step_flow.staff_of(permit)


@transaction.atomic
def upload(user, permit, post, files):
    """The owner uploads the notice's scan and types its figures (the staff may upload the signed paper of a notice they issued)."""
    mine = permit.request.user_id == user.id
    if not mine and not (may_open(user, permit) and permit.notice_state == 'issued'):
        raise NotFound('پرونده پیدا نشد.')
    if not at_step(permit):
        raise Conflict('پرونده در مرحله‌ی اخطاریه نیست.')
    if permit.notice_state not in UPLOAD_STATES:
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
    permit.notice, permit.notice_state, permit.notice_at = {**(permit.notice or {}), **values}, 'uploaded', timezone.now()
    permit.save(update_fields=['notice', 'notice_state', 'notice_at', 'updated_at'])
    sr = permit.request
    if was_returned:
        permit_request.resubmitted(sr, user)
    else:
        sr.add_workflow_step(action='ارسال اخطاریه‌ی امضاشده (مرحله ۳)', from_user=user, to_role='engineer')
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
    permit.notice, permit.notice_state = {**(permit.notice or {}), **values}, 'verified'
    permit.staff_notes = (post.get('notes') or '')[:2000]
    permit.save()
    sr = permit.request
    sr.add_workflow_step(action=f'تایید اخطاریه‌ی مالک (شماره {values["number"]}) - درخواست بازدید کارشناس فنی نوبت است', from_user=actor, to_role='engineer', notes=permit.staff_notes)
    sr.save(update_fields=['workflow_history', 'updated_at'])
    notify(sr.user, 'اخطاریه‌ی شما تایید شد', f'دهیاری اخطاریه‌ی پرونده {permit.pk} (شماره {values["number"]}) را تایید کرد؛ حالا درخواست بازدید کارشناس فنی را بدهید.', request=sr)
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
    permit_request.ask_for_documents(permit, actor, f'اخطاریه‌ی مالک: {notes}')
    permit.notice_state, permit.staff_notes = 'returned', notes[:2000]
    permit.save(update_fields=['notice_state', 'staff_notes', 'updated_at'])
    return permit


# ---------- the owner has no notice: he asks, the staff fill and print one, he signs it in person ----------

@transaction.atomic
def request_issue(user, permit):
    """The owner has no notice: he asks the village for the earlier notice and goes to the dehyari in person."""
    if permit.request.user_id != user.id:
        raise NotFound('پرونده پیدا نشد.')
    if not at_step(permit):
        raise Conflict('پرونده در مرحله‌ی اخطاریه نیست.')
    if permit.notice_state not in ('', 'returned'):
        raise Conflict('درخواست یا اخطاریه‌ای از قبل در جریان است.')
    permit.notice_state, permit.notice_at = 'requested', timezone.now()
    permit.save(update_fields=['notice_state', 'notice_at', 'updated_at'])
    sr = permit.request
    sr.add_workflow_step(action='درخواست دریافت اخطاریه‌ی قبلی توسط متقاضی (مرحله ۳)', from_user=user, to_role='engineer')
    sr.save(update_fields=['workflow_history', 'updated_at'])
    for staff in _staff(permit):
        notify(staff, 'درخواست اخطاریه', f'متقاضی پرونده {permit.pk} اخطاریه ندارد و درخواست اخطاریه داده؛ مراجعه‌ی حضوری می‌کند، اخطاریه را پر و چاپ کنید.', request=sr)
    return permit


def clean_issue(post):
    """The notice form as the staff filled it: returns (values, errors)."""
    errors = {}
    values = {'number': _clean(post.get('number'), 40), 'addressee': _clean(post.get('addressee'), 120), 'address': _clean(post.get('address'), 200),
              'position': post.get('position', ''), 'delivery': post.get('delivery', ''),
              'ticks': {key: post.get('tick_' + key) == 'on' for key, _ in TICKS}}
    date = permit_form._jalali(post.get('date', ''))                  # pylint: disable=protected-access
    if not date:
        errors['date'] = 'تاریخ اخطاریه را به شکل ۱۴۰۵/۰۶/۲۲ وارد کنید.'
    values['date'] = date or ''
    if not values['addressee']:
        errors['addressee'] = 'نام مالک را وارد کنید.'
    if values['position'] and values['position'] not in POSITIONS:
        errors['position'] = 'داخل یا خارج از طرح هادی را درست انتخاب کنید.'
    if values['delivery'] and values['delivery'] not in DELIVERIES:
        errors['delivery'] = 'نحوه‌ی ابلاغ را درست انتخاب کنید.'
    if not any(values['ticks'].values()):
        errors['ticks'] = 'دست‌کم یکی از موارد تخلف را تیک بزنید.'
    return values, errors


@transaction.atomic
def issue(actor, permit, post):
    """Any of the clerk / technical expert / dehyari fills the notice from the file (ticks included); the owner signs it in person."""
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی صدور اخطاریه را ندارید.')
    if not at_step(permit) or permit.notice_state not in ISSUE_STATES:
        raise Conflict('اخطاریه در مرحله‌ی صدور نیست.')
    values, errors = clean_issue(post)
    if errors:
        raise Invalid(next(iter(errors.values())))
    data_ = dict(permit.notice or {})
    data_['form'] = values
    data_['issued'] = {'by': actor.get_full_name() or actor.username, 'at': timezone.now().strftime('%Y-%m-%d %H:%M')}
    permit.notice, permit.notice_state, permit.notice_at = data_, 'issued', timezone.now()
    permit.save(update_fields=['notice', 'notice_state', 'notice_at', 'updated_at'])
    sr = permit.request
    sr.add_workflow_step(action='صدور اخطاریه برای مالک (مرحله ۳)', from_user=actor, to_role='citizen')
    sr.save(update_fields=['workflow_history', 'updated_at'])
    notify(sr.user, 'اخطاریه‌ی شما صادر شد', f'اخطاریه‌ی پرونده {permit.pk} آماده است؛ حضوری به دهیاری مراجعه و آن را امضا کنید و تصویر امضاشده را بارگذاری کنید.', request=sr)
    return permit


# ---------- the technical expert's visit ----------

def _visit_open(permit):
    return at_step(permit) and permit.notice_state == 'verified'


def _future_date(value):
    date = permit_form._jalali(value)                                  # pylint: disable=protected-access
    if not date or date < permit_step2.today():
        raise Invalid('تاریخ را به شکل ۱۴۰۵/۰۶/۲۲ وارد کنید (نمی‌تواند گذشته باشد).')
    return date


@transaction.atomic
def request_visit(user, permit, post):
    """The owner asks the technical expert to visit the building."""
    if permit.request.user_id != user.id:
        raise NotFound('پرونده پیدا نشد.')
    if not _visit_open(permit):
        raise Conflict('درخواست بازدید پس از تایید اخطاریه ممکن است.')
    if permit.visit_state:
        raise Conflict('درخواست بازدید قبلاً ثبت شده است.')
    slot = post.get('slot', '')
    if slot not in SLOTS:
        raise Invalid('بازه‌ی زمانی بازدید را انتخاب کنید.')
    permit.visit = {'preferred_date': _future_date(post.get('date', '')), 'slot': slot, 'note': ' '.join(str(post.get('note', '')).split())[:300],
                    'requested_at': timezone.now().strftime('%Y-%m-%d %H:%M')}
    permit.visit_state, permit.visit_at = 'requested', timezone.now()
    permit.save(update_fields=['visit', 'visit_state', 'visit_at', 'updated_at'])
    sr = permit.request
    sr.add_workflow_step(action='درخواست بازدید کارشناس فنی توسط متقاضی (مرحله ۳)', from_user=user, to_role='engineer')
    sr.save(update_fields=['workflow_history', 'updated_at'])
    for staff in _staff(permit):
        notify(staff, 'درخواست بازدید', f'متقاضی پرونده {permit.pk} بازدید کارشناس فنی را برای {permit.visit["preferred_date"]} ({SLOTS[slot]}) خواسته است.', request=sr)
    return permit


@transaction.atomic
def schedule_visit(actor, permit, post):
    """Any of the clerk / technical expert / dehyari fix the day of the visit (it may differ from what the owner asked)."""
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی زمان‌بندی بازدید را ندارید.')
    if not _visit_open(permit) or permit.visit_state not in ('requested', 'scheduled'):
        raise Conflict('درخواست بازدیدی برای زمان‌بندی نیست.')
    slot = post.get('slot', '')
    if slot not in SLOTS:
        raise Invalid('بازه‌ی زمانی بازدید را انتخاب کنید.')
    data_ = dict(permit.visit or {})
    data_.update({'date': _future_date(post.get('date', '')), 'slot': slot, 'scheduled_by': actor.get_full_name() or actor.username})
    permit.visit, permit.visit_state = data_, 'scheduled'
    permit.save(update_fields=['visit', 'visit_state', 'updated_at'])
    notify(permit.request.user, 'زمان بازدید', f'بازدید کارشناس فنی از ملک پرونده {permit.pk} برای {data_["date"]} ({SLOTS[slot]}) تعیین شد.', request=permit.request)
    return permit


@transaction.atomic
def complete_visit(actor, permit, post):
    """The visit was made: the file goes on to step 4."""
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی ثبت بازدید را ندارید.')
    if not _visit_open(permit) or permit.visit_state not in ('requested', 'scheduled'):
        raise Conflict('بازدیدی برای ثبت نیست.')
    if post.get('confirm') != 'on':
        raise Invalid('تیک «بازدید از ملک انجام شد» لازم است.')
    data_ = dict(permit.visit or {})
    data_['done'] = {'by': actor.get_full_name() or actor.username, 'at': timezone.now().strftime('%Y-%m-%d %H:%M'),
                     'notes': ' '.join(str(post.get('notes', '')).split())[:800]}
    permit.visit, permit.visit_state, permit.stage_no = data_, 'done', 4
    permit.save()
    sr = permit.request
    sr.add_workflow_step(action='انجام بازدید کارشناس فنی - پایان مرحله ۳', from_user=actor, to_role='engineer', notes=data_['done']['notes'])
    sr.save(update_fields=['workflow_history', 'updated_at'])
    notify(sr.user, 'بازدید انجام شد', f'بازدید کارشناس فنی از ملک پرونده {permit.pk} ثبت شد؛ پرونده به مرحله‌ی ۴ رفت.', request=sr)
    return permit

