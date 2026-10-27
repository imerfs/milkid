"""Building permit supervision: forms 8-13, one after the other, signed by the supervising engineer on paper.

After the permit is issued the owner takes the forms to the supervising engineer one by one: 8 (start of work), 9 (after the
foundation concrete), 10 (columns and beams), 11 (roof and partitions), 12 (the final report) and 13 (the progress report with the
request for the end-of-work certificate). The system fills each from the file; the owner prints it, the engineer inspects, ticks and
signs and stamps it, the owner uploads the scan, and one of the clerk / technical expert / dehyari confirms it, which opens the
next form. The technical supervisor (inspector) of the system is linked to the file, follows the progress and may fill in the
inspection ticks. A violation (تخلف) stops the form and goes to the dehyari for the Article 99 commission; the commission's decision
is recorded and the stage is inspected again. Form 13 closes the supervision and moves the file to the end-of-work request.
"""
from django.db import transaction
from django.utils import timezone

from main.access import role_of
from main.models import PermitDocument, UserProfile
from main.notifications import notify
from main.office import permit_form, permit_step2, permit_step4, permit_step7, permits
from main.office.errors import Conflict, Forbidden, Invalid
from main.office.permits import may_open

NUMBERS = (8, 9, 10, 11, 12, 13)
TITLES = {8: 'اعلام شروع به کار عملیات ساختمانی', 9: 'گزارش مرحله اول (بعد از بتن‌ریزی پی)', 10: 'گزارش مرحله دوم (اجرای اسکلت و عملیات سازه‌ای)',
          11: 'گزارش مرحله سوم (اجرای عملیات سفت‌کاری و نازک‌کاری)', 12: 'گزارش مرحله چهارم (گزارش نهایی کار)', 13: 'گزارش پیشرفت عملیات ساختمانی و درخواست گواهی پایان کار'}
STATE_TEXT = {'open': 'در انتظار بازدید و امضای ناظر', 'uploaded': 'منتظر تایید دهیاری', 'approved': 'تایید شد', 'returned': 'برگشت‌خورده',
              'violation': 'تخلف گزارش شد', 'commission': 'در کمیسیون ماده ۹۹'}
