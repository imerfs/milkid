"""Reading the building-permit application (step 1, «ایجاد پرونده اولیه»): the form page posts here.

``parse(post, files)`` returns ``(data, errors)``. ``data`` holds the cleaned fields, the people (applicant first) and
the uploaded files by kind; ``errors`` maps a field name to a message, so the page can show it beside the field.
Nothing is saved here.
"""
import os
import re

import jdatetime
from django.conf import settings
from django.core.exceptions import ValidationError

from main.accounting.parse import digits
from main.models import CityVillage, County, Dehestan, District, PermitFile, Province
from main.validators import ALLOWED_MIMES, validate_file_content, validate_iranian_national_id

ID_EXTENSIONS = ('.pdf', '.jpg', '.jpeg', '.png')
SHAMIM_EXTENSIONS = ('.dwg', '.dxf', '.geojson', '.zip', '.kml')
MAX_FILES_PER_KIND = 8
CO_OWNERS = 3
OWNERSHIP_DOC = {'deed': 'deed', 'agreement': 'agreement', 'bonyad': 'bonyad_contract'}
OWNERSHIP_LABEL = {'deed': 'تصویر سند مالکیت', 'agreement': 'تصویر قولنامه', 'bonyad': 'تصویر قرارداد واگذاری بنیاد مسکن'}
CO_ROLES = ('co_owner', 'spouse', 'representative')
_PHONE = re.compile(r'^09\d{9}$')
_LOT = re.compile(r'^\d{1,6}$')
_CODE = re.compile(r'^\d{1,3}-\d{1,3}-\d{1,6}-\d{1,6}-\d{1,3}$')


def text(post, name, limit=200):
    return ' '.join(str(post.get(name, '')).split())[:limit]


def _jalali(value):
    """'1376/03/17' (any digits, / or -) -> that text normalised, or None when it is not a real Jalali date."""
    parts = re.split(r'[/\-.]', digits(value))
    try:
        year, month, day = (int(p) for p in parts)
        jdatetime.date(year, month, day)
    except (ValueError, TypeError):
        return None
    return f'{year:04d}/{month:02d}/{day:02d}'


def _file_error(upload, allowed, max_bytes):
    ext = os.path.splitext(upload.name)[1].lower()
    if ext not in allowed:
        return f'«{upload.name}»: فرمت مجاز نیست ({"، ".join(e[1:] for e in allowed)}).'
    if upload.size > max_bytes:
        return f'«{upload.name}»: حجم بیش از {max_bytes // (1024 * 1024)} مگابایت است.'
    if upload.size == 0:
        return f'«{upload.name}»: فایل خالی است.'
    if ext[1:] in ALLOWED_MIMES:          # zip / geojson / kml have no signature check; they are only ever sent back as downloads
        try:
            validate_file_content(upload)
        except ValidationError:
            return f'«{upload.name}»: محتوای فایل با پسوند آن نمی‌خواند.'
    return ''


def _uploads(files, name, allowed, max_bytes=None):
    """(uploads, error) for a file input that may hold several files."""
    uploads = files.getlist(name) if hasattr(files, 'getlist') else list(files.get(name, []))
    uploads = [u for u in uploads if u and u.name]
    if len(uploads) > MAX_FILES_PER_KIND:
        return [], f'حداکثر {MAX_FILES_PER_KIND} فایل می‌توانید بفرستید.'
    for upload in uploads:
        error = _file_error(upload, allowed, max_bytes or settings.MAX_FILE_SIZE)
        if error:
            return [], error
    return uploads, ''


def _national_id(value):
    value = digits(value)
    try:
        validate_iranian_national_id(value)
    except ValidationError as exc:
        return value, exc.messages[0]
    return value, ''


def _person(post, prefix, errors, role):
    """One person's fields; ``prefix`` is '' for the applicant and 'coN_' for the others."""
    person = {'role': role}
    for key, label, limit in (('first_name', 'نام', 60), ('last_name', 'نام خانوادگی', 80), ('father_name', 'نام پدر', 60)):
        person[key] = text(post, prefix + key, limit)
        if not person[key] and (role == 'applicant' or key != 'father_name'):
            errors[prefix + key] = f'{label} را وارد کنید.'
    person['national_id'], problem = _national_id(post.get(prefix + 'national_id', ''))
    if problem:
        errors[prefix + 'national_id'] = problem
    person['id_number'] = digits(post.get(prefix + 'id_number', ''))[:15]
    birth = digits(post.get(prefix + 'birth_date', ''))
    person['birth_date'] = ''
    if birth:
        person['birth_date'] = _jalali(birth) or ''
        if not person['birth_date']:
            errors[prefix + 'birth_date'] = 'تاریخ تولد را به شکل ۱۳۷۶/۰۳/۱۷ وارد کنید.'
    person['birth_place'] = text(post, prefix + 'birth_place', 80)
    return person


