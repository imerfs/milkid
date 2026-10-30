"""Building permit, services: the letters the dehyari gives the owner to get electricity, gas and water.

With the permit (or the end-of-work certificate) the owner asks the dehyari for the letters the utility companies want: the
property status inquiry (form 2) for electricity and gas, the letter introducing the owner for an electricity / gas meter / water
connection, and the letter allowing the gas company to cut the asphalt once the fee slip is paid. The system fills each letter from
the file; the clerk / technical expert / dehyari check and approve the request (which gives the letter a number and a date), the owner
prints it and the dehyari signs and stamps it by hand; the staff then record that the signed letter was handed over.
"""
from django.db import transaction
from django.utils import timezone

from main.accounting.parse import digits
from main.notifications import notify
from main.office import permit_form, permit_step2, permit_step7, permits, step_flow
from main.office.errors import Conflict, Forbidden, Invalid, NotFound
from main.office.permits import may_open

BASE = ('name', 'father', 'national_id', 'id_number', 'issued_at', 'phone', 'village', 'section', 'address', 'plot', 'postal_code')
STATUS = ('area', 'built', 'n', 's', 'e', 'w', 'street', 'hadi_date', 'basis', 'utm_x', 'utm_y', 'notes')
PERMIT = ('permit_no', 'permit_date')
ENDWORK = ('endwork_no', 'endwork_date')
DIG = ('ref_no', 'ref_date', 'slip_no', 'slip_date')
CLEAR = ('village', 'section', 'name', 'plot', 'address', 'permit_no', 'permit_date', 'req_no', 'req_date', 'report_date', 'sup_name', 'stage_text', 'notes', 'tech_name')
# the non-violation certificates (گواهی عدم خلاف) of the permit booklet: kind -> (supervision form that must be confirmed first, the stage's name)
CLEARANCES = {'nov_1': (9, 'اول (بعد از بتن‌ریزی پی)'), 'nov_2': (10, 'دوم (اجرای اسکلت و عملیات سازه‌ای)'), 'nov_3': (11, 'سوم (اجرای سفت‌کاری و نازک‌کاری)')}
KINDS = {
    'elec_status': {'title': 'برق: استعلام وضعیت ملک (فرم ۲)', 'company': 'مدیر محترم شرکت توزیع نیروی برق شهرستان بیرجند', 'fields': BASE + STATUS, 'pages': 2, 'what': 'برق'},
    'elec_permit': {'title': 'برق: معرفی برای انشعاب (با پروانه)', 'company': 'مدیریت محترم توزیع نیروی برق شهرستان بیرجند', 'fields': BASE + PERMIT, 'pages': 1, 'what': 'برق'},
    'elec_endwork': {'title': 'برق: معرفی برای انشعاب (با پایان‌کار)', 'company': 'مدیریت محترم توزیع نیروی برق شهرستان بیرجند', 'fields': BASE + ENDWORK, 'pages': 1, 'what': 'برق'},
    'gas_status': {'title': 'گاز: استعلام وضعیت ملک (فرم ۲)', 'company': 'مدیر محترم شرکت گاز شهرستان بیرجند', 'fields': BASE + STATUS, 'pages': 2, 'what': 'گاز'},
    'gas_meter': {'title': 'گاز: جانمایی و نصب علمک', 'company': 'رئیس محترم شرکت گاز شهرستان بیرجند', 'fields': BASE, 'pages': 1, 'what': 'گاز'},
    'gas_dig': {'title': 'گاز: اجازه‌ی حفاری (پس از پرداخت آسفالت شکافی)', 'company': 'رئیس محترم شرکت گاز شهرستان بیرجند', 'fields': BASE + DIG, 'pages': 1, 'what': 'گاز'},
    'nov_1': {'title': 'گواهی عدم خلاف: مرحله‌ی اول (بعد از بتن‌ریزی پی)', 'company': '', 'fields': CLEAR, 'pages': 1, 'what': ''},
    'nov_2': {'title': 'گواهی عدم خلاف: مرحله‌ی دوم (اسکلت)', 'company': '', 'fields': CLEAR, 'pages': 1, 'what': ''},
    'nov_3': {'title': 'گواهی عدم خلاف: مرحله‌ی سوم (سفت‌کاری و نازک‌کاری)', 'company': '', 'fields': CLEAR, 'pages': 1, 'what': ''},
    'water_permit': {'title': 'آب: معرفی برای انشعاب (با پروانه)', 'company': 'رئیس محترم اداره آب و فاضلاب روستایی شهرستان بیرجند', 'fields': BASE + PERMIT, 'pages': 1, 'what': 'آب'},
}
LABELS = {
    'name': 'نام و نام خانوادگی', 'father': 'فرزند', 'national_id': 'کد ملی', 'id_number': 'شماره‌ی شناسنامه', 'issued_at': 'صادره از', 'phone': 'تلفن همراه',
    'village': 'روستا', 'section': 'بخش', 'address': 'نشانی (خیابان و کوچه)', 'plot': 'پلاک / قطعه', 'postal_code': 'کد پستی', 'area': 'مساحت عرصه (م²)',
    'built': 'اعیان (م²)', 'n': 'حد شمال (متر)', 's': 'حد جنوب (متر)', 'e': 'حد شرق (متر)', 'w': 'حد غرب (متر)', 'street': 'عرض معبر (متر)',
    'hadi_date': 'تاریخ ابلاغ طرح هادی', 'basis': 'مبنای تایید (پروانه یا رای کمیسیون)', 'utm_x': 'مختصات X', 'utm_y': 'مختصات Y', 'notes': 'توضیحات',
    'permit_no': 'شماره‌ی پروانه', 'permit_date': 'تاریخ پروانه', 'endwork_no': 'شماره‌ی پایان‌کار', 'endwork_date': 'تاریخ پایان‌کار',
    'ref_no': 'شماره‌ی نامه‌ی شرکت', 'ref_date': 'تاریخ نامه‌ی شرکت', 'slip_no': 'شماره‌ی فیش آسفالت شکافی', 'slip_date': 'تاریخ فیش',
    'number': 'شماره‌ی نامه', 'date': 'تاریخ نامه', 'dehyari_name': 'نام دهیار', 'req_no': 'شماره‌ی درخواست', 'req_date': 'تاریخ درخواست',
    'report_date': 'تاریخ گزارش ناظر', 'sup_name': 'ناظر فنی (مهندس ناظر)', 'stage_text': 'مرحله‌ی ساختمان', 'tech_name': 'نام مسئول فنی دهیاری'}
