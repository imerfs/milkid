"""The building-permit file, step 1 (افتتاح پرونده): filing it, who sees it, and how the staff open it.

The applicant files with identity papers, a paper that proves ownership (deed, agreement or a Bonyad-e Maskan contract)
and the shamim file. The clerk (or the technical expert, or the dehyari) checks them, gives the renewal code the shamim
file leads to, and opens the file; that also writes the owner and the permit onto the plot of the village map. What the
applicant typed stays in the profile, so the next application starts filled in.
"""
from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from main import lifecycle
from main.accounting.parse import jalali_str
from main.access import can, role_of
from main.gis import locks
from main.models import (MapParcel, Municipality, ParcelArchive, PermitDocument, PermitFile, PermitPerson, ServiceRequest,
                         UserProfile)
from main.models_permit import STAGES
from main.notifications import notify
from main.office import permit_form
from main.office.directory import requests_for, village_of
from main.office.errors import Conflict, Forbidden, Invalid, NotFound
from main.office.roles import is_admin

BONYAD_NAME = 'بنیاد مسکن انقلاب اسلامی'
FILE_STAFF = ('clerk', 'engineer', 'dehyari')


# ---------- the applicant ----------

def prefill(user):
    """What the site already knows about ``user``, for the application form."""
    profile = getattr(user, 'profile', None)

    def get(name):
        return (getattr(profile, name, '') or '') if profile is not None else ''
    return {
        'first_name': user.first_name, 'last_name': user.last_name, 'father_name': get('father_name'),
        'national_id': get('national_id'), 'id_number': get('id_number'), 'birth_date': get('birth_date'),
        'birth_place': get('birth_place'), 'phone': get('mobile_number'), 'email': user.email,
        'postal_code': get('postal_code'), 'address': get('address'),
    }


def _remember(user, applicant):
    """Keep what the applicant typed in the profile (the next application and the staff's view of the person)."""
    User.objects.filter(pk=user.pk).update(first_name=applicant['first_name'], last_name=applicant['last_name'],
                                           **({'email': applicant['email']} if applicant['email'] and not user.email else {}))
    changes = {'father_name': applicant['father_name'], 'id_number': applicant['id_number'],
               'birth_date': applicant['birth_date'], 'birth_place': applicant['birth_place']}
    profile = user.profile
    if not profile.mobile_number and applicant['phone']:
        changes['mobile_number'] = applicant['phone']
    if not profile.national_id and applicant['national_id']:
        if not UserProfile.objects.filter(national_id=applicant['national_id']).exclude(pk=profile.pk).exists():
            changes['national_id'] = applicant['national_id']
    UserProfile.objects.filter(pk=profile.pk).update(**{k: v for k, v in changes.items() if v})


def _save_documents(permit, uploads_by_name, people_by_prefix, actor):
    for name, uploads in uploads_by_name.items():
        prefix = name[:4] if name.startswith('co') and name[3:4] == '_' else ''
        kind = name[len(prefix):]
        owner = people_by_prefix.get(prefix) if kind in ('national_card', 'birth_cert') else None   # the property's papers are no one's
        for upload in uploads:
            PermitDocument.objects.create(file=permit, person=owner, kind=kind, document=upload,
                                          original_name=upload.name[:200], size=upload.size, uploaded_by=actor)


def _staff_to_tell(village):
    users = list(User.objects.filter(is_active=True, profile__role__in=('clerk', 'engineer'), profile__city_village=village))
    users += [m.admin_user for m in Municipality.objects.filter(city_village=village).select_related('admin_user') if m.admin_user]
    return {u.pk: u for u in users}.values()