OPEN_STATES = ('open', 'returned')
EXTENSIONS = ('.pdf', '.jpg', '.jpeg', '.png')
# (label, option a, option b) of the inspection items printed on forms 9-12
ITEMS = {
    9: [('کنترل ابعاد پی‌ها و کلاف', 'مطابق نقشه مصوب می‌باشد', 'نمی‌باشد'), ('پی‌کنی تا عمق خاک مناسب و عمق یخبندان', 'انجام شده است', 'انجام نشده است'),
        ('کنترل پوشش میلگردهای داخل پی', 'مطابق نقشه مصوب می‌باشد', 'نمی‌باشد'), ('پوشش میلگردهای داخل پی: چهل برابر قطر میلگرد', 'رعایت شده است', 'رعایت نشده است'),
        ('کنترل میلگردهای انتظار کلاف: در حد لازم', 'رعایت شده است', 'رعایت نشده است'), ('کنترل اجرای صفحه زیر ستون', 'مناسب است', 'مناسب نیست'),
        ('قالب پی به طوری که آب بتن از بین نرود', 'پوشش شده است', 'پوشش نشده است'), ('بتن‌ریزی پی از مصالح و اختلاط مناسب', 'انجام گرفته است', 'انجام نگرفته است')],
    10: [('اجرای ستون‌ها در محورها طبق نقشه مصوب', 'می‌باشد', 'نمی‌باشد'), ('اجرای تیرهای اصلی مطابق نقشه مصوب', 'می‌باشد', 'نمی‌باشد'),
         ('در صورت وجود بادبند مطابق نقشه مصوب', 'اجرا شده است', 'اجرا نشده است'),
         ('در صورت وجود دیوار باربر: ضخامت و طول مطابق نقشه مصوب', 'می‌باشد', 'نمی‌باشد'), ('دیوار باربر طبق استانداردهای اجرایی مناسب', 'اجرا شده است', 'نشده است')],
    11: [('اجرای عملیات سقف با مصالح مرغوب و رعایت استانداردها', 'صورت گرفته', 'صورت نگرفته'), ('اتصالات سقف به سازه مناسب و با پوشش لازم', 'اجرا گردیده است', 'نگردیده است'),
         ('دیوارچینی مطابق نقشه‌های مصوب و رعایت مقررات', 'اجرا شده است', 'اجرا نشده است'), ('مصالح بکار رفته در این مرحله از کیفیت لازم', 'برخوردار بوده است', 'نبوده است'),
         ('مراحل عایق‌کاری بنا', 'به طور مناسب اجرا شده است', 'نشده است')],
    12: [(label, 'بدون ایراد است', 'ایراد دارد') for label in ('کنترل اجرای شیب‌بندی و پوشش بام', 'کنترل عایق‌بندی بام و سرویس‌ها', 'کنترل اجرای پوشش کف',
                                                                  'کنترل اجرای پوشش داخلی دیوارها', 'کنترل نصب بازشوها', 'کنترل اجرای نماسازی')],
}
FIELDS = {
    8: ('village', 'sup_name', 'sup_license', 'sup_license_date', 'permit_no', 'permit_date', 'pledge_no', 'owner', 'dahestan', 'section', 'shahrestan', 'start_date'),
    9: ('permit_no', 'permit_date', 'owner', 'sup_name', 'sup_license', 'pledge_no', 'use', 'floors', 'structure', 'area'),
    13: ('village', 'sup_name', 'father', 'id_no', 'issued_at', 'sup_license', 'license_date', 'pledge_no', 'end_date', 's1_no', 's1_date', 's2_no', 's2_date',
         's3_no', 's3_date', 's4_no', 's4_date', 'vote_no', 'req_permit_no', 'req_permit_date', 'req_owner'),
}
FIELDS[10] = FIELDS[11] = FIELDS[12] = FIELDS[9]
LABELS = {
    'village': 'روستا', 'sup_name': 'نام و نام خانوادگی مهندس ناظر', 'sup_license': 'شماره‌ی پروانه‌ی اشتغال', 'sup_license_date': 'تاریخ پروانه‌ی اشتغال',
    'permit_no': 'شماره‌ی پروانه‌ی ساختمانی', 'permit_date': 'تاریخ صدور پروانه', 'pledge_no': 'شماره‌ی برگه‌ی تعهد نظارت', 'owner': 'نام متقاضی (مالک)',
    'dahestan': 'دهستان', 'section': 'بخش', 'shahrestan': 'شهرستان', 'start_date': 'تاریخ شروع عملیات', 'use': 'نوع کاربری', 'floors': 'تعداد طبقات',
    'structure': 'نوع سازه', 'area': 'زیربنای مفید', 'father': 'فرزند', 'id_no': 'شماره‌ی شناسنامه', 'issued_at': 'صادره از', 'license_date': 'تاریخ پروانه‌ی اشتغال',
    'end_date': 'تاریخ اتمام عملیات', 's1_no': 'مرحله‌ی اول: شماره', 's1_date': 'مرحله‌ی اول: تاریخ', 's2_no': 'مرحله‌ی دوم: شماره', 's2_date': 'مرحله‌ی دوم: تاریخ',
    's3_no': 'مرحله‌ی سوم: شماره', 's3_date': 'مرحله‌ی سوم: تاریخ', 's4_no': 'مرحله‌ی چهارم: شماره', 's4_date': 'مرحله‌ی چهارم: تاریخ',
    'vote_no': 'رای کمیسیون ماده ۹۹: شماره', 'req_permit_no': 'پایان کار برای پروانه‌ی شماره', 'req_permit_date': 'مورخ', 'req_owner': 'به مالکیت آقای/خانم',
    'number': 'شماره‌ی ثبت در دهیاری', 'date': 'تاریخ'}