STATE_TEXT = {'requested': 'منتظر تایید دهیاری', 'approved': 'تایید شد؛ چاپ و امضای دهیار', 'issued': 'امضا و تحویل شد', 'rejected': 'رد شد', 'cancelled': 'لغو شد'}
REQUIRED = {'elec_endwork': ('endwork_no', 'endwork_date'), 'gas_dig': ('ref_no', 'slip_no', 'slip_date'), 'elec_permit': ('permit_no',), 'water_permit': ('permit_no',)}


_clean = step_flow.clean


def services(permit):
    return list(permit.services or [])


def find_service(permit, sid):
    item = next((s for s in services(permit) if s.get('id') == sid), None)
    if item is None:
        raise NotFound('درخواست پیدا نشد.')
    return item


def _street(address, village):
    """The address without the leading «روستای <village>،» the permit form puts in front of it."""
    text = str(address or '').strip()
    prefix = f'روستای {village}'
    if text.startswith(prefix):
        text = text[len(prefix):].lstrip('،, ')
    return text


def _report_date(permit, kind):
    """The date of the supervision report the clearance rests on."""
    form = CLEARANCES.get(kind, (0, ''))[0]
    if not form:
        return ''
    from main.office import permit_supervision       # pylint: disable=import-outside-toplevel
    return permit_supervision.forms(permit)[form]['f'].get('date', '')


