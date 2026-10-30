"""Building permit, steps 5 and 6: the fees and the introduction to the Social Security Organisation.

Step 5 (the fees): once the dehyari has signed the plans the financial officer (مسئول مالی) goes through the 31 rows of the
«فرم محاسبه عوارض و بهای خدمات», picks the rows that apply to this owner, sets the amount of each and sends the list to the
owner. The owner agrees (the file moves to step 6) or objects with a note and the officer revises. The dehyari has no
calculation formula, so the officer decides every amount; a row's factors (area, council factor, value ...) are only kept
beside the amount and the page offers their product as a suggestion.

Step 6 (the introduction): the owner pays the fees at the dehyari's bank account and the receipts are recorded (the owner may
upload the slip, the staff or the officer confirm it, or record a payment received on the spot). When the confirmed payments
cover the total, the clerk / expert / dehyari issue the letter introducing the owner to the Social Security Organisation,
which names the building fees the insurance share is taken from. The letter is printed, signed and stamped by the dehyari.
"""
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from main.access import can
from main.accounting.parse import digits, jalali_str, parse_amount, parse_jalali
from main.models import PermitDocument, PermitFile
from main.notifications import notify
from main.office import permit_form, permit_step2, permit_step4, permits, step_flow
from main.office.errors import Conflict, Forbidden, Invalid
from main.office.permits import may_open

MAX_RECEIPTS = 10
RECEIPT_EXTENSIONS = ('.pdf', '.jpg', '.jpeg', '.png')
FACTORS = (('area', 'عرصه (م²)'), ('built', 'اعیان (م²)'), ('b', 'ضریب شورا (B)'), ('value', 'ارزش معاملاتی عرصه (P، ریال)'),
           ('coef', 'ضریب P'), ('height', 'ارتفاع (متر)'), ('floors', 'تعداد طبقات'), ('diff', 'تفاضل قیمت کارشناسی (ریال)'))
EXTRA_ROWS = 3
OBJECTION_STATES = ('', 'objected')
NO_FORMULA = 'این دهیاری فاقد فرمول محاسبه عوارض می‌باشد.'
GROUP_FLOORS = ('پیلوت، زیرزمین', 'طبقه همکف', 'طبقه اول', 'طبقه دوم و بالاتر')


def _catalogue():
    rows = []

    def building(group, waste=None):
        for floor in GROUP_FLOORS:
            rows.append({'no': len(rows) + 1, 'group': group, 'title': f'عوارض احداث بنا {floor}', 'build': True})
        rows.append({'no': len(rows) + 1, 'group': group, 'title': 'عوارض پیش‌آمدگی و بالکن', 'build': True})
        if waste:
            rows.append({'no': len(rows) + 1, 'group': group, 'title': f'بهای خدمات مدیریت پسماند {waste}', 'build': False})

    building('مسکونی', 'مسکونی')
    building('تجاری', 'تجاری')
    building('خدماتی - کارگاهی')
    building('صنعتی - تاسیساتی')
    for group, title in (
            ('حصارکشی', 'عوارض حصارکشی'),
            ('الحاق', 'سهم خدمات عمومی اراضی الحاقی به محدوده از مزروعی و مسکونی'),
            ('ارزش افزوده', 'عوارض ارزش افزوده ناشی از تغییر کاربری مسکونی به تجاری'),
            ('ارزش افزوده', 'عوارض ارزش افزوده ناشی از تغییر کاربری اداری، درمانی، ورزشی، آموزشی، فرهنگی، مذهبی، تاسیسات، حمل و نقل، انبار و فضای سبز به مسکونی'),
            ('ارزش افزوده', 'عوارض ارزش افزوده ناشی از اجرای طرح‌های عمرانی روستایی'),
            ('سایر', 'بهای کارشناسی'), ('سایر', 'بهای آتش‌نشانی'), ('سایر', 'تشکیل پرونده'),
            ('سایر', 'عوارض سالیانه املاک و مستحدثات (سطح روستا)')):
        rows.append({'no': len(rows) + 1, 'group': group, 'title': title, 'build': False})
    return rows


ROWS = _catalogue()
ROW_NUMBERS = {row['no'] for row in ROWS}
BUILD_ROWS = {row['no'] for row in ROWS if row['build']}