def _clean(value, limit=120):
    return ' '.join(str(value or '').split())[:limit]


def _choice_label(key, value):
    return dict(permit_step7.CHOICES[key]).get(value, '')


def _blank():
    return {'state': 'open', 'f': {}, 'c': {}, 'result': '', 'notes': '', 'docs': []}


def forms(permit):
    saved = (permit.supervision or {}).get('forms') or {}
    return {n: {**_blank(), **(saved.get(str(n)) or {})} for n in NUMBERS}


def current(permit):
    """The form waiting its turn (the first not yet confirmed), or None when all six are confirmed."""
    data = forms(permit)
    return next((n for n in NUMBERS if data[n]['state'] != 'approved'), None)


def status(permit):
    """One line for the lists once the permit is issued: where the supervision stands."""
    if permit.stage_no >= 9 or permit.licence_state != 'issued':
        return ''
    n = current(permit)
    if n is None:
        return ''
    state = forms(permit)[n]['state']
    if n == 8 and state == 'open' and not (permit.supervision or {}).get('forms'):
        return ''
    return f'نظارت، فرم {n}: {STATE_TEXT.get(state, "")}'


def defaults(permit, n):
    """The fields of form ``n`` that the file already knows."""
    lic = permit_step7.payload(permit) if permit.licence_state == 'issued' else {}
    village = permit_step2._village(permit)               # pylint: disable=protected-access
    design = permit_step4.payload(permit)
    people = design['people']['supervisor']
    owner = permit.people.first()
    done = forms(permit)
    sheet = {'number': permit_step2._next_number(village), 'date': permit_step2.today(),      # pylint: disable=protected-access
             'village': village, 'sup_name': people.get('name') or lic.get('sup_name', ''), 'sup_license': people.get('license') or lic.get('sup_license', ''),
             'permit_no': lic.get('permit_no', ''), 'permit_date': lic.get('issue_date', ''), 'owner': owner.full_name if owner else '',
             'pledge_no': design['forms']['f07']['number'], 'father': people.get('father', ''),
             'section': lic.get('section', ''), 'start_date': permit_step2.today(), 'use': _choice_label('usage', lic.get('usage', '')) or lic.get('kind', ''),
             'floors': (permit.bonyad or {}).get('floors', ''), 'structure': _choice_label('structure', lic.get('structure', '')),
             'area': lic.get('built_allowed', ''), 'req_permit_no': lic.get('permit_no', ''), 'req_permit_date': lic.get('issue_date', ''),
             'req_owner': owner.full_name if owner else '', 'end_date': permit_step2.today()}
    for stage, form_no in enumerate((9, 10, 11, 12), start=1):
        sheet[f's{stage}_no'], sheet[f's{stage}_date'] = done[form_no]['f'].get('number', ''), done[form_no]['f'].get('date', '')
    commission = (permit.supervision or {}).get('commission') or []
    sheet['vote_no'] = commission[-1].get('vote_no', '') if commission else ''
    return {key: sheet.get(key, '') for key in ('number', 'date') + FIELDS[n]}


def payload(permit):
    """Every form with defaults under what was saved, for the page and the drawing."""
    out = {}
    for n, data in forms(permit).items():
        out[n] = {**data, 'f': {**defaults(permit, n), **{k: v for k, v in data['f'].items() if v != ''}}, 'title': TITLES[n]}
    return out


def _is_current(permit, n):
    if permit.stage_no != 7 or permit.licence_state != 'issued':
        raise Conflict('نظارت پس از صدور پروانه آغاز می‌شود.')
    if n not in NUMBERS or current(permit) != n:
        raise Conflict('نوبت این فرم نیست.')


def may_fill(user, permit):
    return may_open(user, permit) or (role_of(user) == 'inspector' and permit.supervisor_id == user.id)


def _staff(permit):
    return list(permits._staff_to_tell(permit_step2._village(permit)))       # pylint: disable=protected-access


def _supervisor_and_staff(permit, skip=None):
    users = _staff(permit) + ([permit.supervisor] if permit.supervisor_id else [])
    return [u for u in users if u.pk != getattr(skip, 'pk', None)]


