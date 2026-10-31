"""Construction without a permit, step 4: the technical expert's visit report (گزارش بازدید), put in the owner's file.

After the visit the technical expert (or the dehyari) fills the report from what was seen and measured: the owner and the plot, the
four limits, the areas, the built floors (residential, commercial, parking, pilotis, storage, penthouse, overhang over the street and
over the yard), the occupation level and the parking. The system fills what the file already holds (owner, address, the limits measured
on the village map, the built area the owner gave) and works out the totals the sheet works out: the built area of each floor and in
all, the excess over the permit and the commission's ruling, the occupation percentage, the parking needed and the separation limit.
Filing the report puts it in the owner's file (he sees and prints it) and says whether the owner must now ask the electricity office
(an overhang over the street) and clear materials from the street (main/office/permit_site.py).
"""
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from main.access import can
from main.accounting.parse import digits
from main.notifications import notify
from main.office import permit_step2, permits, step_flow
from main.office.errors import Conflict, Forbidden, Invalid
from main.office.permits import may_open

SIDES = (('north', 'شمال'), ('east', 'شرق'), ('south', 'جنوب'), ('west', 'غرب'))
FLOORS = (('ground', 'همکف'), ('first', 'اول'), ('second', 'دوم'), ('third', 'سوم'))
FLOOR_FIELDS = ('units', 'res', 'commercial', 'parking', 'penthouse', 'overhang', 'pilotis', 'storage', 'height', 'over_yard', 'yard')
STATUSES = ('بهره‌برداری', 'در حال ساخت', 'نیمه‌کاره')
ROOFS = ('بتن', 'تیرچه بلوک', 'تیرآهن و طاق ضربی', 'سقف فلزی', 'چوب')
STRUCTURES = ('دیوار باربر', 'اسکلت فلزی', 'اسکلت بتنی', 'نیم‌اسکلت', 'بنایی')
MIN_SEPARABLE_M2 = 160          # a plot of 160 m² or more respects the separation limit (the sheet's «حد مجاز تفکیک»)
TWO_THIRDS = Decimal(2) / Decimal(3)


def _num(value, label='', maximum=1_000_000, allow_blank=True):
    text = digits(value).replace('٫', '.').replace(',', '.').strip()
    if not text:
        if allow_blank:
            return Decimal(0)
        raise Invalid(f'{label} را وارد کنید.')
    try:
        number = Decimal(text)
    except InvalidOperation:
        raise Invalid(f'{label or "مقدار"} را به‌صورت عدد وارد کنید.') from None
    if number < 0 or number > maximum:
        raise Invalid(f'{label or "مقدار"} معتبر نیست.')
    return number


def _text(value, limit=120):
    return step_flow.clean(value, limit)


def _fmt(number):
    number = Decimal(number)
    return str(int(number)) if number == number.to_integral() else str(number.quantize(Decimal('0.01')).normalize())


def may_fill(user, permit):
    """The technical expert and the dehyari of the file's village fill the report (any of the three staff confirm the rest)."""
    return can(user, 'permit.report') and permits.files_for(user).filter(pk=permit.pk).exists()


def find(user, file_id):
    permit = permits.find(user, file_id, any_track=True)
    return permit if permit is not None and permit.unlicensed else None


def at_step(permit):
    return permit.unlicensed and permit.stage_no == 4 and permit.state == 'done'


def _village(permit):
    return permit_step2._village(permit)               # pylint: disable=protected-access


