"""Building permit, step 4: the engineers, the plans, forms 04-07 and the dehyari's signature.

After the Bonyad's answer the owner has the plans drawn by an architect and a structural engineer (offices introduced by the
Bonyad and the engineers' organisation) and picks a supervising engineer. Forms 05 (structure), 06 (architecture) and 07
(supervision) are undertakings the engineers and the dehyari sign; form 04 is the dehyari's order to prepare the plans. The
system fills all four from what the file holds (the owner, the plot, the Bonyad's allowed floors and area, the four limits);
the owner prints them and collects the signatures on paper. The plans themselves are uploaded here (everything except the
signed forms). The clerk / expert / dehyari review the upload and the dehyari signs it: the system records who, when and a
fingerprint of every uploaded sheet, so a sheet changed afterwards is noticed.
"""
import hashlib

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from main.office import permit_request
from main import lifecycle
from main.access import can
from main.accounting.parse import digits
from main.models import PermitDocument
from main.notifications import notify
from main.office import permit_form, permit_step2, permits
from main.office.errors import Conflict, Forbidden, Invalid, NotFound
from main.office.permits import may_open

PLAN_KINDS = {'plan_arch': 'نقشه‌های معماری', 'plan_struct': 'نقشه‌های سازه', 'plan_other': 'نقشه‌های دیگر (تاسیسات و ...)'}
PLAN_EXTENSIONS = ('.pdf', '.jpg', '.jpeg', '.png', '.dwg', '.dxf')
MAX_PLAN_FILES = 150
ROLES = {'architect': 'مهندس طراح معماری', 'structure': 'مهندس محاسب سازه', 'supervisor': 'مهندس ناظر'}
PERSON_FIELDS = ('name', 'father', 'grade', 'field', 'license')
FORMS = ('f04', 'f05', 'f06', 'f07')
COMMON = ('owner', 'plot', 'lot', 'district', 'file_class', 'reg_no', 'floors', 'area', 'address')
KIND_OF_PERMIT = {'construction': 'construct', 'demolition': 'demolish', 'repair': 'repair'}
SIDES = ('north', 'south', 'east', 'west')
OPEN_STATES = ('', 'returned')


def _clean(value, limit=150):
    return ' '.join(str(value or '').split())[:limit]


def _num(value):
    text = digits(value).replace('٫', '.').replace(',', '.')
    try:
        number = float(text)
    except ValueError:
        return ''
    return int(number) if number == int(number) else round(number, 2)


def defaults(permit):
    """Everything the four forms need that the file already knows."""
    form1 = (permit.step2 or {}).get('form1') or {}
    form2 = (permit.step2 or {}).get('form2') or {}
    answer = permit.bonyad or {}
    owner = permit.people.first()
    village = permit_step2._village(permit)           # pylint: disable=protected-access
    limits = form1.get('limits') or {}
    floors, floor_area = answer.get('floors', ''), answer.get('floor_area', '')
    per_floor = round(float(floor_area) / float(floors), 2) if floors and floor_area else ''
    sides = {}
    for side in SIDES:
        lim = limits.get(side) or {}
        length = lim.get('length') or ''
        sides[side] = {'length': length, 'after': length, 'passage': 12 if lim.get('to') == 'معبر' else '', 'approved': 12 if lim.get('to') == 'معبر' else ''}
    first = permit_step2._next_number(village)        # pylint: disable=protected-access
    numbers, previous = {}, first
    for key in FORMS:
        numbers[key] = {'number': previous, 'date': permit_step2.today()}
        previous = permit_step2._next_number(village, after=previous)      # pylint: disable=protected-access
    return {
        'common': {'owner': owner.full_name, 'plot': permit.renewal_code or permit.lot_number, 'lot': permit.lot_number,
                   'district': permit.request.district.name if permit.request.district else '', 'file_class': str(permit.pk),
                   'reg_no': permit.registry_plot, 'floors': floors, 'area': floor_area,
                   'address': f'روستای {village}' + (f'، {permit.address}' if permit.address else '')},
        'people': {role: {field: '' for field in PERSON_FIELDS} for role in ROLES},
        'order': {
            'kind': KIND_OF_PERMIT.get(permit.permit_kind, 'construct'), 'basis': 'hadi', 'floors': floors, 'floor_area': per_floor,
            'area': f'{permit.area_m2:g}' if permit.area_m2 else '', 'asli': form2.get('asli', ''), 'fari': form2.get('fari', ''),
            'lease_no': permit.doc_number if permit.ownership_type == 'bonyad' else '',
            'lease_date': permit.doc_date if permit.ownership_type == 'bonyad' else '',
            'request_no': form1.get('request_no', ''), 'request_date': form1.get('request_date', ''), 'sides': sides,
        },
        'forms': numbers,
    }