def _save(permit, n, data):
    supervision = dict(permit.supervision or {})
    all_forms = dict(supervision.get('forms') or {})
    all_forms[str(n)] = data
    supervision['forms'] = all_forms
    permit.supervision = supervision
    permit.save(update_fields=['supervision', 'updated_at'])


def _step(permit, text):
    sr = permit.request
    sr.add_workflow_step(action=text, from_user=None, to_role='clerk')
    sr.save(update_fields=['workflow_history', 'updated_at'])


@transaction.atomic
def fill(actor, permit, n, post):
    """The figures of the form and, on forms 9-12, the inspection result: the staff or the technical supervisor of the file."""
    if not may_fill(actor, permit):
        raise Forbidden('فرم را کارکنان دهیاری یا ناظر فنی پرونده پر می‌کنند.')
    _is_current(permit, n)
    data = forms(permit)[n]
    if data['state'] not in OPEN_STATES:
        raise Conflict('این فرم در انتظار بررسی یا کمیسیون است و نمی‌توان آن را تغییر داد.')
    fields = {key: _clean(post.get(f'f_{key}')) for key in ('number', 'date') + FIELDS[n]}
    data['f'] = fields
    data['notes'] = _clean(post.get('notes'), 500)
    if n in ITEMS:
        checks = {str(i): post.get(f'c_{i}') for i in range(1, len(ITEMS[n]) + 1) if post.get(f'c_{i}') in ('a', 'b')}
        result = post.get('result', '')
        if result not in ('ok', 'violation', ''):
            raise Invalid('نتیجه‌ی بازدید نامعتبر است.')
        if result == 'ok' and len(checks) != len(ITEMS[n]):
            raise Invalid('برای «عدم وقوع تخلف» همه‌ی موارد بازدید را علامت بزنید.')
        if result == 'violation' and not data['notes']:
            raise Invalid('برای گزارش تخلف، توضیحات را بنویسید.')
        data['c'], data['result'] = checks, result
    if n in ITEMS and data['result'] == 'violation':
        data['state'] = 'violation'
        _save(permit, n, data)
        _step(permit, f'گزارش تخلف در فرم {n} نظارت')
        for user in _supervisor_and_staff(permit, actor) + [permit.request.user]:
            notify(user, 'گزارش تخلف در ساخت', f'در بازدید مرحله‌ی فرم {n} پرونده {permit.pk} تخلف گزارش شد؛ دهیار پرونده را به کمیسیون ماده ۹۹ ارجاع می‌دهد.', request=permit.request)
    else:
        _save(permit, n, data)
    return permit


@transaction.atomic
def upload(user, permit, n, uploads):
    """The owner uploads the printed form signed and stamped by the supervising engineer."""
    if permit.request.user_id != user.id:
        raise Forbidden('فقط متقاضی فرم امضاشده را بارگذاری می‌کند.')
    _is_current(permit, n)
    data = forms(permit)[n]
    if data['state'] not in OPEN_STATES:
        raise Conflict('الان نمی‌توانید این فرم را بفرستید.')
    if n in ITEMS and data['result'] != 'ok':
        raise Conflict('هنوز نتیجه‌ی بازدید (بدون تخلف) برای این فرم ثبت نشده است؛ از ناظر یا دهیاری بخواهید ثبت کنند.')
    uploads = list(uploads)
    if not uploads or len(uploads) > 6:
        raise Invalid('تصویر فرم امضاشده (حداکثر ۶ فایل) را بارگذاری کنید.')
    for item in uploads:
        error = permit_form._file_error(item, EXTENSIONS, 10 * 1024 * 1024)            # pylint: disable=protected-access
        if error:
            raise Invalid(error)
    for old in permit.documents.filter(pk__in=data['docs'], kind='supervision_form'):
        old.document.delete(save=False)
        old.delete()
    data['docs'] = [PermitDocument.objects.create(file=permit, kind='supervision_form', document=item, original_name=item.name[:200], size=item.size,
                                                  uploaded_by=user).pk for item in uploads]
    if not data['f'].get('number'):                 # the sheet that was printed: keep its numbers as they were
        data['f'] = defaults(permit, n)
    data['state'] = 'uploaded'
    _save(permit, n, data)
    _step(permit, f'ارسال فرم {n} نظارت با امضای ناظر')
    for staff in _staff(permit):
        notify(staff, 'فرم نظارت رسید', f'متقاضی پرونده {permit.pk} فرم {n} را با امضای ناظر فرستاد؛ بررسی و تایید کنید.', request=permit.request)
    return permit


