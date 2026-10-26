"""Building permit, step 2: the two forms and the plot map, filled in by the system.

* **Form 1** (استعلام ضوابط ساخت و ساز, to the Bonyad-e Maskan) is filled in by the village staff (clerk, expert or
  dehyari): the owner's identity, the plot, its four limits measured from the village map, the registration number.
  The plot's map is attached to it as a second page.
* **Form 2** (تقاضای صدور پروانه ساختمان روستایی) is filled in by the owner, from what the file already holds.

The owner downloads both (the page draws them over the blank forms, ``static/forms/permit``), has the dehyari sign and
stamp form 1, signs form 2 and takes them to the Bonyad; the Bonyad has no access to this system. When the staff mark the
signed forms as handed over, the file moves on to step 3.
"""
import re

import jdatetime
from django.db import transaction
from django.db.models import Q
from django.templatetags.static import static
from django.utils import timezone

from main import lifecycle
from main.accounting.parse import digits
from main.models import MapParcel, PermitFile, VillageMap
from main.notifications import notify
from main.office import geo, plotmap
from main.office.errors import Conflict, Forbidden, Invalid, NotFound
from main.office.permits import may_open

PURPOSES = {'construction': 'احداث بنا', 'repair': 'تعمیر و مرمت', 'demolition': 'تخریب و نوسازی'}
DIRS = ('north', 'south', 'west', 'east')
_NUMBER = re.compile(r'^(\d+)/(\d+)$')


def today():
    return jdatetime.date.today().strftime('%Y/%m/%d')


def _village(permit):
    sr = permit.request
    profile = getattr(sr.user, 'profile', None)
    return (sr.city_village.name if sr.city_village else '') or (getattr(profile, 'city_village', '') or '')


def village_map_of(permit):
    if permit.parcel_id:
        return permit.parcel.village_map
    return VillageMap.objects.filter(name=_village(permit)).first()


def limits_for(permit):
    """The four limits: measured on the village map when the file is tied to a plot, else from the shamim outline."""
    village_map = village_map_of(permit)
    found = {}
    if permit.parcel_id and village_map:
        found = plotmap.limits(village_map, parcel_id=permit.parcel_id)
    elif permit.shamim_info.get('outline'):
        ring = [tuple(p) for p in permit.shamim_info['outline']]
        sums = {}
        for edge in geo.edges(ring):
            sums[edge['side']] = sums.get(edge['side'], 0.0) + edge['length']
        found = {side: {'length': round(sums.get(side, 0.0), 2), 'to': ''} for side in DIRS}
    details = permit.details or {}
    for side in DIRS:       # what the owner wrote from the contract fills the sides the map could not name
        written = details.get(f'limit_{side}', '')
        entry = found.setdefault(side, {'length': 0.0, 'to': ''})
        if written and not entry.get('to'):
            entry['to'] = written
    return {side: found.get(side, {'length': 0.0, 'to': ''}) for side in DIRS}


def sheet_for(permit):
    village_map = village_map_of(permit)
    if permit.parcel_id and village_map:
        return plotmap.sheet(village_map, parcel_id=permit.parcel_id)
    outline = permit.shamim_info.get('outline')
    if outline:
        ring = [tuple(p) for p in outline]
        return {'plot': outline, 'neighbours': [], 'area': round(geo.area(ring), 2),
                'edges': [{'a': list(e['a']), 'b': list(e['b']), 'length': round(e['length'], 2)} for e in geo.edges(ring)]}
    return None


def _next_number(village, after=None):
    """The next registration number in the village's own pattern («18/1836»), or a year/serial one when it is the first."""
    prefix, serial = '', -1
    here = Q(request__city_village__name=village) | Q(request__city_village__isnull=True, request__user__profile__city_village=village)
    seen = [((f.step2 or {}).get(key) or {}).get('number', '') for f in PermitFile.objects.filter(here).exclude(step2={})
            for key in ('form1', 'form2')]
    for text in seen + ([after] if after else []):
        m = _NUMBER.match(text or '')
        if m and int(m.group(2)) > serial:
            prefix, serial = m.group(1), int(m.group(2))
    if serial >= 0:
        return f'{prefix}/{serial + 1}'
    return f'{jdatetime.date.today().year}/1'


def _registry(permit):
    text = permit.registry_plot or ''
    m = re.search(r'(\d+)\s*(?:فرعی)\s*از\s*(\d+)', digits(text))
    return {'plot': '', 'asli': m.group(2), 'fari': m.group(1)} if m else {'plot': digits(text), 'asli': '', 'fari': ''}


