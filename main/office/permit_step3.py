"""Building permit, step 3: the Bonyad-e Maskan's answer, brought to the dehyari and checked there.

The owner takes the signed forms to the Bonyad and comes back with its answer (form الف۲-۱, «کارشناسی فنی صدور پروانه
ساختمانی»). The Bonyad has no access to this system, so the owner uploads the scan and types the key figures; the clerk,
the technical expert or the dehyari check the paper (its tracking code can be verified on the Bonyad's own site), see what
the system compared by itself, correct a figure if the owner mistyped it, and confirm the answer or send it back.
A confirmed answer moves the file to step 4 and is written on the plot of the village map.
"""
import math
import re

import jdatetime
from django.db import transaction
from django.utils import timezone

from main.office import permit_request
from main import lifecycle
from main.accounting.parse import digits
from main.models import ParcelArchive, PermitDocument, PermitFile
from main.notifications import notify
from main.office import geo, permit_form, permit_step2, permits
from main.office.errors import Conflict, Forbidden, Invalid, NotFound
from main.office.permits import may_open

TEXT = ('letter_no', 'tracking_code', 'request_ref', 'position', 'usage', 'permit_type')
NUMBERS = {                       # key: (label, minimum, maximum)
    'total_area': ('مساحت کل ملک', 0, 1_000_000), 'area_after': ('مساحت پس از رعایت کاربری و ابعاد اصلاحی', 0, 1_000_000),
    'occupancy_pct': ('درصد سطح اشغال', 0, 100), 'occupancy_m2': ('سطح اشغال (مترمربع)', 0, 1_000_000),
    'density_pct': ('تراکم (درصد)', 0, 1000), 'floor_area': ('مجموع زیربنای مجاز', 0, 1_000_000),
    'height_total': ('ارتفاع کل مجاز', 0, 100), 'height_base': ('ارتفاع کف ساختمان', 0, 100),
    'center_x': ('X مرکز ملک', 100_000, 900_000), 'center_y': ('Y مرکز ملک', 2_000_000, 5_000_000),
}
CENTRE_TOLERANCE_M = 25
AREA_TOLERANCE_PCT = 3
VERDICTS = {'allowed': 'مجاز', 'denied': 'غیرمجاز'}


def _number(raw):
    text = digits(raw).replace('٫', '.').replace(',', '.')
    return float(text)


def clean(post):
    """``(data, errors)`` from the answer form (the owner's and the staff's share it)."""
    data, errors = {}, {}
    for key in TEXT:
        data[key] = ' '.join(str(post.get(key, '')).split())[:120]
    data['tracking_code'] = re.sub(r'\D', '', digits(data['tracking_code']))
    data['letter_no'] = digits(data['letter_no'])
    data['request_ref'] = digits(data['request_ref'])
    for key, (label, low, high) in NUMBERS.items():
        raw = str(post.get(key, '')).strip()
        if not raw:
            data[key] = ''
            continue
        try:
            value = _number(raw)
            if not low <= value <= high:
                raise ValueError
            data[key] = round(value, 2)
        except ValueError:
            errors[key] = f'«{label}» را به‌صورت عدد درست وارد کنید.'
    raw = str(post.get('floors', '')).strip()
    data['floors'] = ''
    if raw:
        if digits(raw).isdigit() and 0 <= int(digits(raw)) <= 20:
            data['floors'] = int(digits(raw))
        else:
            errors['floors'] = 'تعداد طبقات را درست وارد کنید.'
    for key, label in (('letter_date', 'تاریخ نامه'), ('valid_until', 'تاریخ اعتبار')):
        raw = digits(post.get(key, ''))
        data[key] = ''
        if raw:
            data[key] = permit_form._jalali(raw) or ''         # pylint: disable=protected-access
            if not data[key]:
                errors[key] = f'{label} را به شکل ۱۴۰۴/۰۳/۲۰ وارد کنید.'
    data['verdict'] = post.get('verdict', '')
    if data['verdict'] not in VERDICTS:
        errors['verdict'] = 'نتیجه‌ی پاسخ (مجاز یا غیرمجاز) را انتخاب کنید.'
    for key, label in (('letter_no', 'شماره‌ی نامه'), ('tracking_code', 'کد رهگیری'), ('letter_date', 'تاریخ نامه')):
        if not data[key] and key not in errors:
            errors[key] = f'{label} را وارد کنید.'
    if data['tracking_code'] and not 8 <= len(data['tracking_code']) <= 30:
        errors['tracking_code'] = 'کد رهگیری را همان‌طور که بالای نامه آمده (فقط رقم) وارد کنید.'
    if data['verdict'] == 'allowed':
        for key, label in (('floors', 'تعداد طبقات'), ('floor_area', 'مجموع زیربنای مجاز'), ('occupancy_pct', 'درصد سطح اشغال')):
            if data.get(key) == '' and key not in errors:
                errors[key] = f'{label} را از نامه وارد کنید.'
    return data, errors