@transaction.atomic
def approve(actor, permit, n):
    if not may_open(actor, permit):
        raise Forbidden('تایید فرم با کارکنان دهیاری است.')
    _is_current(permit, n)
    data = forms(permit)[n]
    if data['state'] != 'uploaded':
        raise Conflict('فرمی برای تایید وجود ندارد.')
    data['state'], data['approved_by'] = 'approved', actor.get_full_name() or actor.username
    data['approved_at'] = timezone.localtime().strftime('%Y/%m/%d %H:%M')
    _save(permit, n, data)
    _step(permit, f'تایید فرم {n} نظارت: {TITLES[n]}')
    last = n == NUMBERS[-1]
    if last:
        permit.stage_no = 9
        permit.save(update_fields=['stage_no', 'updated_at'])
    text = 'همه‌ی فرم‌های نظارت تایید شد؛ درخواست گواهی پایان کار ثبت شد.' if last else f'فرم {n} تایید شد؛ نوبت فرم {n + 1} است.'
    for user in [permit.request.user] + ([permit.supervisor] if permit.supervisor_id else []):
        notify(user, 'فرم نظارت تایید شد', text, request=permit.request)
    return permit


@transaction.atomic
def send_back(actor, permit, n, notes):
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی این کار را ندارید.')
    _is_current(permit, n)
    data = forms(permit)[n]
    notes = _clean(notes, 1000)
    if data['state'] != 'uploaded':
        raise Conflict('فرمی برای برگرداندن وجود ندارد.')
    if not notes:
        raise Invalid('بنویسید مشکل چیست.')
    data['state'], data['return_notes'] = 'returned', notes
    _save(permit, n, data)
    notify(permit.request.user, 'فرم نظارت برگشت خورد', f'فرم {n}: {notes}', request=permit.request)
    return permit


@transaction.atomic
def refer(actor, permit, n, post):
    """The dehyari sends the reported violation to the Article 99 commission."""
    if not may_open(actor, permit):
        raise Forbidden('ارجاع به کمیسیون با کارکنان دهیاری است.')
    _is_current(permit, n)
    data = forms(permit)[n]
    if data['state'] != 'violation':
        raise Conflict('تخلفی برای ارجاع وجود ندارد.')
    data['state'] = 'commission'
    data['case'] = {'ref': _clean(post.get('case_ref'), 60), 'date': _clean(post.get('case_date'), 12) or permit_step2.today(),
                    'by': actor.get_full_name() or actor.username}
    _save(permit, n, data)
    _step(permit, f'ارجاع تخلف فرم {n} به کمیسیون ماده ۹۹')
    notify(permit.request.user, 'ارجاع به کمیسیون ماده ۹۹', f'تخلف گزارش‌شده در فرم {n} پرونده شما به کمیسیون ماده ۹۹ ارجاع شد.', request=permit.request)
    return permit