def _factor(value):
    """A factor kept as typed (Latin digits, «۱/۳» as 1.3); anything that is not a number is dropped."""
    text = digits(value).replace('٫', '.').replace('/', '.').replace(',', '').replace(' ', '')
    try:
        float(text)
    except ValueError:
        return ''
    return text[:14]


def _money(value, label):
    try:
        return parse_amount(value)
    except Invalid as exc:
        raise Invalid(f'{label}: {exc}') from exc


def _clean(value, limit=200):
    return step_flow.clean(value, limit)


def total_of(fees):
    amount = sum(row.get('amount', 0) for row in (fees.get('rows') or {}).values() if row.get('on'))
    return amount + sum(extra.get('amount', 0) for extra in fees.get('extra') or [])


def building_fees(fees):
    """What the insurance share is taken from: the rows that charge the building itself."""
    return sum(row.get('amount', 0) for no, row in (fees.get('rows') or {}).items() if row.get('on') and int(no) in BUILD_ROWS)


def fee_rows(permit):
    """The catalogue with what the officer saved on each row, for the page."""
    saved = (permit.fees or {}).get('rows') or {}
    out = []
    for row in ROWS:
        mine = saved.get(str(row['no'])) or {}
        out.append({**row, 'on': bool(mine.get('on')), 'amount': mine.get('amount') or '', 'note': mine.get('note', ''),
                    'factors': [(key, label, (mine.get('f') or {}).get(key, '')) for key, label in FACTORS]})
    return out


def extras(permit):
    saved = list((permit.fees or {}).get('extra') or [])
    return [{'title': e.get('title', ''), 'amount': e.get('amount') or ''} for e in saved] + [{'title': '', 'amount': ''}] * (EXTRA_ROWS - len(saved))


def can_define(user):
    return can(user, 'permit.fees')


def find(user, file_id):
    """The file for the fee screens: its owner, the file staff and the village's financial officer (not before step 5)."""
    permit = permits.find(user, file_id)
    if permit is not None:
        return permit
    permit = PermitFile.objects.select_related('request', 'request__user', 'request__user__profile', 'parcel').filter(pk=file_id, track='permit').first()
    if permit and can(user, 'permit.fees') and permit.stage_no >= 5 and permits.files_for(user).filter(pk=permit.pk).exists():
        return permit
    return None


def _accountants(permit):
    village = permit_step2._village(permit)      # pylint: disable=protected-access
    return get_user_model().objects.filter(is_active=True, profile__role='accountant', profile__city_village=village)


def tell_the_officer(permit):
    """The plans were signed: the financial officer has the fees to define."""
    for officer in _accountants(permit):
        notify(officer, 'عوارض پرونده‌ی پروانه', f'نقشه‌های پرونده {permit.pk} امضا شد؛ عوارض آن را تعیین کنید.', request=permit.request)


def _step(permit, number):
    if permit.stage_no != number:
        raise Conflict('پرونده در این مرحله نیست.')


# ---------- step 5: the fees ----------

