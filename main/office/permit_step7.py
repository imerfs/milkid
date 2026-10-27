"""Building permit, step 7: the building permit form (پروانه ساختمان) the dehyari prints.

Once the Social Security certificate is confirmed the dehyari issues the permit. The system cannot sign or stamp it: the
dehyari and the supervising engineer sign and stamp the printed form by hand. What the system does is fill the three pages of
the form from everything the file holds (owner, plot, limits, the Bonyad's allowed figures, the engineers, the fee and
insurance slips) so the staff only check and change what differs, print it, and afterwards record that the permit was signed
and handed over. The owner is told what to do on paper.
"""
from django.db import transaction
from django.utils import timezone

from main.accounting.parse import digits
from main.models import Municipality, UserProfile
from main.notifications import notify
from main.office import permit_form, permit_step2, permit_step4, permits
from main.office.errors import Conflict, Forbidden, Invalid
from main.office.permits import may_open

SIDES = (('north', 'شمالاً'), ('south', 'جنوباً'), ('east', 'شرقاً'), ('west', 'غرباً'))
FLOORS = (('basement', 'زیرزمین'), ('ground', 'همکف'), ('mezz', 'نیم‌طبقه'), ('first', 'اول'), ('attic', 'خرپشته'))
FLOOR_FIELDS = (('count', 'تعداد'), ('area', 'مساحت (م²)'), ('height', 'ارتفاع (م)'), ('res', 'مسکونی (م²)'), ('other', 'سایر (م²)'))
SIDE_FIELDS = (('deed', 'ابعاد در سند'), ('actual', 'ابعاد موجود'), ('passage', 'عرض گذر'), ('after', 'پس از اصلاحی'))
CHOICES = {
    'ownership': (('public', 'بخش دولتی'), ('private', 'بخش خصوصی'), ('coop', 'بخش تعاونی')),
    'existing': (('', '—'), ('destroyed', 'ساختمان تخریبی'), ('new', 'ساختمان نوساز'), ('half', 'ساختمان نیمه‌تمام'), ('empty', 'زمین بایر')),
    'land': (('', '—'), ('trees', 'مشجر'), ('plain', 'غیر مشجر')),
    'usage': (('residential', 'مسکونی'), ('commercial', 'تجاری'), ('industrial', 'صنعتی'), ('health', 'بهداشتی و درمانی'),
              ('administrative', 'اداری'), ('other', 'سایر')),
    'position': (('', '—'), ('north', 'شمال'), ('south', 'جنوب'), ('east', 'شرق'), ('west', 'غرب')),
    'structure': (('', '—'), ('steel', 'فولادی'), ('concrete', 'بتنی'), ('brick', 'آجری'), ('bolt', 'پیچ و مهره')),
    'roof': (('', '—'), ('composite', 'کرمیت-کمپوزیت'), ('joist', 'تیرچه و بلوک'), ('rc', 'بتن آرمه'), ('other', 'سایر')),
    'energy': (('', '—'), ('1', 'ساختمان‌های با صرفه‌جویی انرژی زیاد'), ('2', 'ساختمان‌های با صرفه‌جویی انرژی قابل قبول'),
               ('3', 'ساختمان‌های با صرفه‌جویی انرژی متوسط'), ('4', 'ساختمان‌های بدون نیاز به صرفه‌جویی در مصرف انرژی')),
    'checklist': (('', '—'), ('yes', 'بلی'), ('no', 'خیر')),
    'material': (('', '—'), ('brick', 'آجر'), ('stone', 'سنگ'), ('cement', 'سیمان'), ('other', 'سایر')),
}
USAGE_OF = {'residential': 'residential', 'commercial': 'commercial', 'administrative': 'administrative', 'services': 'other'}
USAGE_WORDS = {'مسکونی': 'residential', 'تجاری': 'commercial', 'صنعتی': 'industrial', 'اداری': 'administrative', 'بهداشتی': 'health'}
POSITION_WORDS = {'شمال': 'north', 'جنوب': 'south', 'شرق': 'east', 'غرب': 'west'}
TEXT_KEYS = (
    'kind', 'permit_no', 'issue_date', 'fee_slip_no', 'fee_slip_date', 'entry_slip_no', 'entry_slip_date', 'ins_slip_no', 'ins_code',
    'finish_date', 'finish_year', 'registry_plot', 'section', 'lot', 'zone', 'owner', 'father', 'id_number', 'issued_at', 'national_id',
    'lawyer', 'lawyer_no', 'address', 'alley', 'plot_no', 'postal_code', 'sup_name', 'sup_license', 'sup_sign', 'calc_name', 'calc_license',
    'calc_sign', 'inst_name', 'inst_license', 'inst_sign', 'arch_name', 'arch_license', 'arch_sign', 'trees', 'deed_area', 'area_after',
    'density_pct', 'built_allowed', 'occupancy_m2', 'aerial_code', 'usage_other', 'material_other', 'parking', 'bonyad_ref', 'dehyari_name',
    'tech_name', 'notes_extra', 'trees_cut', 'fee_no_cut')