def defaults(permit, kind):
    """The letter's fields the file already knows."""
    lic = permit_step7.payload(permit) if permit.licence_state == 'issued' else {}
    village = permit_step2._village(permit)                          # pylint: disable=protected-access
    owner = permit.people.first()
    answer = permit.bonyad or {}
    permit_no, permit_date = lic.get('permit_no', ''), lic.get('issue_date', '')
    data = {
        'name': owner.full_name if owner else '', 'father': owner.father_name if owner else '', 'national_id': owner.national_id if owner else '',
        'id_number': owner.id_number if owner else '', 'issued_at': owner.birth_place if owner else '', 'phone': owner.phone if owner else '',
        'village': village, 'section': lic.get('section', '') or 'مرکزی', 'address': _street(lic.get('address', '') or permit.address, village), 'plot': lic.get('plot_no', '') or permit.lot_number,
        'postal_code': lic.get('postal_code', '') or permit.postal_code, 'area': lic.get('area_after', ''), 'built': lic.get('built_allowed', ''),
        'n': lic.get('sd_north_actual', ''), 's': lic.get('sd_south_actual', ''), 'e': lic.get('sd_east_actual', ''), 'w': lic.get('sd_west_actual', ''),
        'street': next((lic.get(f'sd_{x}_passage') for x in ('north', 'south', 'east', 'west') if lic.get(f'sd_{x}_passage')), ''), 'hadi_date': '',
        'basis': f'شماره پروانه {permit_no} مورخ {permit_date}' if permit_no else '', 'utm_x': answer.get('center_x', ''), 'utm_y': answer.get('center_y', ''),
        'notes': '', 'permit_no': permit_no, 'permit_date': permit_date, 'endwork_no': (permit.endwork or {}).get('f', {}).get('number', '') if permit.endwork_state == 'issued' else '',
        'endwork_date': (permit.endwork or {}).get('f', {}).get('date', '') if permit.endwork_state == 'issued' else '', 'ref_no': '', 'ref_date': '', 'slip_no': '', 'slip_date': '',
        'number': '', 'date': permit_step2.today(), 'dehyari_name': permit_step7._signers(village)[0],         # pylint: disable=protected-access
        'tech_name': permit_step7._signers(village)[1], 'sup_name': lic.get('sup_name', ''), 'req_no': '', 'req_date': '',          # pylint: disable=protected-access
        'stage_text': CLEARANCES.get(kind, (0, ''))[1], 'report_date': _report_date(permit, kind),
    }
    return {key: data.get(key, '') for key in KINDS[kind]['fields'] + ('number', 'date', 'dehyari_name')}


def payload(permit, item):
    return {**defaults(permit, item['kind']), **{k: v for k, v in (item.get('f') or {}).items() if v != ''}}


def _owner_or_staff(actor, permit):
    return permit.request.user_id == actor.id or may_open(actor, permit)


def _check_open(permit):
    if permit.licence_state != 'issued':
        raise Conflict('نامه‌ی خدمات پس از صدور پروانه ممکن است.')


def _save(permit, items):
    permit.services = items
    permit.save(update_fields=['services', 'updated_at'])


def _collect(kind, post):
    return {key: _clean(post.get(f'f_{key}')) for key in KINDS[kind]['fields'] + ('number', 'date', 'dehyari_name')}


@transaction.atomic
def request(actor, permit, kind, post):
    """The owner (or the staff for a walk-in owner) asks for a letter."""
    if not _owner_or_staff(actor, permit):
        raise Forbidden('اجازه‌ی درخواست ندارید.')
    _check_open(permit)
    if kind not in KINDS:
        raise Invalid('نوع نامه نامعتبر است.')
    items = services(permit)
    if any(s['kind'] == kind and s['state'] in ('requested', 'approved') for s in items):
        raise Conflict('برای این نامه درخواست بازی دارید.')
    if kind in CLEARANCES:
        from main.office import permit_supervision       # pylint: disable=import-outside-toplevel
        if permit_supervision.forms(permit)[CLEARANCES[kind][0]]['state'] != 'approved':
            raise Conflict('گواهی عدم خلاف پس از تایید فرم نظارت همان مرحله ممکن است.')
    given = {key: _clean(post.get(f'f_{key}')) for key in KINDS[kind]['fields'] if post.get(f'f_{key}')}
    if kind in CLEARANCES:
        given.setdefault('req_no', permit_step2._next_number(permit_step2._village(permit)))       # pylint: disable=protected-access
        given.setdefault('req_date', permit_step2.today())
    shown = {**defaults(permit, kind), **given}
    missing = [LABELS[key] for key in REQUIRED.get(kind, ()) if not shown.get(key)]
    if missing:
        raise Invalid('این‌ها را وارد کنید: ' + '، '.join(missing))
    sid = max([s.get('id', 0) for s in items] + [0]) + 1
    items.append({'id': sid, 'kind': kind, 'state': 'requested', 'f': given, 'by': actor.get_full_name() or actor.username,
                  'at': timezone.localtime().strftime('%Y/%m/%d %H:%M')})
    _save(permit, items)
    sr = permit.request
    sr.add_workflow_step(action=f'درخواست نامه‌ی خدمات: {KINDS[kind]["title"]}', from_user=actor, to_role='clerk')
    sr.save(update_fields=['workflow_history', 'updated_at'])
    if sr.user_id == actor.id:
        step_flow.notify_staff(permit, 'درخواست نامه‌ی خدمات', f'متقاضی پرونده {permit.pk}: {KINDS[kind]["title"]}')
    return permit