@transaction.atomic
def save_fees(actor, permit, post, *, offer=False):
    """The officer's list: the rows that apply (with their amounts), up to three extra rows and a note; ``offer`` sends it."""
    if not can_define(actor):
        raise Forbidden('عوارض را مسئول مالی تعیین می‌کند.')
    _step(permit, 5)
    if permit.fees_state not in OBJECTION_STATES:
        raise Conflict('عوارض برای متقاضی فرستاده شده است.')
    rows = {}
    for row in ROWS:
        no = row['no']
        if post.get(f'r{no}_on') != 'on':
            continue
        amount = _money(post.get(f'r{no}_amount'), f'ردیف {no}')
        if not amount:
            raise Invalid(f'مبلغ ردیف {no} را وارد کنید یا آن را بردارید.')
        rows[str(no)] = {'on': True, 'amount': amount, 'note': _clean(post.get(f'r{no}_note'), 150),
                         'f': {key: _factor(post.get(f'r{no}_{key}')) for key, _ in FACTORS if _factor(post.get(f'r{no}_{key}'))}}
    extra = []
    for n in range(1, EXTRA_ROWS + 1):
        title, amount = _clean(post.get(f'x{n}_title'), 120), _money(post.get(f'x{n}_amount'), f'ردیف اضافه {n}')
        if title and amount:
            extra.append({'title': title, 'amount': amount})
        elif title or amount:
            raise Invalid(f'ردیف اضافه {n}: هم عنوان و هم مبلغ لازم است.')
    fees = {'rows': rows, 'extra': extra, 'notes': _clean(post.get('notes'), 600), 'objection': (permit.fees or {}).get('objection', '')}
    fees['total'] = total_of(fees)
    if offer and not fees['total']:
        raise Invalid('دست‌کم یک ردیف با مبلغ لازم است.')
    permit.fees = fees
    update = ['fees', 'updated_at']
    if offer:
        permit.fees_state, permit.fees_at, permit.fees_by = 'offered', timezone.now(), actor
        update += ['fees_state', 'fees_at', 'fees_by']
        sr = permit.request
        sr.add_workflow_step(action=f'تعیین عوارض و بهای خدمات: {fees["total"]:,} ریال - ارسال برای تایید متقاضی', from_user=actor, to_role='citizen')
        sr.save(update_fields=['workflow_history', 'updated_at'])
        notify(sr.user, 'عوارض پرونده‌ی شما تعیین شد',
               f'مجموع عوارض و بهای خدمات پرونده {permit.pk}: {fees["total"]:,} ریال. آن را ببینید و تایید کنید.', request=sr)
    permit.save(update_fields=update)
    return permit


def offer(actor, permit, post):
    return save_fees(actor, permit, post, offer=True)


@transaction.atomic
def object_to(user, permit, note):
    """The owner does not agree: the officer sees the note and revises."""
    if permit.request.user_id != user.id:
        raise Forbidden('فقط متقاضی می‌تواند به عوارض اعتراض کند.')
    _step(permit, 5)
    if permit.fees_state != 'offered':
        raise Conflict('عوارضی برای پاسخ وجود ندارد.')
    note = _clean(note, 800)
    if not note:
        raise Invalid('بنویسید با کدام ردیف مشکل دارید.')
    fees = dict(permit.fees or {})
    fees['objection'] = note
    permit.fees, permit.fees_state = fees, 'objected'
    permit.save(update_fields=['fees', 'fees_state', 'updated_at'])
    sr = permit.request
    sr.add_workflow_step(action='اعتراض متقاضی به عوارض', from_user=user, to_role='accountant', notes=note)
    sr.save(update_fields=['workflow_history', 'updated_at'])
    for officer in list(_accountants(permit)) + list(permits._staff_to_tell(permit_step2._village(permit))):      # pylint: disable=protected-access
        notify(officer, 'اعتراض به عوارض', f'متقاضی پرونده {permit.pk} به عوارض اعتراض کرد.', request=sr)
    return permit


@transaction.atomic
def approve(user, permit):
    """The owner agrees to the fees: step 6, the introduction to the Social Security Organisation."""
    if permit.request.user_id != user.id:
        raise Forbidden('فقط متقاضی می‌تواند عوارض را تایید کند.')
    _step(permit, 5)
    if permit.fees_state != 'offered':
        raise Conflict('عوارضی برای تایید وجود ندارد.')
    permit.fees_state, permit.fees_approved_at, permit.stage_no = 'approved', timezone.now(), 6
    permit.save(update_fields=['fees_state', 'fees_approved_at', 'stage_no', 'updated_at'])
    sr = permit.request
    total = (permit.fees or {}).get('total', 0)
    sr.add_workflow_step(action=f'تایید عوارض ({total:,} ریال) توسط متقاضی - پایان مرحله ۵', from_user=user, to_role='clerk')
    sr.save(update_fields=['workflow_history', 'updated_at'])
    step_flow.notify_staff(permit, 'عوارض تایید شد', f'متقاضی پرونده {permit.pk} عوارض را تایید کرد؛ پرداخت و معرفی‌نامه‌ی تامین اجتماعی.')
    return permit


# ---------- step 6: the payments and the letter ----------

def payments(permit):
    return list((permit.insurance or {}).get('payments') or [])


def paid_total(permit):
    return sum(p['amount'] for p in payments(permit) if p.get('ok'))