CHOICE_KEYS = ('ownership', 'existing', 'land', 'usage', 'position', 'structure', 'roof', 'energy', 'checklist', 'material')


def _clean(value, limit=120):
    return ' '.join(str(value or '').split())[:limit]


def _plain(number):
    if isinstance(number, float) and number == int(number):
        return int(number)
    return number


def _signers(village):
    muni = Municipality.objects.filter(city_village=village).select_related('admin_user').first()
    dehyari = (muni.admin_user.get_full_name() or '').strip() if muni and muni.admin_user else ''
    expert = UserProfile.objects.filter(role='engineer', city_village=village, is_active=True).select_related('user').first()
    return dehyari, (expert.user.get_full_name() or '').strip() if expert else ''


def defaults(permit):
    """Every field of the three pages that the file already knows."""
    village = permit_step2._village(permit)                      # pylint: disable=protected-access
    answer, owner = permit.bonyad or {}, permit.people.first()
    design = permit_step4.payload(permit)
    people, sides = design['people'], design['order']['sides']
    pays = [p for p in (permit.insurance or {}).get('payments') or [] if p.get('ok')]
    cert = (permit.insurance or {}).get('cert') or {}
    floors = int(answer.get('floors') or 0) or 1
    total = float(answer.get('floor_area') or 0)
    per = _plain(round(total / floors, 2)) if total else ''
    height = _plain(answer.get('height_base') or answer.get('height_total') or '')
    usage = USAGE_OF.get(permit.land_use) or next((v for k, v in USAGE_WORDS.items() if k in (answer.get('usage') or '')), 'residential')
    data = {
        'kind': dict(permit.LAND_USES).get(permit.land_use) or 'مسکونی',
        'permit_no': permit_step2._next_number(village),         # pylint: disable=protected-access
        'issue_date': permit_step2.today(),
        'fee_slip_no': pays[0]['slip_no'] if pays else '', 'fee_slip_date': pays[0]['date'] if pays else '',
        'ins_slip_no': cert.get('slip_no', ''), 'ins_code': cert.get('workshop_no', ''),
        'registry_plot': permit.registry_plot, 'lot': permit.lot_number,
        'owner': owner.full_name if owner else '', 'father': owner.father_name if owner else '',
        'id_number': owner.id_number if owner else '', 'issued_at': owner.birth_place if owner else '', 'national_id': owner.national_id if owner else '',
        'ownership': 'private', 'address': f'روستای {village}' + (f'، {permit.address}' if permit.address else ''), 'postal_code': permit.postal_code,
        'sup_name': people['supervisor']['name'], 'sup_license': people['supervisor']['license'],
        'calc_name': people['structure']['name'], 'calc_license': people['structure']['license'],
        'deed_area': '', 'area_after': _plain(answer.get('area_after') or answer.get('total_area') or (float(permit.area_m2) if permit.area_m2 else '')),
        'density_pct': _plain(answer.get('density_pct') or ''), 'built_allowed': _plain(answer.get('floor_area') or ''),
        'occupancy_m2': _plain(answer.get('occupancy_m2') or ''), 'usage': usage,
        'position': next((v for k, v in POSITION_WORDS.items() if k in (answer.get('position') or '')), ''),
        'bonyad_ref': (f'شماره‌ی مجوز احداث بنا از بنیاد مسکن انقلاب اسلامی {answer["letter_no"]} مورخ {answer["letter_date"]} می‌باشد.'
                       if answer.get('letter_no') else ''),
        'parking': 1 if usage == 'residential' else '',
    }
    data['dehyari_name'], data['tech_name'] = _signers(village)
    for side, _ in SIDES:
        lim = sides.get(side) or {}
        data[f'sd_{side}_actual'], data[f'sd_{side}_passage'], data[f'sd_{side}_after'] = lim.get('length', ''), lim.get('passage', ''), lim.get('after', '')
        data[f'sd_{side}_deed'] = ''
    for key, _ in FLOORS:
        row = {'count': '', 'area': '', 'height': '', 'res': '', 'other': ''}
        if key == 'ground' or (key == 'first' and floors >= 2):
            row = {'count': 1, 'area': per, 'height': height, 'res': per if usage == 'residential' else '', 'other': '' if usage == 'residential' else per}
        for field, _label in FLOOR_FIELDS:
            data[f'fl_{key}_{field}'] = row[field]
    return data