def payload(permit):
    base, saved = defaults(permit), permit.design or {}
    merged = {}
    for key in ('common', 'people', 'order', 'forms'):
        part = base[key]
        for name, value in (saved.get(key) or {}).items():
            if isinstance(value, dict) and isinstance(part.get(name), dict):
                part[name] = {**part[name], **value}
            else:
                part[name] = value
        merged[key] = part
    merged['review'] = saved.get('review') or {}
    merged['signed'] = saved.get('signed') or {}
    return merged


def counts(permit):
    out = {kind: permit.documents.filter(kind=kind).count() for kind in PLAN_KINDS}
    out['total'] = sum(out.values())
    return out


def _editable_by_owner(permit, user):
    return permit.request.user_id == user.id and permit.stage_no == 4 and permit.design_state in OPEN_STATES


def _at_step(permit):
    if permit.stage_no != 4:
        raise Conflict('پرونده در مرحله‌ی نقشه‌ها نیست.')


@transaction.atomic
def save_people(actor, permit, post):
    """The engineers: the owner fills them in (staff may correct them until the dehyari signs)."""
    _at_step(permit)
    if not (_editable_by_owner(permit, actor) or (may_open(actor, permit) and permit.design_state != 'signed')):
        raise Forbidden('اجازه‌ی ویرایش مشخصات مهندسان را ندارید.')
    design = dict(permit.design or {})
    design['people'] = {role: {field: _clean(post.get(f'{role}_{field}', ''), 80) for field in PERSON_FIELDS} for role in ROLES}
    permit.design = design
    permit.save(update_fields=['design', 'updated_at'])
    return permit


@transaction.atomic
def save_forms(actor, permit, post):
    """The staff's part: form 04 (the order to prepare the plans) and the numbers and dates of forms 04-07."""
    if not may_open(actor, permit):
        raise Forbidden('فرم‌ها را کارکنان دهیاری پر می‌کنند.')
    _at_step(permit)
    if permit.design_state == 'signed':
        raise Conflict('نقشه‌ها امضا شده و دیگر قابل ویرایش نیست.')
    design = dict(permit.design or {})
    design['common'] = {key: _clean(post.get(f'c_{key}', ''), 200) for key in COMMON}
    order = {key: _clean(post.get(f'o_{key}', ''), 80) for key in ('floors', 'floor_area', 'area', 'asli', 'fari', 'lease_no', 'lease_date', 'request_no', 'request_date')}
    order['kind'] = post.get('o_kind') if post.get('o_kind') in ('construct', 'demolish', 'repair') else 'construct'
    order['basis'] = 'urf' if post.get('o_basis') == 'urf' else 'hadi'
    order['sides'] = {side: {key: _clean(post.get(f's_{side}_{key}', ''), 20) for key in ('length', 'after', 'passage', 'approved')} for side in SIDES}
    design['order'] = order
    design['forms'] = {key: {'number': _clean(post.get(f'{key}_number', ''), 40), 'date': _clean(post.get(f'{key}_date', ''), 12)} for key in FORMS}
    permit.design = design
    permit.save(update_fields=['design', 'updated_at'])
    return permit


def _digest(upload):
    sha = hashlib.sha256()
    for chunk in upload.chunks():
        sha.update(chunk)
    upload.seek(0)
    return sha.hexdigest()