@transaction.atomic
def save(actor, permit, sid, post):
    if not may_open(actor, permit):
        raise Forbidden('نامه را کارکنان دهیاری پر می‌کنند.')
    items = services(permit)
    item = find_service(permit, sid)
    if item['state'] not in ('requested', 'approved'):
        raise Conflict('این درخواست بسته شده است.')
    item['f'] = _collect(item['kind'], post)
    _save(permit, items)
    return permit


@transaction.atomic
def approve(actor, permit, sid, post):
    """The staff checked the letter: it gets its number and date and the owner may print it for the dehyari's signature."""
    if not may_open(actor, permit):
        raise Forbidden('تایید نامه با کارکنان دهیاری است.')
    items = services(permit)
    item = find_service(permit, sid)
    if item['state'] != 'requested':
        raise Conflict('درخواستی برای تایید وجود ندارد.')
    fields = _collect(item['kind'], post)
    if not digits(fields['number']):
        raise Invalid('شماره‌ی نامه را وارد کنید.')
    if not permit_form._jalali(fields['date']):                                  # pylint: disable=protected-access
        raise Invalid('تاریخ نامه را شمسی و درست وارد کنید.')
    fields['date'] = permit_form._jalali(fields['date'])                         # pylint: disable=protected-access
    missing = [LABELS[key] for key in REQUIRED.get(item['kind'], ()) if not fields.get(key)]
    if missing:
        raise Invalid('این‌ها لازم است: ' + '، '.join(missing))
    item.update({'f': fields, 'state': 'approved', 'approved_by': actor.get_full_name() or actor.username,
                 'approved_at': timezone.localtime().strftime('%Y/%m/%d %H:%M')})
    _save(permit, items)
    sr = permit.request
    sr.add_workflow_step(action=f'تایید نامه‌ی خدمات شماره {fields["number"]}: {KINDS[item["kind"]]["title"]}', from_user=actor, to_role='citizen')
    sr.save(update_fields=['workflow_history', 'updated_at'])
    notify(sr.user, 'نامه‌ی شما آماده است', f'نامه‌ی «{KINDS[item["kind"]]["title"]}» تایید شد؛ آن را چاپ کنید و برای مهر و امضای دهیار به دهیاری ببرید.', request=sr)
    return permit


@transaction.atomic
def reject(actor, permit, sid, reason):
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی این کار را ندارید.')
    items = services(permit)
    item = find_service(permit, sid)
    if item['state'] != 'requested':
        raise Conflict('درخواستی برای رد وجود ندارد.')
    reason = _clean(reason, 500)
    if not reason:
        raise Invalid('دلیل رد را بنویسید.')
    item.update({'state': 'rejected', 'reason': reason})
    _save(permit, items)
    notify(permit.request.user, 'درخواست نامه رد شد', f'{KINDS[item["kind"]]["title"]}: {reason}', request=permit.request)
    return permit


@transaction.atomic
def cancel(actor, permit, sid):
    if permit.request.user_id != actor.id:
        raise Forbidden('فقط متقاضی درخواستش را لغو می‌کند.')
    items = services(permit)
    item = find_service(permit, sid)
    if item['state'] != 'requested':
        raise Conflict('این درخواست دیگر قابل لغو نیست.')
    item['state'] = 'cancelled'
    _save(permit, items)
    return permit


@transaction.atomic
def issue(actor, permit, sid, post):
    """The dehyari signed and stamped the printed letter and it was handed over."""
    if not may_open(actor, permit):
        raise Forbidden('ثبت تحویل نامه با کارکنان دهیاری است.')
    items = services(permit)
    item = find_service(permit, sid)
    if item['state'] != 'approved':
        raise Conflict('نامه‌ای برای ثبت تحویل وجود ندارد.')
    if post.get('signed') != 'on':
        raise Invalid('تیک «نامه با مهر و امضای دهیار به متقاضی تحویل شد» را بزنید.')
    item.update({'state': 'issued', 'issued_by': actor.get_full_name() or actor.username, 'issued_at': timezone.localtime().strftime('%Y/%m/%d %H:%M')})
    _save(permit, items)
    notify(permit.request.user, 'نامه‌ی خدمات تحویل شد', f'{KINDS[item["kind"]]["title"]} با امضای دهیار تحویل شد.', request=permit.request)
    return permit