def form2_defaults(permit):
    sr = permit.request
    person = permit.people.first()
    profile = getattr(sr.user, 'profile', None)
    registry = _registry(permit)
    details = permit.details or {}
    docs = permit.documents
    lessor = permit.doc_issuer or 'بنیاد مسکن انقلاب اسلامی'
    return {
        'number': '', 'date': today(),
        'name': person.full_name, 'father': person.father_name, 'id_number': person.id_number, 'issued_at': person.birth_place,
        'village': _village(permit), 'dehestan': details.get('dehestan') or (getattr(profile, 'dehestan_name', '') or ''),
        'district': sr.district.name if sr.district else (getattr(profile, 'district', '') or ''),
        'area': f'{permit.area_m2:g}' if permit.area_m2 else '', 'purpose': permit.permit_kind,
        'ownership': permit.ownership_type,
        'section': '', 'plot': registry['plot'], 'qate': permit.lot_number, 'asli': registry['asli'], 'fari': registry['fari'],
        'exact_address': permit.address,
        'lease_no': permit.doc_number if permit.ownership_type == 'bonyad' else '',
        'lessor': lessor if permit.ownership_type == 'bonyad' else '',
        'lease_date': permit.doc_date if permit.ownership_type == 'bonyad' else '',
        'rep_name': '', 'rep_father': '', 'rep_id': '', 'rep_issued': '',
        'attach1': docs.filter(kind='birth_cert').exists(), 'attach2': True,
        'attach3': permit.ownership_type == 'agreement', 'attach4': False,
    }


def form1_defaults(permit):
    sr = permit.request
    person = permit.people.first()
    profile = getattr(sr.user, 'profile', None)
    village = _village(permit)
    saved2 = (permit.step2 or {}).get('form2') or {}
    number = _next_number(village)
    return {
        'number': number, 'date': today(),
        'bonyad_city': sr.county.name if sr.county else (getattr(profile, 'county', '') or ''),
        'request_no': saved2.get('number') or _next_number(village, after=number), 'request_date': saved2.get('date') or today(),
        'name': person.full_name, 'father': person.father_name, 'id_number': person.id_number, 'issued_at': person.birth_place,
        'national_id': person.national_id, 'wakalat_no': '',
        'plot': (permit.registry_plot or ''), 'area': f'{permit.area_m2:g}' if permit.area_m2 else '',
        'village': village, 'district': sr.district.name if sr.district else (getattr(profile, 'district', '') or ''),
        'county': sr.county.name if sr.county else (getattr(profile, 'county', '') or ''),
        'address': f'روستای {village}' + (f'، قطعه {permit.lot_number}' if permit.lot_number else '') + (f'، {permit.address}' if permit.address else ''),
        'limits': limits_for(permit),
    }


def _clean_text(value, limit=200):
    return ' '.join(str(value or '').split())[:limit]


FORM1_TEXT = ('number', 'date', 'bonyad_city', 'request_no', 'request_date', 'name', 'father', 'id_number', 'issued_at',
              'national_id', 'wakalat_no', 'plot', 'area', 'village', 'district', 'county', 'address')
FORM2_TEXT = ('name', 'father', 'id_number', 'issued_at', 'village', 'dehestan', 'district', 'area', 'section', 'plot', 'qate',
              'asli', 'fari', 'exact_address', 'lease_no', 'lessor', 'lease_date', 'rep_name', 'rep_father', 'rep_id', 'rep_issued')


def _merged(permit, key, defaults):
    return {**defaults, **((permit.step2 or {}).get(key) or {})}


def payload(permit):
    """Everything the forms page draws."""
    form1 = _merged(permit, 'form1', form1_defaults(permit))
    form2 = _merged(permit, 'form2', form2_defaults(permit))
    return {
        'form1': form1, 'form2': form2, 'sheet': sheet_for(permit),
        'form1_saved': bool(permit.form1_at), 'form2_saved': bool(permit.form2_at), 'delivered': bool(permit.delivered_at),
        'purposes': PURPOSES, 'file': permit.pk, 'plot_label': permit.lot_number or (permit.parcel.number if permit.parcel_id else ''),
        'renewal_code': permit.renewal_code, 'blank': {'form1': static('forms/permit/form1_blank.jpg'), 'form2': static('forms/permit/form2_blank.jpg')},
    }


def _numbers(post, name):
    try:
        return round(float(digits(post.get(name, '')).replace('٫', '.').replace(',', '.')), 2)
    except ValueError:
        return 0.0