def payload(permit):
    """The defaults overridden by what the staff saved."""
    merged = defaults(permit)
    merged.update((permit.licence or {}).get('f') or {})
    return merged


def _valid_keys():
    keys = list(TEXT_KEYS) + list(CHOICE_KEYS)
    for side, _ in SIDES:
        keys += [f'sd_{side}_{f}' for f, _ in SIDE_FIELDS]
    for floor, _ in FLOORS:
        keys += [f'fl_{floor}_{f}' for f, _ in FLOOR_FIELDS]
    return keys


def _form_data(post):
    data = {}
    allowed = {key: {v for v, _ in CHOICES[key]} for key in CHOICE_KEYS}
    for key in _valid_keys():
        value = _clean(post.get(f'f_{key}', ''))
        if key in allowed and value not in allowed[key]:
            value = ''
        data[key] = value
    return data


def _step(permit):
    if permit.stage_no != 7:
        raise Conflict('پرونده در مرحله‌ی صدور پروانه نیست.')
    if permit.licence_state == 'issued':
        raise Conflict('پروانه صادر شده و دیگر قابل ویرایش نیست.')


@transaction.atomic
def save(actor, permit, post):
    if not may_open(actor, permit):
        raise Forbidden('فرم پروانه را کارکنان دهیاری پر می‌کنند.')
    _step(permit)
    saved = dict(permit.licence or {})
    saved['f'] = _form_data(post)
    permit.licence = saved
    permit.save(update_fields=['licence', 'updated_at'])
    return permit


@transaction.atomic
def issue(actor, permit, post):
    """The permit was signed and stamped by the dehyari and the supervisor and handed over: the file records it."""
    if not may_open(actor, permit):
        raise Forbidden('ثبت صدور پروانه با کارکنان دهیاری است.')
    _step(permit)
    data = _form_data(post)
    number = digits(data['permit_no'])
    if not number:
        raise Invalid('شماره‌ی پروانه را وارد کنید.')
    if post.get('signed') != 'on':
        raise Invalid('تیک «پروانه با مهر و امضای دهیار و ناظر به متقاضی تحویل شد» را بزنید.')
    if not permit_form._jalali(data['issue_date']):                  # pylint: disable=protected-access
        raise Invalid('تاریخ صدور را شمسی و درست وارد کنید.')
    data['issue_date'] = permit_form._jalali(data['issue_date'])     # pylint: disable=protected-access
    saved = dict(permit.licence or {})
    saved['f'] = data
    saved['issued'] = {'by': actor.get_full_name() or actor.username, 'at': timezone.localtime().strftime('%Y/%m/%d %H:%M')}
    permit.licence, permit.licence_state = saved, 'issued'
    permit.licence_at, permit.licence_by = timezone.now(), actor
    permit.save(update_fields=['licence', 'licence_state', 'licence_at', 'licence_by', 'updated_at'])
    sr = permit.request
    sr.add_workflow_step(action=f'صدور پروانه‌ی ساختمان شماره {data["permit_no"]} و تحویل به متقاضی', from_user=actor, to_role='citizen')
    sr.save(update_fields=['workflow_history', 'updated_at'])
    notify(sr.user, 'پروانه‌ی ساختمان شما صادر شد', f'پروانه‌ی ساختمان شماره {data["permit_no"]} صادر شد. پروانه را نگه دارید و پیش از شروع کار به ناظر فنی اطلاع دهید.', request=sr)
    return permit