@transaction.atomic
def upload_plans(user, permit, kind, uploads):
    if not _editable_by_owner(permit, user):
        raise Forbidden('الان نمی‌توانید نقشه بفرستید.')
    if kind not in PLAN_KINDS:
        raise Invalid('نوع نقشه نامعتبر است.')
    if not uploads:
        raise Invalid('فایلی انتخاب نشده است.')
    if permit.documents.filter(kind__in=PLAN_KINDS).count() + len(uploads) > MAX_PLAN_FILES:
        raise Invalid(f'حداکثر {MAX_PLAN_FILES} فایل نقشه می‌توانید بفرستید.')
    for upload in uploads:
        error = permit_form._file_error(upload, PLAN_EXTENSIONS, settings.MAX_FILE_SIZE)      # pylint: disable=protected-access
        if error:
            raise Invalid(error)
    design = dict(permit.design or {})
    hashes = dict(design.get('hashes') or {})
    for upload in uploads:
        digest = _digest(upload)
        doc = PermitDocument.objects.create(file=permit, kind=kind, document=upload, original_name=upload.name[:200], size=upload.size, uploaded_by=user)
        hashes[str(doc.pk)] = digest
    design['hashes'] = hashes
    permit.design = design
    permit.save(update_fields=['design', 'updated_at'])
    return len(uploads)


@transaction.atomic
def delete_plan(user, permit, doc_id):
    if not _editable_by_owner(permit, user):
        raise Forbidden('الان نمی‌توانید نقشه را حذف کنید.')
    doc = permit.documents.filter(pk=doc_id, kind__in=PLAN_KINDS).first()
    if doc is None:
        raise NotFound('نقشه پیدا نشد.')
    design = dict(permit.design or {})
    design.get('hashes', {}).pop(str(doc.pk), None)
    permit.design = design
    permit.save(update_fields=['design', 'updated_at'])
    doc.document.delete(save=False)
    doc.delete()


def _staff_to_tell(permit):
    return permits._staff_to_tell(permit_step2._village(permit))       # pylint: disable=protected-access


@transaction.atomic
def submit(user, permit):
    """The owner sends the plans for review."""
    if not _editable_by_owner(permit, user):
        raise Conflict('پرونده را نمی‌توان الان فرستاد.')
    people = payload(permit)['people']
    for role, label in ROLES.items():
        if not people[role]['name']:
            raise Invalid(f'نام {label} را وارد کنید.')
    have = counts(permit)
    if not have['plan_arch'] or not have['plan_struct']:
        raise Invalid('نقشه‌های معماری و سازه هر دو لازم است.')
    again = permit.design_state == 'returned'
    permit.design_state, permit.design_at = 'submitted', timezone.now()
    permit.save(update_fields=['design_state', 'design_at', 'updated_at'])
    sr = permit.request
    if again:
        permit_request.resubmitted(sr, user)
    else:
        sr.add_workflow_step(action='ارسال نقشه‌های معماری و سازه برای بررسی (مرحله ۴)', from_user=user, to_role='engineer')
        sr.save(update_fields=['workflow_history', 'updated_at'])
    for staff in _staff_to_tell(permit):
        notify(staff, 'نقشه‌های پرونده رسید', f'متقاضی نقشه‌های پرونده {permit.pk} را برای بررسی فرستاد.', request=sr)
    return permit


@transaction.atomic
def send_back(actor, permit, notes):
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی این کار را ندارید.')
    if permit.stage_no != 4 or permit.design_state not in ('submitted', 'reviewed'):
        raise Conflict('نقشه‌ای برای برگرداندن وجود ندارد.')
    notes = (notes or '').strip()
    if not notes:
        raise Invalid('بنویسید چه چیزی باید اصلاح شود.')
    permit_request.ask_for_documents(permit, actor, f'نقشه‌ها: {notes}')
    permit.design_state, permit.staff_notes = 'returned', notes[:2000]
    permit.save(update_fields=['design_state', 'staff_notes', 'updated_at'])
    return permit