def _jdate(text):
    try:
        y, m, d = (int(p) for p in text.split('/'))
        return jdatetime.date(y, m, d)
    except (ValueError, AttributeError):
        return None


def _plot_centre(permit):
    """(lat, lng) of the file's plot: from the map when it is tied to one, else from the shamim outline."""
    village_map = permit_step2.village_map_of(permit)
    if permit.parcel_id and village_map:
        from main.office import plotmap
        grid, rows = plotmap.index(village_map)
        row = next((r for r in rows if r['id'] == permit.parcel_id), None)
        if row:
            x, y = geo.centroid(row['ring'])
            return grid.lat0 + y / grid.ky, grid.lng0 + x / grid.kx
    return None


def checks(permit):
    """What the system compared by itself: each is ok / warn / info with a sentence."""
    data = permit.bonyad or {}
    out = []

    def add(status, text):
        out.append({'status': status, 'text': text})
    form1 = ((permit.step2 or {}).get('form1') or {})
    ref, number = digits(data.get('request_ref', '')), digits(form1.get('number', ''))
    if not ref:
        add('info', 'شماره‌ی درخواست ذکرشده در نامه وارد نشده است.')
    elif ref == number:
        add('ok', f'شماره‌ی درخواست نامه ({data["request_ref"]}) همان شماره‌ی ثبت فرم ۱ این پرونده است.')
    else:
        add('warn', f'شماره‌ی درخواست نامه ({data["request_ref"]}) با شماره‌ی فرم ۱ این پرونده ({form1.get("number", "—")}) یکی نیست.')
    area, declared = data.get('total_area') or data.get('area_after'), float(permit.area_m2 or 0)
    if area and declared:
        diff = (float(area) - declared) / declared * 100
        add('ok' if abs(diff) <= AREA_TOLERANCE_PCT else 'warn',
            f'مساحت در نامه {area:g} م² و در پرونده {declared:g} م² است' + ('.' if abs(diff) <= AREA_TOLERANCE_PCT else f' ({abs(diff):.0f}٪ اختلاف).'))
    sent, requested = _jdate(data.get('letter_date', '')), _jdate(form1.get('date', ''))
    if sent and requested:
        add('ok' if sent >= requested else 'warn', 'نامه پس از تاریخ فرم ۱ صادر شده است.' if sent >= requested else 'تاریخ نامه پیش از تاریخ فرم ۱ است.')
    valid = _jdate(data.get('valid_until', ''))
    if valid:
        add('ok' if valid >= jdatetime.date.today() else 'warn', f'اعتبار پاسخ تا {data["valid_until"]} است.' if valid >= jdatetime.date.today() else f'اعتبار پاسخ از {data["valid_until"]} گذشته است.')
    code = data.get('tracking_code', '')
    if code:
        clash = PermitFile.objects.filter(bonyad__tracking_code=code).exclude(pk=permit.pk).exists()
        add('warn' if clash else 'ok', 'این کد رهگیری در پرونده‌ی دیگری هم استفاده شده است!' if clash else 'کد رهگیری تکراری نیست.')
    if data.get('center_x') and data.get('center_y'):
        centre = _plot_centre(permit)
        if centre:
            lat, lng = geo.utm_to_latlng(float(data['center_x']), float(data['center_y']))
            grid = geo.Grid(*centre)
            dx, dy = grid.to_xy(lat, lng)
            distance = math.hypot(dx, dy)
            add('ok' if distance <= CENTRE_TOLERANCE_M else 'warn',
                f'مرکز ملک در نامه {distance:.0f} متر با ملک این پرونده روی نقشه فاصله دارد.')
    if not permit.documents.filter(kind='bonyad_answer').exists():
        add('warn', 'تصویر نامه بارگذاری نشده است.')
    return out


def _answer_documents(permit):
    return permit.documents.filter(kind='bonyad_answer')