def defaults(permit, actor=None):
    """Everything the file already knows, laid out as the report needs it."""
    owner = permit.people.first()
    details = permit.details or {}
    limits = permit_step2.limits_for(permit)
    built = Decimal(str(details.get('built_area') or 0))
    floors = int(details.get('floors') or 1)
    per_floor = (built / floors) if floors else built
    visit = permit.visit or {}
    base_floors = {}
    for index, (key, _) in enumerate(FLOORS):
        base_floors[key] = {f: '' for f in FLOOR_FIELDS}
        base_floors[key]['units'] = '1' if index < min(floors, 4) else '0'
        base_floors[key]['res'] = _fmt(per_floor) if index < min(floors, 4) and per_floor else ''
    return {
        'number': permit_step2._next_number(_village(permit)),           # pylint: disable=protected-access
        'date': permit_step2.today(), 'visit_date': (visit.get('date') or visit.get('preferred_date') or ''),
        'name': owner.full_name, 'father': owner.father_name, 'national_id': owner.national_id, 'phone': owner.phone,
        'land_use': permit.get_land_use_display() if permit.land_use else '',
        'status': STATUSES[0], 'address': f'{permit.address}' if permit.address else f'روستای {_village(permit)}',
        'utm_x': '', 'utm_y': '',
        'permit_area': '0', 'permit_date': '', 'permit_no': '', 'ruling_area': '0', 'ruling_date': '', 'ruling_no': '',
        'year': '', 'roof': ROOFS[0], 'structure': STRUCTURES[0],
        'limits': {side: {'adjacent': (limits.get(side) or {}).get('to') or '', 'existing': _fmt((limits.get(side) or {}).get('length') or 0),
                          'passage': '0', 'after': _fmt((limits.get(side) or {}).get('length') or 0)} for side, _ in SIDES},
        'deed_area': _fmt(permit.area_m2 or 0), 'existing_area': _fmt(permit.area_m2 or 0), 'after_area': _fmt(permit.area_m2 or 0),
        'parking_provided': '0', 'floors': base_floors,
        'overhang_built': True, 'overhang_rows': {side: {'passage': '', 'sidewalk': '', 'balcony': '', 'network': ''} for side, _ in SIDES},
        'materials': False, 'materials_note': '', 'notes': '',
        'signer': (actor.get_full_name() or actor.username) if actor is not None else '',
    }


def data(permit, actor=None):
    base = defaults(permit, actor)
    saved = permit.report or {}
    merged = {**base, **{k: v for k, v in saved.items() if k in base and k not in ('limits', 'floors', 'overhang_rows')}}
    merged['limits'] = {side: {**base['limits'][side], **((saved.get('limits') or {}).get(side) or {})} for side, _ in SIDES}
    merged['floors'] = {key: {**base['floors'][key], **((saved.get('floors') or {}).get(key) or {})} for key, _ in FLOORS}
    merged['overhang_rows'] = {side: {**base['overhang_rows'][side], **((saved.get('overhang_rows') or {}).get(side) or {})} for side, _ in SIDES}
    return merged


def totals(values):
    """The sums the sheet works out (all of them from the numbers typed in the report)."""
    per_floor, total, units = {}, Decimal(0), 0
    overhang_passage = Decimal(0)
    for key, _ in FLOORS:
        f = {name: _num(values['floors'][key].get(name, '')) for name in FLOOR_FIELDS}
        residential = f['res'] + f['over_yard'] * TWO_THIRDS + f['yard']          # 2/3 of an overhang closed on two or three sides, the small yard
        amount = residential + f['commercial'] + f['parking'] + f['pilotis'] + f['storage'] + f['penthouse'] + f['overhang']
        per_floor[key] = {'residential': residential, 'total': amount}
        total += amount
        units += int(f['units'])
        overhang_passage += f['overhang']
    existing = _num(values.get('existing_area', ''))
    ground = per_floor['ground']['total']
    excess = total - _num(values.get('permit_area', '')) - _num(values.get('ruling_area', ''))
    return {'floors': per_floor, 'total': total, 'excess': excess, 'units': units, 'overhang_passage': overhang_passage,
            'occupation': (ground * 100 / existing) if existing else Decimal(0),
            'separation_ok': existing >= MIN_SEPARABLE_M2, 'parking_needed': units}


def needs_power(values):
    """True when the building has an overhang over the street (the sheet's column «پیش‌آمدگی به معبر»)."""
    return sum(_num(values['floors'][key].get('overhang', '')) for key, _ in FLOORS) > 0


