"""Construction without a permit, step 5: the introduction to a judiciary expert, the neighbours' consent and the notarial undertaking.

- **The experts** (کارشناسان دادگستری) are listed by the dehyari of the village (only the dehyari adds or switches them off). Any of the
  clerk / technical expert / dehyari picks one for the owner and issues the introduction letter, which the system fills from the file.
- **The neighbours' consent** (تعهدنامه‌ی مالک و همسایگان): the form is filled from the file and from the village map (the plots touching the
  east and west sides, with the owner data of their archive); the owner prints it, the neighbours sign it, the owner uploads the scan.
- **The notarial undertaking** (تعهد محضری): the system types the draft from the file (the limits, the areas, the floors); the owner takes
  it to the notary, hands the original to the dehyari and uploads the scan with its number, date and office.
Each upload is confirmed, or sent back with a reason, by any of the three staff (``permit.open``); when the introduction is made and
both papers are confirmed, any of them confirms the step and the file goes on to step 6.
"""
from django.db import transaction
from django.utils import timezone

from main import lifecycle
from main.access import can
from main.accounting.parse import digits
from main.models import JudicialExpert, MapParcel, PermitDocument
from main.notifications import notify
from main.office import permit_form, permit_step2, permits, plotmap
from main.office.directory import village_of
from main.office.errors import Conflict, Forbidden, Invalid, NotFound
from main.office.permits import may_open

CONSENT_KIND, DEED_KIND = 'consent_form', 'deed_scan'
MAX_FILES = 8
MAX_NEIGHBOURS = 3
SIDE_LABELS = {'north': 'شمال', 'east': 'شرق', 'south': 'جنوب', 'west': 'غرب'}
SIDE_ORDER = ('east', 'west', 'north', 'south')             # the owner's right and left first, as the commission asks


def _now():
    return timezone.now().strftime('%Y-%m-%d %H:%M')


def _clean(value, limit=150):
    return ' '.join(str(value or '').split())[:limit]


def _staff(permit):
    return permits._staff_to_tell(permit_step2._village(permit))       # pylint: disable=protected-access


def find(user, file_id):
    permit = permits.find(user, file_id, any_track=True)
    return permit if permit is not None and permit.unlicensed else None


def at_step(permit):
    return permit.unlicensed and permit.stage_no == 5 and permit.state == 'done'


def documents(permit, kind):
    return list(permit.documents.filter(kind=kind))


# ---------- the experts the dehyari lists ----------

def may_manage_experts(user):
    return can(user, 'permit.experts') and bool(village_of(user))


def experts_for(village, active_only=True):
    rows = JudicialExpert.objects.filter(city_village=village)
    return rows.filter(active=True) if active_only else rows


def add_expert(actor, post):
    if not may_manage_experts(actor):
        raise Forbidden('فقط دهیار فهرست کارشناسان را مدیریت می‌کند.')
    name = _clean(post.get('name'), 120)
    if len(name) < 4:
        raise Invalid('نام کارشناس را وارد کنید.')
    village = village_of(actor)
    if JudicialExpert.objects.filter(city_village=village, name=name, active=True).exists():
        raise Conflict('این کارشناس در فهرست هست.')
    phone = digits(post.get('phone', ''))
    return JudicialExpert.objects.create(city_village=village, name=name, field=_clean(post.get('field'), 120), phone=phone[:20], created_by=actor)


def set_expert_active(actor, expert_id, active):
    if not may_manage_experts(actor):
        raise Forbidden('فقط دهیار فهرست کارشناسان را مدیریت می‌کند.')
    expert = JudicialExpert.objects.filter(pk=expert_id, city_village=village_of(actor)).first()
    if expert is None:
        raise NotFound('کارشناس پیدا نشد.')
    expert.active = active
    expert.save(update_fields=['active'])
    return expert


# ---------- the introduction letter ----------

def _owner(permit):
    return permit.people.first()


def letter_payload(permit, actor=None):
    """What the letter needs, from the file: the owner, the address, the phone, the signer."""
    owner = _owner(permit)
    saved = (permit.commit or {}).get('expert') or {}
    village = permit_step2._village(permit)                # pylint: disable=protected-access
    return {
        'village': village, 'owner': owner.full_name, 'phone': owner.phone,
        'address': permit.address or f'روستای {village}', 'date': saved.get('letter_date') or permit_step2.today(), 'number': saved.get('letter_no', ''),
        'expert': saved.get('name', ''), 'field': saved.get('field', ''),
        'signer': (actor.get_full_name() or actor.username) if actor is not None and can(actor, 'permit.sign') else '',
        'experts': [{'id': e.pk, 'name': e.name, 'field': e.field, 'phone': e.phone} for e in experts_for(village)],
    }