@transaction.atomic
def submit_answer(user, permit, post, files):
    """The owner uploads the Bonyad's answer and types its figures."""
    if permit.request.user_id != user.id:
        raise NotFound('پرونده پیدا نشد.')
    if permit.stage_no != 3 or permit.state != 'done':
        raise Conflict('پرونده در مرحله‌ی پاسخ بنیاد نیست.')
    if permit.bonyad_state not in ('', 'rejected'):
        raise Conflict('پاسخ بنیاد قبلاً فرستاده شده است.')
    uploads, error = permit_form._uploads(files, 'answer', permit_form.ID_EXTENSIONS)      # pylint: disable=protected-access
    if error:
        raise Invalid(error)
    if not uploads and not _answer_documents(permit).exists():
        raise Invalid('تصویر پاسخ بنیاد (همه‌ی صفحه‌ها) را بارگذاری کنید.')
    data, errors = clean(post)
    if errors:
        raise Invalid(next(iter(errors.values())))
    was_sent_back = permit.bonyad_state == 'rejected'
    for upload in uploads:
        PermitDocument.objects.create(file=permit, kind='bonyad_answer', document=upload, original_name=upload.name[:200],
                                      size=upload.size, uploaded_by=user)
    permit.bonyad, permit.bonyad_state, permit.bonyad_at = data, 'uploaded', timezone.now()
    permit.save(update_fields=['bonyad', 'bonyad_state', 'bonyad_at', 'updated_at'])
    sr = permit.request
    if was_sent_back:
        permit_request.resubmitted(sr, user)
    else:
        sr.add_workflow_step(action='ارسال پاسخ بنیاد مسکن توسط متقاضی (مرحله ۳)', from_user=user, to_role='engineer')
        sr.save(update_fields=['workflow_history', 'updated_at'])
    village = permit_step2._village(permit)          # pylint: disable=protected-access
    for staff in permits._staff_to_tell(village):    # pylint: disable=protected-access
        notify(staff, 'پاسخ بنیاد مسکن رسید', f'متقاضی پاسخ بنیاد را برای پرونده {permit.pk} فرستاد؛ منتظر تایید صحت است.', request=sr)
    return permit


def _sync_parcel(permit, actor):
    parcel = permit.parcel
    if parcel is None:
        return
    data = permit.bonyad
    archive, _ = ParcelArchive.objects.get_or_create(parcel=parcel)
    marker = f'پاسخ بنیاد پرونده {permit.pk}:'
    if marker not in archive.permit_notes:
        line = (f'{marker} {VERDICTS[data["verdict"]]} - نامه {data["letter_no"]} ({data["letter_date"]})'
                + (f' - {data["floors"]} طبقه، زیربنای مجاز {data["floor_area"]:g} م²' if data['verdict'] == 'allowed' else ''))
        archive.permit_notes = f'{archive.permit_notes}\n{line}'.strip()
    archive.updated_by = actor
    archive.save()


@transaction.atomic
def verify(actor, permit, post):
    """The staff confirm the answer is genuine (after checking its tracking code); the figures may be corrected."""
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی تایید این پاسخ را ندارید.')
    if permit.stage_no != 3 or permit.bonyad_state != 'uploaded':
        raise Conflict('پاسخی برای تایید وجود ندارد.')
    if post.get('confirm') != 'on':
        raise Invalid('تیک «صحت نامه و کد رهگیری را بررسی کردم» لازم است.')
    data, errors = clean(post)
    if errors:
        raise Invalid(next(iter(errors.values())))
    permit.bonyad = data
    permit.bonyad_checked_at, permit.bonyad_checked_by = timezone.now(), actor
    permit.staff_notes = (post.get('notes') or '')[:2000]
    sr = permit.request
    if data['verdict'] == 'denied':
        permit.bonyad_state, permit.state = 'verified', 'rejected'
        permit.save()
        permit_request.reject(permit, actor, f'پاسخ بنیاد مسکن (نامه {data["letter_no"]}) غیرمجاز است.')
        _sync_parcel(permit, actor)
        return permit
    permit.bonyad_state, permit.stage_no = 'verified', 4
    permit.save()
    sr.add_workflow_step(action=f'تایید صحت پاسخ بنیاد مسکن (کد رهگیری {data["tracking_code"]}) - پایان مرحله ۳', from_user=actor,
                         to_role='engineer', notes=permit.staff_notes)
    sr.save(update_fields=['workflow_history', 'updated_at'])
    notify(sr.user, 'پاسخ بنیاد مسکن تایید شد', f'دهیاری صحت پاسخ بنیاد (نامه {data["letter_no"]}) را تایید کرد؛ پرونده‌ی شما به مرحله‌ی ۴ رفت.', request=sr)
    _sync_parcel(permit, actor)
    return permit


@transaction.atomic
def send_back(actor, permit, notes):
    """The paper is unreadable or does not match: the owner uploads it again."""
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی این کار را ندارید.')
    if permit.stage_no != 3 or permit.bonyad_state != 'uploaded':
        raise Conflict('پاسخی برای برگرداندن وجود ندارد.')
    notes = (notes or '').strip()
    if not notes:
        raise Invalid('بنویسید مشکل پاسخ چیست.')
    permit_request.ask_for_documents(permit, actor, f'پاسخ بنیاد مسکن: {notes}')
    permit.bonyad_state, permit.staff_notes = 'rejected', notes[:2000]
    permit.save(update_fields=['bonyad_state', 'staff_notes', 'updated_at'])
    return permit