def _may_record(actor, permit):
    return may_open(actor, permit) or (can(actor, 'permit.fees') and permits.files_for(actor).filter(pk=permit.pk).exists())


@transaction.atomic
def add_payment(actor, permit, post, uploads=()):
    """A fee slip: the owner types it (and may attach the scan) and the staff confirm it; a payment the staff record is confirmed at once."""
    mine = permit.request.user_id == actor.id
    if not (mine or _may_record(actor, permit)):
        raise Forbidden('اجازه‌ی ثبت پرداخت را ندارید.')
    _step(permit, 6)
    if permit.insurance_state:
        raise Conflict('معرفی‌نامه صادر شده است.')
    amount = _money(post.get('amount'), 'مبلغ')
    if not amount:
        raise Invalid('مبلغ پرداخت را وارد کنید.')
    try:
        paid_on = parse_jalali(post.get('date', ''))
    except Invalid as exc:
        raise Invalid('تاریخ فیش را شمسی وارد کنید، مثل ۱۴۰۵/۰۷/۲۶.') from exc
    number = _clean(digits(post.get('slip_no')), 40)
    if not number:
        raise Invalid('شماره‌ی فیش (یا شماره‌ی پیگیری) را وارد کنید.')
    uploads = list(uploads)[:MAX_RECEIPTS]
    for upload in uploads:
        error = permit_form._file_error(upload, RECEIPT_EXTENSIONS, 10 * 1024 * 1024)       # pylint: disable=protected-access
        if error:
            raise Invalid(error)
    data = dict(permit.insurance or {})
    rows = list(data.get('payments') or [])
    if any(p['slip_no'] == number for p in rows):
        raise Conflict('این شماره‌ی فیش قبلا ثبت شده است.')
    docs = [PermitDocument.objects.create(file=permit, kind='fee_receipt', document=u, original_name=u.name[:200], size=u.size, uploaded_by=actor).pk
            for u in uploads]
    rows.append({'id': max([p['id'] for p in rows] + [0]) + 1, 'slip_no': number, 'date': jalali_str(paid_on), 'amount': amount,
                 'note': _clean(post.get('note'), 150), 'docs': docs, 'ok': not mine, 'by': actor.get_full_name() or actor.username,
                 'at': timezone.localtime().strftime('%Y/%m/%d %H:%M')})
    data['payments'] = rows
    permit.insurance = data
    permit.save(update_fields=['insurance', 'updated_at'])
    if mine:
        for staff in list(permits._staff_to_tell(permit_step2._village(permit))) + list(_accountants(permit)):      # pylint: disable=protected-access
            notify(staff, 'فیش پرداخت عوارض', f'متقاضی پرونده {permit.pk} فیش پرداخت را ثبت کرد؛ بررسی و تایید کنید.', request=permit.request)
    return permit


@transaction.atomic
def confirm_payment(actor, permit, payment_id):
    if not _may_record(actor, permit):
        raise Forbidden('تایید پرداخت با کارکنان دهیاری و مسئول مالی است.')
    _step(permit, 6)
    data = dict(permit.insurance or {})
    rows = list(data.get('payments') or [])
    row = next((p for p in rows if p['id'] == payment_id), None)
    if row is None:
        raise Conflict('پرداخت پیدا نشد.')
    row['ok'], row['confirmed_by'] = True, actor.get_full_name() or actor.username
    data['payments'] = rows
    permit.insurance = data
    permit.save(update_fields=['insurance', 'updated_at'])
    sr = permit.request
    sr.add_workflow_step(action=f'تایید فیش پرداخت {row["slip_no"]} به مبلغ {row["amount"]:,} ریال', from_user=actor, to_role='clerk')
    sr.save(update_fields=['workflow_history', 'updated_at'])
    return permit