@transaction.atomic
def introduce(actor, permit, post):
    """Any of the three staff: the owner is introduced to the expert chosen from the dehyari's list."""
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی این کار را ندارید.')
    if not at_step(permit):
        raise Conflict('پرونده در مرحله‌ی معرفی به کارشناس دادگستری نیست.')
    expert = experts_for(permit_step2._village(permit)).filter(pk=post.get('expert') or 0).first()       # pylint: disable=protected-access
    if expert is None:
        raise Invalid('کارشناس را از فهرست دهیاری انتخاب کنید.')
    date = permit_form._jalali(post.get('letter_date', '')) or permit_step2.today()          # pylint: disable=protected-access
    commit = dict(permit.commit or {})
    commit['expert'] = {'id': expert.pk, 'name': expert.name, 'field': expert.field, 'phone': expert.phone, 'letter_no': _clean(post.get('letter_no'), 40),
                        'letter_date': date, 'by': actor.get_full_name() or actor.username, 'at': _now()}
    permit.commit, permit.expert_state = commit, 'introduced'
    permit.save(update_fields=['commit', 'expert_state', 'updated_at'])
    sr = permit.request
    sr.add_workflow_step(action=f'معرفی مالک به کارشناس دادگستری: {expert.name} (مرحله ۵)', from_user=actor, to_role='citizen')
    sr.save(update_fields=['workflow_history', 'updated_at'])
    notify(sr.user, 'معرفی به کارشناس دادگستری', f'شما به {expert.name} معرفی شدید؛ نامه‌ی معرفی را از پرونده چاپ کنید و به او بدهید.', request=sr)
    return permit


# ---------- the neighbours' consent ----------

def _blank_neighbour(side=''):
    return {'side': side, 'name': '', 'father': '', 'national_id': '', 'birth': '', 'address': '', 'phone': ''}


def neighbours_default(permit):
    """Up to three neighbours: the plots touching the owner's sides on the village map, with the owner data of their archive."""
    village_map = permit_step2.village_map_of(permit)         # pylint: disable=protected-access
    found = []
    if permit.parcel_id and village_map:
        touching = plotmap.neighbours(village_map, permit.parcel_id)
        for side in SIDE_ORDER:
            for parcel_id in touching.get(side, []):
                parcel = MapParcel.objects.filter(pk=parcel_id).select_related('archive').first()
                archive = getattr(parcel, 'archive', None) if parcel else None
                row = _blank_neighbour(side)
                if archive is not None:
                    row.update(name=archive.owner_name, national_id=archive.owner_national_id, phone=archive.owner_phone)
                village = permit_step2._village(permit)         # pylint: disable=protected-access
                row['address'] = f'روستای {village}' + (f'، قطعه {parcel.number}' if parcel and parcel.number else '')
                found.append(row)
    for side in SIDE_ORDER:                      # sides the map could not name stay open for the owner to write
        if len(found) >= MAX_NEIGHBOURS:
            break
        if not any(r['side'] == side for r in found):
            found.append(_blank_neighbour(side))
    return found[:MAX_NEIGHBOURS]


def consent_data(permit):
    owner = _owner(permit)
    saved = (permit.commit or {}).get('consent') or {}
    rows = saved.get('neighbours') or neighbours_default(permit)
    rows = [{**_blank_neighbour(), **r} for r in rows][:MAX_NEIGHBOURS]
    while len(rows) < MAX_NEIGHBOURS:
        rows.append(_blank_neighbour())
    return {
        'village': permit_step2._village(permit), 'date': saved.get('date') or permit_step2.today(),         # pylint: disable=protected-access
        'owner': {'name': owner.full_name, 'father': owner.father_name, 'national_id': owner.national_id, 'birth': owner.birth_date,
                  'address': permit.address, 'phone': owner.phone},
        'neighbours': rows,
    }


def _clean_neighbours(post):
    out = []
    for i in range(MAX_NEIGHBOURS):
        row = {key: _clean(post.get(f'n{i}_{key}'), 150) for key in ('name', 'father', 'national_id', 'birth', 'address', 'phone')}
        row['side'] = post.get(f'n{i}_side') if post.get(f'n{i}_side') in SIDE_LABELS else ''
        row['national_id'] = ''.join(ch for ch in digits(row['national_id']) if ch.isdigit())[:10]
        row['phone'] = digits(row['phone'])[:11]
        out.append(row)
    return out