def clean(post):
    """The report as the technical expert filled it: returns the stored dict (raises Invalid on the first bad number)."""
    out = {key: _text(post.get(key, ''), 200) for key in ('number', 'visit_date', 'name', 'father', 'national_id', 'phone', 'land_use', 'status',
                                                          'address', 'utm_x', 'utm_y', 'permit_date', 'permit_no', 'ruling_date', 'ruling_no', 'year',
                                                          'roof', 'structure', 'materials_note', 'notes', 'signer')}
    out['date'] = _text(post.get('date', ''), 10)
    from main.office import permit_form             # pylint: disable=import-outside-toplevel
    jalali = permit_form._jalali(out['date'])           # pylint: disable=protected-access
    if not jalali:
        raise Invalid('تاریخ گزارش را به شکل ۱۴۰۵/۰۶/۲۲ وارد کنید.')
    out['date'] = jalali
    if not out['name']:
        raise Invalid('نام مالک را وارد کنید.')
    for key, label in (('permit_area', 'مساحت با پروانه'), ('ruling_area', 'مساحت رأی کمیسیون'), ('deed_area', 'مساحت طبق سند'),
                       ('existing_area', 'مساحت وضع موجود'), ('after_area', 'مساحت پس از رعایت برهای اصلاحی'), ('parking_provided', 'پارکینگ تأمین‌شده')):
        out[key] = _fmt(_num(post.get(key, ''), label))
    out['limits'] = {side: {'adjacent': _text(post.get(f'{side}_adjacent', ''), 60),
                            'existing': _fmt(_num(post.get(f'{side}_existing', ''), f'ابعاد موجود {label}')),
                            'passage': _fmt(_num(post.get(f'{side}_passage', ''), f'عرض معبر {label}')),
                            'after': _fmt(_num(post.get(f'{side}_after', ''), f'ابعاد پس از اصلاح {label}'))} for side, label in SIDES}
    out['floors'] = {}
    for key, label in FLOORS:
        row = {}
        for name in FLOOR_FIELDS:
            row[name] = _fmt(_num(post.get(f'{key}_{name}', ''), f'{name} طبقه‌ی {label}', maximum=100_000))
        out['floors'][key] = row
    out['overhang_built'] = post.get('overhang_built', 'built') == 'built'
    out['overhang_rows'] = {side: {name: _fmt(_num(post.get(f'oh_{side}_{name}', ''), f'پیش‌آمدگی {label}')) if post.get(f'oh_{side}_{name}', '').strip() else ''
                                   for name in ('passage', 'sidewalk', 'balcony', 'network')} for side, label in SIDES}
    out['materials'] = post.get('materials') == 'on'
    if totals(out)['total'] <= 0:
        raise Invalid('زیربنای هیچ طبقه‌ای وارد نشده است.')
    return out


def _gate(actor, permit):
    if not may_fill(actor, permit):
        raise Forbidden('گزارش بازدید را کارشناس فنی (یا دهیار) پر می‌کند.')
    if not at_step(permit):
        raise Conflict('پرونده در مرحله‌ی گزارش بازدید نیست.')


@transaction.atomic
def save(actor, permit, post):
    """Keep the report as a draft (the owner does not see it yet)."""
    _gate(actor, permit)
    permit.report = clean(post)
    permit.save(update_fields=['report', 'updated_at'])
    return permit


@transaction.atomic
def file_report(actor, permit, post):
    """Put the report in the owner's file; say what the owner must still do (electricity office, materials)."""
    _gate(actor, permit)
    values = clean(post)
    permit.report = values
    permit.report_state, permit.report_at = 'filed', timezone.now()
    power, materials = needs_power(values), bool(values['materials'])
    if power and permit.overhang_state in ('', 'returned'):
        permit.overhang_state = 'required' if permit.overhang_state == '' else permit.overhang_state
    elif not power and permit.overhang_state != 'verified':
        permit.overhang_state = ''
    if materials and permit.materials_state == '':
        permit.materials_state = 'required'
    elif not materials and permit.materials_state != 'verified':
        permit.materials_state = ''
    permit.save()
    sr = permit.request
    sr.add_workflow_step(action=f'ثبت گزارش بازدید کارشناس فنی (شماره {values["number"]}) در پرونده - مرحله ۴', from_user=actor, to_role='citizen')
    sr.save(update_fields=['workflow_history', 'updated_at'])
    todo = []
    if power:
        todo.append('درخواست مجوز پیش‌آمدگی از اداره برق')
    if materials:
        todo.append('جمع‌آوری مصالح از معبر و بارگذاری عکس')
    notify(sr.user, 'گزارش بازدید در پرونده‌ی شما است', f'گزارش بازدید پرونده {permit.pk} ثبت شد.' + (' کارهای لازم: ' + ' و '.join(todo) + '.' if todo else ''), request=sr)
    return permit
