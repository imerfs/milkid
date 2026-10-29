"""Construction without a permit, step 1: the owner's defence form (فرم ارائه دفاعیات و توضیحات ذینفع یا نماینده قانونی متخلف ساختمانی).

The form goes to the members of the Article 99 commission. The system fills it from the file (the owner, the village, the built area from
the filing); the owner may change the values and writes the explanation of why the building was put up without a permit, prints it, signs
and leaves a fingerprint, takes it to the dehyari for the confirmation box at the bottom, and uploads the scan. Step 1 cannot be confirmed
by the staff (clerk / technical expert / dehyari) before that scan is there.
"""
from django.db import transaction

from main.models import Municipality, PermitDocument
from main.notifications import notify
from main.office import permit_form, permit_step2, permits
from main.office.errors import Conflict, Forbidden, Invalid, NotFound
from main.office.permits import may_open

KIND = 'defence_form'
FIELDS = ('name', 'father', 'phone', 'village', 'district', 'county', 'area', 'status', 'explanation', 'date', 'dehyari')
STATUSES = {'without': 'بدون اخذ پروانه', 'over': 'مازاد بر پروانه'}
SUGGESTIONS = ('از موارد قانونی اطلاعی نداشتم.', 'توان مالی پرداخت هزینه‌های جریمه و دهیاری را نداشتم.')
OPEN_STATES = ('submitted', 'needs_docs')
MAX_SCANS = 6


def _clean(value, limit=150):
    return ' '.join(str(value or '').split())[:limit]


def find(user, file_id):
    permit = permits.find(user, file_id, any_track=True)
    return permit if permit is not None and permit.unlicensed else None


def at_step(permit):
    return permit.unlicensed and permit.stage_no == 1 and permit.state in OPEN_STATES


def _dehyari_name(permit):
    village = permit_step2._village(permit)         # pylint: disable=protected-access
    muni = Municipality.objects.filter(city_village=village).first()
    return (muni.manager_name if muni else '') or ''


def defaults(permit):
    owner = permit.people.first()
    request = permit.request
    return {'name': owner.full_name, 'father': owner.father_name, 'phone': owner.phone,
            'village': permit_step2._village(permit),         # pylint: disable=protected-access
            'district': request.district.name if request.district else '', 'county': request.county.name if request.county else '',
            'area': (permit.details or {}).get('built_area', ''), 'status': 'without', 'explanation': '',
            'date': permit_step2.today(), 'dehyari': _dehyari_name(permit)}


def payload(permit):
    form = {**defaults(permit), **{k: v for k, v in (permit.defence or {}).items() if k in FIELDS}}
    return {'form': form, 'file': permit.pk, 'statuses': STATUSES}


def scans(permit):
    return list(permit.documents.filter(kind=KIND))


def _may_edit(actor, permit):
    owner_open = permit.request.user_id == actor.id
    return at_step(permit) and (owner_open or may_open(actor, permit))


@transaction.atomic
def save_form(actor, permit, post):
    """The values printed on the form (the owner corrects them; the staff may for a walk-in owner)."""
    if not at_step(permit):
        raise Conflict('پرونده در مرحله‌ی فرم دفاعیه نیست.')
    if not _may_edit(actor, permit):
        raise Forbidden('اجازه‌ی ویرایش این فرم را ندارید.')
    values = {key: _clean(post.get(key, ''), 150) for key in FIELDS}
    values['explanation'] = ' '.join(str(post.get('explanation', '')).split())[:450]
    values['phone'] = permit_form.digits(values['phone'])[:11]
    if values['phone'] and not permit_form._PHONE.match(values['phone']):          # pylint: disable=protected-access
        raise Invalid('شماره تماس را به شکل ۰۹۱۲۳۴۵۶۷۸۹ وارد کنید.')
    if not values['name']:
        raise Invalid('نام و نام خانوادگی را وارد کنید.')
    if values['status'] not in STATUSES:
        raise Invalid('بدون اخذ پروانه یا مازاد بر پروانه را انتخاب کنید.')
    values['area'] = permit_form.digits(values['area']).replace('٫', '.').replace(',', '.')
    try:
        if values['area'] and not 0 < float(values['area']) < 1_000_000:
            raise ValueError
    except ValueError:
        raise Invalid('متراژ بنا را به متر مربع و به‌صورت عدد وارد کنید.') from None
    date = permit_form._jalali(values['date'])              # pylint: disable=protected-access
    if not date:
        raise Invalid('تاریخ را به شکل ۱۴۰۵/۰۶/۲۲ وارد کنید.')
    values['date'] = date
    permit.defence = values
    permit.save(update_fields=['defence', 'updated_at'])
    return permit


@transaction.atomic
def upload(user, permit, files):
    """The owner uploads the scan of the signed form (every page); a new upload replaces the old one."""
    if permit.request.user_id != user.id:
        raise NotFound('پرونده پیدا نشد.')
    if not at_step(permit):
        raise Conflict('پرونده در مرحله‌ی فرم دفاعیه نیست.')
    found, error = permit_form._uploads(files, 'scan', permit_form.ID_EXTENSIONS)          # pylint: disable=protected-access
    if error:
        raise Invalid(error)
    if not found:
        raise Invalid('تصویر فرم دفاعیه‌ی امضاشده را انتخاب کنید.')
    if len(found) > MAX_SCANS:
        raise Invalid(f'حداکثر {MAX_SCANS} فایل می‌توانید بفرستید.')
    for old in scans(permit):
        old.document.delete(save=False)
        old.delete()
    for scan in found:
        PermitDocument.objects.create(file=permit, kind=KIND, document=scan, original_name=scan.name[:200], size=scan.size, uploaded_by=user)
    for staff in permits._staff_to_tell(permit_step2._village(permit)):       # pylint: disable=protected-access
        notify(staff, 'فرم دفاعیه رسید', f'متقاضی فرم دفاعیه‌ی امضاشده‌ی پرونده {permit.pk} را فرستاد.', request=permit.request)
    return permit