# What the owner tells about the building that already stands (construction without a permit)
BUILT_FIELDS = (('built_area', 'زیربنای ساخته‌شده (متر مربع)'), ('floors', 'تعداد طبقات'))


def _built(post, fields, errors):
    """The building that was put up without a permit: its built area, floors and (optionally) the year it was built."""
    try:
        built = float(digits(post.get('built_area', '')).replace('٫', '.').replace(',', '.'))
        if not 0 < built < 1_000_000:
            raise ValueError
        fields['details']['built_area'] = str(round(built, 2))
    except ValueError:
        errors['built_area'] = 'زیربنای ساخته‌شده را به متر مربع و به‌صورت عدد وارد کنید.'
    floors = digits(post.get('floors', ''))
    if floors.isdigit() and 1 <= int(floors) <= 30:
        fields['details']['floors'] = floors
    else:
        errors['floors'] = 'تعداد طبقات را به‌صورت عدد (۱ تا ۳۰) وارد کنید.'
    year = digits(post.get('built_year', ''))
    if year:
        if re.fullmatch(r'1[34]\d{2}', year):
            fields['details']['built_year'] = year
        else:
            errors['built_year'] = 'سال ساخت را به شکل ۱۳۹۵ وارد کنید.'
    note = text(post, 'built_note', 300)
    if note:
        fields['details']['built_note'] = note