@transaction.atomic
def save_consent(user, permit, post):
    """The owner (or the staff for him) saves the consent form's fields; the neighbours' details are then printed on it."""
    if not at_step(permit):
        raise Conflict('پرونده در مرحله‌ی تعهدات نیست.')
    if permit.request.user_id != user.id and not may_open(user, permit):
        raise NotFound('پرونده پیدا نشد.')
    commit = dict(permit.commit or {})
    commit['consent'] = {**(commit.get('consent') or {}), 'neighbours': _clean_neighbours(post), 'date': permit_step2.today()}
    permit.commit = commit
    permit.save(update_fields=['commit', 'updated_at'])
    return permit


# ---------- the notarial undertaking ----------

DEED_CLAUSES = (
    'نظر به اینکه بنای احداثی موصوف مطابق آیین‌نامه ۲۸۰۰ مقررات ملی ساختمان انجام نشده و استحکام نسبی آن توسط کارشناس رسمی دادگستری تأیید شده است، '
    'اینجانب متعهد و مکلف می‌شوم بلافاصله نسبت به مقاوم‌سازی و بهسازی ساختمان زیر نظر سازمان نظام مهندسی اقدام نمایم تا سازه‌ی ساختمان '
    'استحکام کافی را در برابر بارهای جانبی و ثقلی پیدا کند.',
    'متعهد می‌شوم چنانچه اعضای کمیسیون ماده ۹۹ به درخواست اینجانب یا دهیاری و بخشداری برای واگذاری انشعابات خدمات آب، برق، تلفن و گاز، '
    'قبل از مقاوم‌سازی رأی جریمه صادر کنند، ضمن پرداخت جریمه به دهیاری، فوراً نسبت به مقاوم‌سازی اقدام نمایم؛ در غیر این صورت هیچ‌گونه '
    'مسئولیت حقوقی متوجه دهیاری و بخشداری و اعضای کمیسیون ماده ۹۹ و کارشناس رسمی دادگستری نخواهد بود و هرگونه خسارت ناشی از ضعف سازه '
    'یا حوادث غیرمترقبه به عهده‌ی اینجانب خواهد بود.',
    'متعهد می‌شوم هنگام عملیات زیربنایی و روبنایی، جدول‌کشی و آسفالت معبر و زیرسازی، چنانچه به دلیل عدم استحکام بنا خسارتی به ملک و معبر '
    'وارد آید، مسئولیت آن با اینجانب باشد، و در صورت انتقال ملک، موارد تعهد خود را به خریدار تفهیم کرده و مراتب را به دهیاری اعلام نمایم.',
    'متعهد می‌شوم بدون هیچ‌گونه قید و شرطی، پس از ابلاغ رأی کمیسیون ماده ۹۹ در موعد مقرر اقدام نمایم و حق هرگونه ایراد و اعتراض را از خود سلب می‌کنم.',
    'آب مصرفی را صرفاً جهت شرب و بهداشت استفاده کنم و هزینه‌ی آب، برق و گاز را به‌موقع بپردازم؛ در صورت واگذاری موقت انشعابات، '
    'تابع تعرفه‌ی موقت و شرایط آیین‌نامه‌ی تکمیلی تعرفه‌های آب، برق و گاز باشم و در غیر این صورت انشعابات قطع شود.',
)


def _meters(value):
    return f'{float(value or 0):g}'


def deed_default(permit):
    """The draft of the undertaking, typed from the file: who, where, the limits, the areas and the floors, then the clauses."""
    owner = _owner(permit)
    details = permit.details or {}
    limits = permit_step2.limits_for(permit)
    parts = []
    for side, label in (('north', 'شمالاً'), ('east', 'شرقاً'), ('south', 'جنوباً'), ('west', 'غرباً')):
        lim = limits.get(side) or {}
        parts.append(f'{label} بطول {_meters(lim.get("length"))} متر به {lim.get("to") or "..."}')
    head = (f'نظر به اینکه اینجانب {owner.full_name} فرزند {owner.father_name or "..."} با شماره ملی {owner.national_id} اظهار می‌نمایم که متصرف یک قطعه زمین '
            f'واقع در {permit.address or "..."} به حدود اربعه: ' + '، '.join(parts) + ' می‌باشم؛ با توجه به اینکه در حال حاضر بنای احداثی موصوف به مساحت زمین '
            f'{_meters(permit.area_m2)} مترمربع و مساحت اعیان {_meters(details.get("built_area"))} مترمربع در {int(details.get("floors") or 1)} طبقه است،')
    return '\n\n'.join([head, *DEED_CLAUSES])