@transaction.atomic
def remove_payment(actor, permit, payment_id):
    """An unconfirmed slip may be removed by whoever typed it (the owner) or by the staff; a confirmed one only by the staff."""
    _step(permit, 6)
    if permit.insurance_state:
        raise Conflict('معرفی‌نامه صادر شده است.')
    data = dict(permit.insurance or {})
    rows = list(data.get('payments') or [])
    row = next((p for p in rows if p['id'] == payment_id), None)
    if row is None:
        raise Conflict('پرداخت پیدا نشد.')
    staff = _may_record(actor, permit)
    if not (staff or (permit.request.user_id == actor.id and not row.get('ok'))):
        raise Forbidden('اجازه‌ی حذف این پرداخت را ندارید.')
    for doc in permit.documents.filter(pk__in=row.get('docs') or [], kind='fee_receipt'):
        doc.document.delete(save=False)
        doc.delete()
    data['payments'] = [p for p in rows if p['id'] != payment_id]
    permit.insurance = data
    permit.save(update_fields=['insurance', 'updated_at'])
    return permit


def letter_defaults(permit):
    """What the introduction letter needs that the file knows."""
    owner = permit.people.first()
    village = permit_step2._village(permit)                       # pylint: disable=protected-access
    order = permit_step4.payload(permit)['order']
    passage = next((s.get('approved') for s in (order.get('sides') or {}).values() if s.get('approved')), '')
    saved = (permit.insurance or {}).get('letter') or {}
    first = permit_step2._next_number(village)                    # pylint: disable=protected-access
    base = building_fees(permit.fees or {})
    area = saved.get('area') or (permit.bonyad or {}).get('floor_area') or order.get('area') or ''
    if isinstance(area, float) and area == int(area):
        area = int(area)
    return {'number': saved.get('number') or first, 'date': saved.get('date') or permit_step2.today(),
            'branch': saved.get('branch', ''), 'owner': owner.full_name if owner else '', 'father': owner.father_name if owner else '',
            'base': saved.get('base') or base, 'area': area,
            'street': saved.get('street') or passage, 'no_formula': saved.get('no_formula', True), 'village': village,
            'paid': paid_total(permit), 'total': (permit.fees or {}).get('total', 0), 'building_fees': base}


@transaction.atomic
def issue_letter(actor, permit, post):
    """The letter introducing the owner to the Social Security Organisation: recorded when the confirmed payments cover the fees."""
    if not may_open(actor, permit):
        raise Forbidden('معرفی‌نامه را کارکنان دهیاری صادر می‌کنند.')
    _step(permit, 6)
    if permit.insurance_state:
        raise Conflict('معرفی‌نامه قبلا صادر شده است.')
    if not permit.paid_up:
        raise Conflict('پرداخت‌های تاییدشده هنوز کل عوارض را نمی‌پوشاند.')
    branch = _clean(post.get('branch'), 80)
    if not branch:
        raise Invalid('نام شعبه‌ی تامین اجتماعی را بنویسید.')
    base = _money(post.get('base'), 'مبلغ عوارض ساختمان')
    if not base:
        raise Invalid('مبلغ عوارض صدور پروانه (مبنای حق بیمه) را وارد کنید.')
    try:
        parse_jalali(post.get('date', ''))
    except Invalid as exc:
        raise Invalid('تاریخ نامه را شمسی وارد کنید.') from exc
    letter = {'number': _clean(post.get('number'), 40), 'date': digits(post.get('date')), 'branch': branch, 'base': base,
              'area': _clean(post.get('area'), 20), 'street': _clean(post.get('street'), 10), 'no_formula': post.get('no_formula') == 'on',
              'by': actor.get_full_name() or actor.username, 'at': timezone.localtime().strftime('%Y/%m/%d %H:%M')}
    if not letter['number']:
        raise Invalid('شماره‌ی نامه را وارد کنید.')
    data = dict(permit.insurance or {})
    data['letter'] = letter
    permit.insurance, permit.insurance_state, permit.insurance_at = data, 'introduced', timezone.now()
    permit.save(update_fields=['insurance', 'insurance_state', 'insurance_at', 'updated_at'])
    sr = permit.request
    sr.add_workflow_step(action=f'صدور معرفی‌نامه‌ی تامین اجتماعی (شعبه {branch}، مبنا {base:,} ریال)', from_user=actor, to_role='citizen')
    sr.save(update_fields=['workflow_history', 'updated_at'])
    notify(sr.user, 'معرفی‌نامه‌ی تامین اجتماعی آماده است',
           'نامه‌ی معرفی شما به تامین اجتماعی آماده است؛ چاپ‌شده و امضاشده را از دهیاری بگیرید و به شعبه ببرید.', request=sr)
    return permit