@transaction.atomic
def save_form1(actor, permit, post):
    """The staff fill in form 1."""
    if not may_open(actor, permit):
        raise Forbidden('فرم ۱ را کارکنان دهیاری پر می‌کنند.')
    if permit.stage_no != 2 or permit.delivered_at:
        raise Conflict('پرونده در مرحله‌ی فرم‌ها نیست.')
    data = {key: _clean_text(post.get(key, '')) for key in FORM1_TEXT}
    if not data['number'] or not data['date']:
        raise Invalid('شماره ثبت و تاریخ فرم ۱ را وارد کنید.')
    data['limits'] = {side: {'length': _numbers(post, f'{side}_length'), 'to': _clean_text(post.get(f'{side}_to', ''), 80)} for side in DIRS}
    steps = dict(permit.step2 or {})
    steps['form1'] = data
    if data['request_no']:                         # the owner's request is registered in the dehyari under this number
        form2 = dict(steps.get('form2') or {})
        form2['number'], form2['date'] = data['request_no'], data['request_date'] or today()
        steps['form2'] = form2
    permit.step2, permit.form1_at = steps, timezone.now()
    permit.save(update_fields=['step2', 'form1_at', 'updated_at'])
    notify(permit.request.user, 'فرم ۱ پرونده‌ی شما آماده شد',
           'فرم استعلام (فرم ۱) و نقشه‌ی ملک شما آماده است؛ از صفحه‌ی پرونده دانلود و برای مهر و امضا به دهیاری بیاورید.', request=permit.request)
    return permit


@transaction.atomic
def save_form2(user, permit, post):
    """The owner fills in form 2."""
    if permit.request.user_id != user.id:
        raise NotFound('پرونده پیدا نشد.')
    if permit.stage_no != 2 or permit.delivered_at:
        raise Conflict('پرونده در مرحله‌ی فرم‌ها نیست.')
    data = {key: _clean_text(post.get(key, '')) for key in FORM2_TEXT}
    for key in ('name', 'father', 'village'):
        if not data[key]:
            raise Invalid('نام، نام پدر و روستا را وارد کنید.')
    data['purpose'] = post.get('purpose') if post.get('purpose') in PURPOSES else 'construction'
    data['ownership'] = post.get('ownership') if post.get('ownership') in ('deed', 'agreement', 'bonyad') else permit.ownership_type
    for n in range(1, 5):
        data[f'attach{n}'] = post.get(f'attach{n}') == 'on'
    steps = dict(permit.step2 or {})
    saved = steps.get('form2') or {}
    data['number'], data['date'] = saved.get('number', ''), saved.get('date', '') or today()     # the dehyari's registration, not the owner's
    steps['form2'] = data
    permit.step2, permit.form2_at = steps, timezone.now()
    permit.save(update_fields=['step2', 'form2_at', 'updated_at'])
    return permit


@transaction.atomic
def deliver(actor, permit):
    """The signed forms were handed to the owner: step 2 is done."""
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی این کار را ندارید.')
    if permit.stage_no != 2 or permit.delivered_at:
        raise Conflict('پرونده در مرحله‌ی فرم‌ها نیست.')
    if not (permit.form1_at and permit.form2_at):
        raise Conflict('هر دو فرم باید پر شده باشد.')
    permit.delivered_at, permit.stage_no = timezone.now(), 3
    permit.save(update_fields=['delivered_at', 'stage_no', 'updated_at'])
    sr = permit.request
    sr.add_workflow_step(action='تحویل فرم‌های ۱ و ۲ مهر و امضاشده به متقاضی (پایان مرحله ۲)', from_user=actor, to_role='citizen')
    sr.save(update_fields=['workflow_history', 'updated_at'])
    notify(sr.user, 'فرم‌ها مهر و امضا شد', 'فرم‌های ۱ و ۲ شما مهر و امضا و تحویل شد؛ آن‌ها را به بنیاد مسکن ببرید. '
           'پاسخ بنیاد مرحله‌ی بعد پرونده است.', request=sr)
    return permit


def refresh_shamim(permit):
    """Read the stored shamim file again and keep the result on the file."""
    from main.office import shamim
    doc = permit.documents.filter(kind='shamim').order_by('-id').first()
    if doc is None:
        permit.shamim_info = {'ok': False, 'notes': ['فایل شمیم بارگذاری نشده است.'], 'matches': []}
    else:
        with doc.document.open('rb') as handle:
            data = handle.read(80 * 1024 * 1024)
        info = shamim.analyse(doc.original_name, data, permit.area_m2, village_map_of(permit))
        permit.shamim_info = info
    permit.save(update_fields=['shamim_info', 'updated_at'])
    return permit.shamim_info


def parcel_choices(permit):
    """Plots of the map the clerk can pick for the renewal code: from the shamim outline first, then by lot number."""
    out, seen = [], set()
    for m in permit.shamim_info.get('matches', []):
        if m['parcel_id'] not in seen:
            seen.add(m['parcel_id'])
            out.append({'id': m['parcel_id'], 'code': m['code'], 'block': m['block'], 'number': m['number'], 'source': 'shamim'})
    if permit.lot_number:
        for p in MapParcel.objects.filter(lot_no=permit.lot_number)[:6]:
            if p.pk not in seen:
                seen.add(p.pk)
                out.append({'id': p.pk, 'code': p.renewal_code, 'block': p.block_no, 'number': p.number, 'source': 'lot'})
    areas = dict(MapParcel.objects.filter(pk__in=seen).values_list('pk', 'area_m2'))
    for row in out:
        row['area'] = round(areas.get(row['id'], 0))
    return out