def _checklist(post):
    ticks = {key: post.get(f'signed_{key}') == 'on' for key in ('f05', 'f06', 'f07')}
    if not all(ticks.values()):
        raise Invalid('رسیدن فرم‌های ۰۵، ۰۶ و ۰۷ با امضای مهندسان و دهیار را تیک بزنید.')
    return ticks


@transaction.atomic
def review(actor, permit, post):
    """Any of the staff: the plans are complete and the signed undertakings were received."""
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی بررسی نقشه‌ها را ندارید.')
    if permit.stage_no != 4 or permit.design_state != 'submitted':
        raise Conflict('نقشه‌ای برای بررسی وجود ندارد.')
    ticks = _checklist(post)
    design = dict(permit.design or {})
    design['review'] = {'forms': ticks, 'notes': _clean(post.get('notes', ''), 1000)}
    permit.design, permit.design_state = design, 'reviewed'
    permit.design_reviewed_at, permit.design_reviewed_by = timezone.now(), actor
    permit.save(update_fields=['design', 'design_state', 'design_reviewed_at', 'design_reviewed_by', 'updated_at'])
    sr = permit.request
    sr.add_workflow_step(action='بررسی نقشه‌ها و دریافت فرم‌های تعهد امضاشده', from_user=actor, to_role='dehyari', notes=design['review']['notes'])
    sr.save(update_fields=['workflow_history', 'updated_at'])
    for staff in _staff_to_tell(permit):
        if can(staff, 'permit.sign') and staff.pk != actor.pk:
            notify(staff, 'نقشه‌ها منتظر امضای شماست', f'نقشه‌های پرونده {permit.pk} بررسی شد.', request=sr)
    return permit


def fingerprint(permit):
    hashes = (permit.design or {}).get('hashes') or {}
    docs = permit.documents.filter(kind__in=PLAN_KINDS).order_by('pk')
    lines = [f'{doc.pk}:{doc.kind}:{hashes.get(str(doc.pk), "")}' for doc in docs]
    return hashlib.sha256('\n'.join(lines).encode()).hexdigest(), len(lines)


@transaction.atomic
def sign(actor, permit, post):
    """The dehyari signs the reviewed plans: step 4 is done. A dehyari who reviews and signs in one go ticks the list here."""
    if not (can(actor, 'permit.sign') and may_open(actor, permit)):
        raise Forbidden('امضای نقشه‌ها با دهیار است.')
    if permit.stage_no != 4 or permit.design_state not in ('submitted', 'reviewed'):
        raise Conflict('نقشه‌ای برای امضا وجود ندارد.')
    design = dict(permit.design or {})
    if permit.design_state == 'submitted':
        design['review'] = {'forms': _checklist(post), 'notes': _clean(post.get('notes', ''), 1000)}
        permit.design_reviewed_at, permit.design_reviewed_by = timezone.now(), actor
    digest, files = fingerprint(permit)
    design['signed'] = {'by': actor.get_full_name() or actor.username, 'at': timezone.localtime().strftime('%Y/%m/%d %H:%M'), 'sha256': digest, 'files': files}
    permit.design, permit.design_state, permit.stage_no = design, 'signed', 5
    permit.design_signed_at, permit.design_signed_by = timezone.now(), actor
    permit.save()
    sr = permit.request
    sr.add_workflow_step(action=f'امضای دهیار بر نقشه‌ها ({files} فایل) - پایان مرحله ۴', from_user=actor, to_role='citizen')
    sr.save(update_fields=['workflow_history', 'updated_at'])
    notify(sr.user, 'نقشه‌های شما امضا شد', 'دهیار نقشه‌های معماری و سازه‌ی پرونده را امضا کرد؛ پرونده به مرحله‌ی ۵ (عوارض) رفت.', request=sr)
    from main.office import permit_step5       # pylint: disable=import-outside-toplevel
    permit_step5.tell_the_officer(permit)
    return permit


def tampered(permit):
    """True when an uploaded sheet differs from what was signed (sheet added, removed or replaced)."""
    signed = (permit.design or {}).get('signed') or {}
    return bool(signed) and fingerprint(permit)[0] != signed.get('sha256')