def deed_data(permit):
    owner = _owner(permit)
    saved = (permit.commit or {}).get('deed') or {}
    return {'village': permit_step2._village(permit), 'text': saved.get('text') or deed_default(permit),          # pylint: disable=protected-access
            'owner': owner.full_name, 'father': owner.father_name, 'national_id': owner.national_id, 'birth': owner.birth_date,
            'id_number': owner.id_number, 'phone': owner.phone, 'address': permit.address,
            'number': saved.get('number', ''), 'date': saved.get('date', ''), 'office': saved.get('office', '')}


@transaction.atomic
def save_deed(user, permit, post):
    """The draft text may be edited (the notary writes the final one); it is kept for the print."""
    if not at_step(permit):
        raise Conflict('پرونده در مرحله‌ی تعهدات نیست.')
    if permit.request.user_id != user.id and not may_open(user, permit):
        raise NotFound('پرونده پیدا نشد.')
    text = '\n\n'.join(' '.join(p.split()) for p in (post.get('text') or '').split('\n\n') if p.strip())
    if len(text) < 100:
        raise Invalid('متن تعهد خیلی کوتاه است.')
    commit = dict(permit.commit or {})
    commit['deed'] = {**(commit.get('deed') or {}), 'text': text[:8000]}
    permit.commit = commit
    permit.save(update_fields=['commit', 'updated_at'])
    return permit


# ---------- the owner's uploads and the staff's decisions ----------

def _owner_check(user, permit):
    if permit.request.user_id != user.id:
        raise NotFound('پرونده پیدا نشد.')
    if not at_step(permit):
        raise Conflict('پرونده در مرحله‌ی تعهدات نیست.')


def _replace(permit, kind, found, user):
    for old in documents(permit, kind):
        old.document.delete(save=False)
        old.delete()
    for upload in found:
        PermitDocument.objects.create(file=permit, kind=kind, document=upload, original_name=upload.name[:200], size=upload.size, uploaded_by=user)


def _upload(user, permit, kind, state, label, files):
    found, error = permit_form._uploads(files, 'scan', permit_form.ID_EXTENSIONS)            # pylint: disable=protected-access
    if error:
        raise Invalid(error)
    if not found and not documents(permit, kind):
        raise Invalid(f'تصویر {label} را بارگذاری کنید.')
    if len(found) > MAX_FILES:
        raise Invalid(f'حداکثر {MAX_FILES} فایل می‌توانید بفرستید.')
    if found:
        _replace(permit, kind, found, user)
    was_returned = getattr(permit, state) == 'returned'
    setattr(permit, state, 'uploaded')
    return was_returned


def _announce(permit, user, label, was_returned):
    sr = permit.request
    if was_returned:
        lifecycle.permit_resubmitted(sr, user)
    else:
        sr.add_workflow_step(action=f'ارسال {label} توسط متقاضی (مرحله ۵)', from_user=user, to_role='engineer')
        sr.save(update_fields=['workflow_history', 'updated_at'])
    for staff in _staff(permit):
        notify(staff, label, f'متقاضی پرونده {permit.pk} {label} را فرستاد؛ منتظر تایید است.', request=sr)


@transaction.atomic
def upload_consent(user, permit, post, files):
    _owner_check(user, permit)
    if permit.consent_state not in ('', 'returned'):
        raise Conflict('تعهدنامه‌ی همسایگان قبلاً فرستاده شده است.')
    if post.get('signed') != 'on':
        raise Invalid('تیک «همسایگان فرم را امضا کرده‌اند» لازم است.')
    was_returned = _upload(user, permit, CONSENT_KIND, 'consent_state', 'تعهدنامه‌ی امضاشده‌ی همسایگان', files)
    commit = dict(permit.commit or {})
    commit['consent'] = {**(commit.get('consent') or {}), 'at': _now()}
    permit.commit = commit
    permit.save(update_fields=['commit', 'consent_state', 'updated_at'])
    _announce(permit, user, 'تعهدنامه‌ی رضایت همسایگان', was_returned)
    return permit