@transaction.atomic
def submit(user, data):
    """File the application. ``data`` is what ``permit_form.parse`` returned without errors."""
    fields, applicant = data['fields'], data['people'][0]
    kind_label = dict(PermitFile.KINDS)[fields['permit_kind']]
    geography = {name: fields[name] for name in ('province', 'county', 'district', 'city_village') if fields.get(name)}
    sr = lifecycle.submit(
        user, action='ثبت درخواست پروانه ساختمان (مرحله ۱: افتتاح پرونده) توسط متقاضی - ارجاع به کارشناس',
        request_type='building_permit', title=f'درخواست {kind_label}',
        description=f'{kind_label} - مساحت {fields["area_m2"]} مترمربع - {fields["address"]}',
        property_address=fields['address'], property_area=fields['area_m2'],
        property_usage=dict(PermitFile.LAND_USES)[fields['land_use']], deed_number=fields['doc_number'],
        parcel_number=fields['renewal_code'], form_data={'permit': True, 'ownership_type': fields['ownership_type']},
        **geography)
    permit = PermitFile.objects.create(
        request=sr, permit_kind=fields['permit_kind'], ownership_type=fields['ownership_type'],
        doc_number=fields['doc_number'], doc_date=fields['doc_date'], doc_issuer=fields['doc_issuer'],
        project_code=fields['project_code'], registry_plot=fields['registry_plot'], lot_number=fields['lot_number'],
        share_dang=fields['share_dang'], area_m2=fields['area_m2'], land_use=fields['land_use'],
        address=fields['address'], postal_code=fields['postal_code'],
        details={**fields['details'], **({'dehestan': fields['dehestan'].name} if fields.get('dehestan') else {})})
    people = {}
    for order, person in enumerate(data['people']):
        row = PermitPerson.objects.create(
            file=permit, user=user if order == 0 else None, order=order, role=person['role'],
            first_name=person['first_name'], last_name=person['last_name'], father_name=person['father_name'],
            national_id=person['national_id'], id_number=person['id_number'], birth_date=person['birth_date'],
            birth_place=person['birth_place'], phone=person.get('phone', ''), email=person.get('email', ''))
        people[person.get('prefix', '')] = row
    _save_documents(permit, data['files'], people, user)
    _remember(user, applicant)
    try:
        from main.office import permit_step2
        permit_step2.refresh_shamim(permit)           # the clerk finds the plot of the map already suggested
    except Exception:                                 # pylint: disable=broad-except   # reading the drawing must never lose an application
        pass
    village = (sr.city_village.name if sr.city_village else '') or village_of(user)
    for staff in _staff_to_tell(village):
        notify(staff, 'پرونده‌ی پروانه ساختمان تازه', f'{applicant["first_name"]} {applicant["last_name"]} پرونده‌ی پروانه '
               f'ساختمان ثبت کرد و منتظر افتتاح پرونده است (کد پرونده {permit.pk}).', request=sr)
    return permit


def supplement(user, permit, kind, uploads):
    """The applicant adds papers after the staff sent the file back."""
    if permit.request.user_id != user.id:
        raise NotFound('پرونده پیدا نشد.')
    if permit.state != 'needs_docs':
        raise Conflict('این پرونده در حال حاضر نیازی به مدارک تازه ندارد.')
    if kind not in dict(PermitDocument.KINDS):
        raise Invalid('نوع مدرک نامعتبر است.')
    allowed = permit_form.SHAMIM_EXTENSIONS if kind == 'shamim' else permit_form.ID_EXTENSIONS
    for upload in uploads:
        error = permit_form._file_error(upload, allowed, settings.MAX_FILE_SIZE)    # pylint: disable=protected-access
        if error:
            raise Invalid(error)
    if not uploads:
        raise Invalid('فایلی انتخاب نشده است.')
    with transaction.atomic():
        for upload in uploads:
            PermitDocument.objects.create(file=permit, kind=kind, document=upload, original_name=upload.name[:200],
                                          size=upload.size, uploaded_by=user)
        permit.state = 'submitted'
        permit.save(update_fields=['state', 'updated_at'])
        lifecycle.permit_resubmitted(permit.request, user)
    for staff in _staff_to_tell((permit.request.city_village.name if permit.request.city_village else '') or village_of(user)):
        notify(staff, 'مدارک تازه‌ی پرونده', f'متقاضی مدارک پرونده {permit.pk} را دوباره فرستاد.', request=permit.request)


# ---------- who sees what ----------

def files_for(user):
    """The permit files the staff member may open: those of their village (an admin sees all)."""
    rows = PermitFile.objects.select_related('request', 'request__user', 'request__user__profile', 'parcel', 'opened_by')
    if is_admin(user):
        return rows
    village = village_of(user)
    if not village:
        return rows.none()
    return rows.filter(request__in=ServiceRequest.objects.filter(requests_for(village)))