def parse(post, files, track='permit'):
    unlicensed = track == 'unlicensed'
    errors = {}
    data = {'people': [], 'files': {}, 'track': track}

    applicant = _person(post, '', errors, 'applicant')
    if not applicant['birth_place']:
        errors['birth_place'] = 'محل صدور شناسنامه را وارد کنید.'
    phone = digits(post.get('phone', ''))
    if not _PHONE.match(phone):
        errors['phone'] = 'شماره موبایل را به شکل ۰۹۱۲۳۴۵۶۷۸۹ وارد کنید.'
    applicant['phone'] = phone
    applicant['email'] = text(post, 'email', 120)
    data['people'].append(applicant)

    # ---- the property
    fields = data['fields'] = {}
    for name in ('province', 'county', 'district', 'dehestan', 'city_village'):
        raw = digits(post.get(name, ''))
        model = {'province': Province, 'county': County, 'district': District, 'dehestan': Dehestan,
                 'city_village': CityVillage}[name]
        fields[name] = model.objects.filter(pk=raw).first() if raw.isdigit() else None
        if raw and fields[name] is None:
            errors[name] = 'مقدار انتخاب‌شده معتبر نیست.'
    postal = digits(post.get('postal_code', ''))
    fields['postal_code'] = postal
    if postal and not re.fullmatch(r'\d{10}', postal):
        errors['postal_code'] = 'کد پستی ۱۰ رقم است.'
    try:
        area = float(digits(post.get('area', '')).replace('٫', '.').replace(',', '.'))
        if not 0 < area < 10_000_000:
            raise ValueError
        fields['area_m2'] = round(area, 2)
    except ValueError:
        errors['area'] = 'مساحت را به متر مربع و به‌صورت عدد وارد کنید.'
    fields['land_use'] = post.get('land_use', '')
    if fields['land_use'] not in dict(PermitFile.LAND_USES):
        errors['land_use'] = 'نوع کاربری را انتخاب کنید.'
    fields['address'] = text(post, 'address', 500)
    if not fields['address']:
        errors['address'] = 'آدرس دقیق ملک را وارد کنید.'
    fields['permit_kind'] = 'construction' if unlicensed else post.get('permit_kind', '')
    if fields['permit_kind'] not in dict(PermitFile.KINDS):
        errors['permit_kind'] = 'نوع درخواست را انتخاب کنید.'

    # ---- the ownership paper
    ownership = post.get('ownership_type', '')
    fields['ownership_type'] = ownership
    if ownership not in OWNERSHIP_DOC:
        errors['ownership_type'] = 'وضعیت سند ملک را انتخاب کنید.'
    fields['doc_number'] = text(post, 'doc_number', 60)
    fields['doc_issuer'] = text(post, 'doc_issuer', 150)
    fields['project_code'] = digits(post.get('project_code', ''))[:40]
    fields['registry_plot'] = text(post, 'registry_plot', 60)
    fields['share_dang'] = digits(post.get('share_dang', ''))[:10]
    doc_date = digits(post.get('doc_date', ''))
    fields['doc_date'] = ''
    if doc_date:
        fields['doc_date'] = _jalali(doc_date) or ''
        if not fields['doc_date']:
            errors['doc_date'] = 'تاریخ را به شکل ۱۴۰۴/۰۳/۰۵ وارد کنید.'
    fields['lot_number'] = digits(post.get('lot_number', ''))
    if fields['lot_number'] and not _LOT.match(fields['lot_number']):
        errors['lot_number'] = 'شماره قطعه‌ی تفکیکی فقط عدد است.'
    code = '-'.join(re.split(r'[\s_/\\.\-]+', digits(post.get('renewal_code', '')))).strip('-')
    fields['renewal_code'] = code
    if code and not _CODE.match(code):
        errors['renewal_code'] = 'کد نوسازی را به شکل ۰-۰-۸-۱۸۲-۲ وارد کنید.'
    fields['details'] = {key: text(post, key, 120) for key in
                         ('limit_north', 'limit_south', 'limit_east', 'limit_west', 'lease_years', 'unit_count') if text(post, key, 120)}
    if unlicensed:
        _built(post, fields, errors)

    # ---- the other owners
    for n in range(1, CO_OWNERS + 1):
        prefix = f'co{n}_'
        filled = any(text(post, prefix + k) for k in ('first_name', 'last_name', 'father_name', 'national_id'))
        if not filled:
            continue
        role = post.get(prefix + 'role', 'co_owner')
        person = _person(post, prefix, errors, role if role in CO_ROLES else 'co_owner')
        person['prefix'] = prefix
        data['people'].append(person)

    # ---- papers
    wanted = [('', 'national_card', 'کارت ملی (پشت و رو)', True), ('', 'birth_cert', 'شناسنامه', True)]
    for person in data['people'][1:]:
        wanted.append((person['prefix'], 'national_card', f'کارت ملی {person["first_name"]} {person["last_name"]}', True))
        wanted.append((person['prefix'], 'birth_cert', f'شناسنامه {person["first_name"]} {person["last_name"]}', False))
    uploaded = data['files']
    for prefix, kind, label, required in wanted:
        name = f'{prefix}{kind}'
        found, error = _uploads(files, name, ID_EXTENSIONS)
        if error:
            errors[name] = error
        elif required and not found:
            errors[name] = f'{label} را بارگذاری کنید.'
        uploaded[name] = found

    if unlicensed and ownership == 'agreement':
        # the agreement (قولنامه) must go back to the first owner: the applicant ticks that it was
        if post.get('agreement_returned') == 'on':
            fields['details']['agreement_returned'] = 'yes'
        else:
            errors['agreement_returned'] = 'قولنامه باید به صاحب اول برگردد؛ تیک تایید لازم است.'
    if ownership in OWNERSHIP_DOC:
        name = OWNERSHIP_DOC[ownership]
        found, error = _uploads(files, name, ID_EXTENSIONS)
        if error:
            errors[name] = error
        elif not found:
            errors[name] = f'{OWNERSHIP_LABEL[ownership]} را بارگذاری کنید.'
        uploaded[name] = found
    found, error = _uploads(files, 'shamim', SHAMIM_EXTENSIONS)
    # without a shamim file the owner of an unlicensed building may ask the technical expert for a sketch (against a fee)
    sketch = unlicensed and not found and post.get('shamim_request') == 'on'
    if sketch:
        data['sketch_request'] = True
    if error:
        errors['shamim'] = error
    elif not found and not sketch:
        errors['shamim'] = 'فایل شمیم را بارگذاری کنید' + ('، یا درخواست کروکی بدهید.' if unlicensed else '.')
    elif len(found) > 1:
        errors['shamim'] = 'فقط یک فایل شمیم (در صورت چند فایل، به‌صورت zip) بفرستید.'
    uploaded['shamim'] = found

    if post.get('confirm') != 'on':
        errors['confirm'] = 'تأیید صحت اطلاعات و مدارک لازم است.'
    return data, errors


def keep_for_redisplay(post):
    """What the page shows again after an error (files cannot be kept; everything typed can)."""
    return {key: value for key, value in post.items() if key != 'csrfmiddlewaretoken'}