@transaction.atomic
def decide(actor, permit, n, post):
    """The commission's decision is recorded; the stage is inspected again."""
    if not may_open(actor, permit):
        raise Forbidden('ثبت رای کمیسیون با کارکنان دهیاری است.')
    _is_current(permit, n)
    data = forms(permit)[n]
    if data['state'] != 'commission':
        raise Conflict('پرونده در کمیسیون نیست.')
    vote, text = _clean(post.get('vote_no'), 40), _clean(post.get('decision'), 500)
    if not vote or not text:
        raise Invalid('شماره‌ی رای و متن تصمیم کمیسیون را وارد کنید.')
    supervision = dict(permit.supervision or {})
    log = list(supervision.get('commission') or [])
    log.append({'form': n, 'vote_no': vote, 'vote_date': _clean(post.get('vote_date'), 12) or permit_step2.today(), 'decision': text,
                'violation': data.get('notes', ''), 'case': data.get('case') or {}, 'by': actor.get_full_name() or actor.username})
    supervision['commission'] = log
    permit.supervision = supervision
    data.update({'state': 'open', 'result': '', 'c': {}, 'notes': ''})
    data.pop('case', None)
    _save(permit, n, data)
    _step(permit, f'ثبت رای کمیسیون ماده ۹۹ (شماره {vote}) برای فرم {n}')
    for user in [permit.request.user] + ([permit.supervisor] if permit.supervisor_id else []):
        notify(user, 'رای کمیسیون ماده ۹۹', f'رای کمیسیون برای پرونده {permit.pk} ثبت شد؛ پس از رفع تخلف، بازدید دوباره انجام می‌شود.', request=permit.request)
    return permit


@transaction.atomic
def assign(actor, permit, user_id):
    """Link the village's technical supervisor (inspector) to the file; blank unlinks."""
    if not may_open(actor, permit):
        raise Forbidden('تعیین ناظر فنی با کارکنان دهیاری است.')
    if not user_id:
        permit.supervisor = None
    else:
        profile = UserProfile.objects.filter(user_id=user_id, role='inspector', is_active=True,
                                             city_village=permit_step2._village(permit)).select_related('user').first()      # pylint: disable=protected-access
        if profile is None:
            raise Invalid('ناظر فنی این روستا پیدا نشد.')
        permit.supervisor = profile.user
        notify(profile.user, 'پرونده‌ی ساخت به شما سپرده شد', f'نظارت بر پرونده {permit.pk} به شما سپرده شد؛ پیشرفت کار را در پنل ببینید.', request=permit.request)
    permit.save(update_fields=['supervisor', 'updated_at'])
    return permit


def supervisors_for(permit):
    return UserProfile.objects.filter(role='inspector', is_active=True, city_village=permit_step2._village(permit)).select_related('user')   # pylint: disable=protected-access


def thread(permit):
    return list((permit.supervision or {}).get('messages') or [])


@transaction.atomic
def post_message(user, permit, text):
    """A short message between the owner, the village staff and the file's technical supervisor."""
    mine = permit.request.user_id == user.id
    if not (mine or may_open(user, permit) or (permit.supervisor_id == user.id)):
        raise Forbidden('اجازه‌ی ارسال پیام ندارید.')
    text = _clean(text, 600)
    if not text:
        raise Invalid('متن پیام را بنویسید.')
    who = 'متقاضی' if mine else 'ناظر فنی' if permit.supervisor_id == user.id else 'دهیاری'
    supervision = dict(permit.supervision or {})
    supervision['messages'] = thread(permit) + [{'by': user.get_full_name() or user.username, 'who': who, 'text': text,
                                                  'at': timezone.localtime().strftime('%Y/%m/%d %H:%M')}]
    permit.supervision = supervision
    permit.save(update_fields=['supervision', 'updated_at'])
    for target in [permit.request.user] + _supervisor_and_staff(permit):
        if target.pk != user.pk:
            notify(target, 'پیام تازه در پرونده', f'{who}: {text[:120]}', request=permit.request)
    return permit


def inspector_rows(user):
    """The files a technical supervisor follows, newest first."""
    from main.models import PermitFile       # pylint: disable=import-outside-toplevel
    rows = PermitFile.objects.filter(supervisor=user).select_related('request', 'request__user').order_by('-updated_at')
    return [{'file': f, 'status': f.status_text, 'form': current(f), 'waiting': any(v.get('state') in ('violation',) for v in forms(f).values())} for f in rows[:50]]