def find(user, file_id):
    """The file if ``user`` is its owner or the village's staff, else None."""
    rows = PermitFile.objects.select_related('request', 'request__user', 'request__user__profile', 'parcel', 'opened_by')
    permit = rows.filter(pk=file_id).first()
    if permit is None:
        return None
    if permit.request.user_id == user.id:
        return permit
    if role_of(user) == 'inspector':             # the technical supervisor sees the files he was linked to, not the village's
        return permit if permit.supervisor_id == user.id else None
    if can(user, 'permit.view') and files_for(user).filter(pk=file_id).exists():
        return permit
    return None


def may_open(user, permit):
    return can(user, 'permit.open') and files_for(user).filter(pk=permit.pk).exists()


def tracker(permit):
    """The nine steps with where the file is: done / current / waiting."""
    rows = []
    for number, title in STAGES:
        done = number < permit.stage_no or (number == 9 and permit.stage_no == 9 and permit.endwork_state == 'issued')
        state = 'done' if done else 'current' if number == permit.stage_no else 'todo'
        rows.append({'no': number, 'title': title, 'state': state})
    return rows


# ---------- the staff ----------

def suggestions(permit):
    """Plots of the village map the shamim outline / lot number points to (the clerk still decides)."""
    from main.office import permit_step2
    return permit_step2.parcel_choices(permit)


def parcels_for_code(code):
    return list(MapParcel.objects.filter(renewal_code=code))


def _fill_blank(archive, **values):
    for name, value in values.items():
        if value and not getattr(archive, name):
            setattr(archive, name, value)


def sync_parcel(permit, actor):
    """Write the owner and the permit onto the plot of the village map (blanks only: staff's own entries stay)."""
    parcel = permit.parcel
    if parcel is None:
        return
    person = permit.people.first()
    archive, _ = ParcelArchive.objects.get_or_create(parcel=parcel)
    _fill_blank(archive, building_owner_name=person.full_name, building_owner_national_id=person.national_id,
                building_owner_phone=person.phone)
    if permit.ownership_type == 'bonyad':
        _fill_blank(archive, owner_name=BONYAD_NAME)
    else:
        _fill_blank(archive, owner_name=person.full_name, owner_national_id=person.national_id, owner_phone=person.phone)
    line = f'پرونده پروانه {permit.pk}: {permit.get_permit_kind_display()} - {person.full_name} - در جریان'
    if f'پرونده پروانه {permit.pk}:' not in archive.permit_notes:
        archive.permit_notes = f'{archive.permit_notes}\n{line}'.strip()
    archive.updated_by = actor
    archive.save()
    if permit.lot_number and not parcel.lot_no:
        parcel.lot_no = permit.lot_number
        parcel.save(update_fields=['lot_no'])


@transaction.atomic
def open_file(actor, permit, *, code, parcel_id=None, notes=''):
    """Step 1 done: the file gets its renewal code (and its plot of the map) and moves to step 2."""
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی افتتاح این پرونده را ندارید.')
    if permit.state != 'submitted':
        raise Conflict('این پرونده در حال بررسی نیست؛ مدارک تازه یا تصمیم قبلی را بررسی کنید.')
    code = '-'.join(permit_form.digits(code).replace('_', ' ').replace('/', ' ').replace('.', ' ').replace('-', ' ').split())
    if not permit_form._CODE.match(code):          # pylint: disable=protected-access
        raise Invalid('کد نوسازی را به شکل «صنف-آپارتمان-ملک-بلوک-محله» مثل ۰-۰-۸-۱۸۲-۲ وارد کنید.')
    refusal = locks.refusal(code)
    if refusal:
        raise Conflict(refusal)
    found = parcels_for_code(code)
    parcel = None
    if found:
        chosen = [p for p in found if str(p.pk) == str(parcel_id)]
        if len(found) > 1 and not chosen:
            raise Invalid('این کد برای چند قطعه‌ی نقشه ثبت شده است؛ قطعه‌ی درست را انتخاب کنید.')
        parcel = chosen[0] if chosen else found[0]
    permit.renewal_code, permit.parcel = code, parcel
    permit.state, permit.stage_no = 'done', 2
    permit.opened_by, permit.opened_at, permit.staff_notes = actor, timezone.now(), notes[:2000]
    permit.save()
    lifecycle.permit_opened(permit.request, actor, code=code, notes=notes)
    sync_parcel(permit, actor)
    return permit