@transaction.atomic
def upload_deed(user, permit, post, files):
    _owner_check(user, permit)
    if permit.deed_state not in ('', 'returned'):
        raise Conflict('تعهد محضری قبلاً فرستاده شده است.')
    number = _clean(post.get('deed_no'), 40)
    date = permit_form._jalali(post.get('deed_date', ''))                 # pylint: disable=protected-access
    office = _clean(post.get('office'), 80)
    if not number or not office:
        raise Invalid('شماره‌ی سند و نام دفترخانه را وارد کنید.')
    if not date or date > permit_step2.today():
        raise Invalid('تاریخ سند را به شکل ۱۴۰۵/۰۶/۲۲ وارد کنید (نمی‌تواند در آینده باشد).')
    if post.get('delivered') != 'on':
        raise Invalid('تیک «اصل تعهد را به دهیاری تحویل داده‌ام» لازم است.')
    was_returned = _upload(user, permit, DEED_KIND, 'deed_state', 'تعهد محضری', files)
    commit = dict(permit.commit or {})
    commit['deed'] = {**(commit.get('deed') or {}), 'number': number, 'date': date, 'office': office, 'at': _now()}
    permit.commit = commit
    permit.save(update_fields=['commit', 'deed_state', 'updated_at'])
    _announce(permit, user, 'تعهد محضری', was_returned)
    return permit


PARTS = {'consent': ('consent_state', 'تعهدنامه‌ی رضایت همسایگان', 'تیک «امضای همسایگان را با فرم مقایسه و بررسی کردم» لازم است.'),
         'deed': ('deed_state', 'تعهد محضری', 'تیک «اصل تعهد محضری به دهیاری رسیده و با تصویر مطابق است» لازم است.')}


def _part(name):
    if name not in PARTS:
        raise Invalid('بخش نامعتبر است.')
    return PARTS[name]


@transaction.atomic
def verify(actor, permit, name, post):
    state, label, tick = _part(name)
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی تایید را ندارید.')
    if not at_step(permit) or getattr(permit, state) != 'uploaded':
        raise Conflict('مدرکی برای تایید نیست.')
    if post.get('confirm') != 'on':
        raise Invalid(tick)
    commit = dict(permit.commit or {})
    commit[name] = {**(commit.get(name) or {}), 'checked': {'by': actor.get_full_name() or actor.username, 'at': _now()}}
    permit.commit = commit
    setattr(permit, state, 'verified')
    permit.save(update_fields=['commit', state, 'updated_at'])
    notify(permit.request.user, f'{label} تایید شد', f'{label} پرونده {permit.pk} تایید شد.', request=permit.request)
    return permit


@transaction.atomic
def send_back(actor, permit, name, notes):
    state, label, _ = _part(name)
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی این کار را ندارید.')
    if not at_step(permit) or getattr(permit, state) != 'uploaded':
        raise Conflict('مدرکی برای برگرداندن نیست.')
    notes = (notes or '').strip()
    if not notes:
        raise Invalid('بنویسید مشکل مدرک چیست.')
    lifecycle.request_documents(permit.request, actor, f'{label}: {notes}')
    setattr(permit, state, 'returned')
    permit.staff_notes = notes[:2000]
    permit.save(update_fields=[state, 'staff_notes', 'updated_at'])
    return permit


def blocking(permit):
    out = []
    if permit.expert_state != 'introduced':
        out.append('مالک هنوز به کارشناس دادگستری معرفی نشده است.')
    if permit.consent_state != 'verified':
        out.append('تعهدنامه‌ی رضایت همسایگان هنوز تایید نشده است.')
    if permit.deed_state != 'verified':
        out.append('تعهد محضری هنوز تایید نشده است.')
    return out


@transaction.atomic
def finish(actor, permit, post):
    """Any of the three staff: the introduction is made and both papers are confirmed; the file goes on to step 6."""
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی تایید این مرحله را ندارید.')
    if not at_step(permit):
        raise Conflict('پرونده در مرحله‌ی تعهدات نیست.')
    waiting = blocking(permit)
    if waiting:
        raise Conflict(waiting[0])
    if post.get('confirm') != 'on':
        raise Invalid('تیک «مدارک این مرحله را بررسی کردم» لازم است.')
    permit.stage_no = 6
    permit.staff_notes = (post.get('notes') or '')[:2000]
    permit.save()
    sr = permit.request
    sr.add_workflow_step(action='تایید مرحله ۵ (معرفی به کارشناس دادگستری و تعهدات)', from_user=actor, to_role='citizen', notes=permit.staff_notes)
    sr.save(update_fields=['workflow_history', 'updated_at'])
    notify(sr.user, 'مرحله‌ی ۵ تایید شد', f'مرحله‌ی تعهدات پرونده {permit.pk} تایید شد؛ پرونده به مرحله‌ی ۶ رفت.', request=sr)
    return permit