def send_back(actor, permit, notes):
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی بررسی این پرونده را ندارید.')
    if permit.state != 'submitted':
        raise Conflict('این پرونده در حال بررسی نیست.')
    notes = (notes or '').strip()
    if not notes:
        raise Invalid('بنویسید چه مدرکی ناقص است.')
    with transaction.atomic():
        lifecycle.request_documents(permit.request, actor, notes)
        permit.state, permit.staff_notes = 'needs_docs', notes[:2000]
        permit.save(update_fields=['state', 'staff_notes', 'updated_at'])


def refuse(actor, permit, reason):
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی بررسی این پرونده را ندارید.')
    if permit.state not in ('submitted', 'needs_docs'):
        raise Conflict('این پرونده قابل رد کردن نیست.')
    reason = (reason or '').strip()
    if not reason:
        raise Invalid('دلیل رد را بنویسید.')
    with transaction.atomic():
        lifecycle.reject(permit.request, actor, reason)
        permit.state, permit.staff_notes = 'rejected', reason[:2000]
        permit.save(update_fields=['state', 'staff_notes', 'updated_at'])


# ---------- what the panels and the map show ----------

def panel_rows(user, limit=60):
    rows = files_for(user).filter(request__request_type='building_permit')
    listed = list(rows[:300])
    ordered = sorted(listed, key=lambda f: (not f.needs_staff, -f.created_at.timestamp()))[:limit]
    return {'rows': ordered, 'waiting': sum(1 for f in listed if f.needs_staff), 'total': rows.count(), 'can_open': can(user, 'permit.open')}


def fee_rows_for(user, limit=60):
    """The financial officer's list: files in step 5 waiting for fees, and files in step 6 with a payment to confirm."""
    rows = [f for f in files_for(user).filter(request__request_type='building_permit', stage_no__in=(5, 6))[:300]]
    todo = [f for f in rows if f.needs_accountant or (f.stage_no == 6 and not f.insurance_state
                                                      and any(not p.get('ok') for p in (f.insurance or {}).get('payments') or []))]
    ordered = sorted(rows, key=lambda f: (f not in todo, -f.created_at.timestamp()))[:limit]
    return {'rows': ordered, 'waiting': len(todo)}


def applicant_history(permit):
    """Other files and requests of the same person, for the staff's view of the applicant."""
    owner = permit.request.user
    return ServiceRequest.objects.filter(user=owner).exclude(pk=permit.request_id).order_by('-created_at')[:8]


def parcel_requests(parcel):
    """Everything filed for a plot: the permit files and any other request that names its renewal code."""
    code = parcel.renewal_code
    files = PermitFile.objects.filter(parcel=parcel) | (PermitFile.objects.filter(renewal_code=code) if code else PermitFile.objects.none())
    rows = []
    for f in files.distinct().select_related('request', 'request__user').prefetch_related('people'):
        applicant = next(iter(f.people.all()), None)
        rows.append({'kind': 'permit', 'id': f.pk, 'title': f.request.title, 'who': applicant.full_name if applicant else
                     f.request.user.get_full_name(), 'status': f.request.get_status_display(), 'stage': f.stage_title,
                     'state': f.get_state_display(), 'date': jalali_str(f.created_at.date()), 'at': f.created_at,
                     'url': reverse('main:permit_file', args=[f.pk])})
    others = ServiceRequest.objects.filter(parcel_number=code).exclude(permit_file__isnull=False).select_related('user') if code else []
    for r in others:
        rows.append({'kind': 'request', 'id': r.pk, 'title': r.title, 'who': r.user.get_full_name() or r.user.username,
                     'status': r.get_status_display(), 'stage': '', 'state': '', 'date': jalali_str(r.created_at.date()), 'at': r.created_at, 'url': ''})
    rows.sort(key=lambda r: r['at'], reverse=True)
    for row in rows:
        del row['at']
    return rows
