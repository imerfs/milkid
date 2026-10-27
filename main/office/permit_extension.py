"""Building permit renewal (تمدید مهلت پروانه): a permit lasts one year from its issue date.

A year after the issue date (or after the previous renewal ends) the owner must renew it; at most two renewals («نوبت اول /
دوم») exist on the paper form. The owner asks with the «فرم درخواست» (signed and fingerprinted on paper), the clerk / expert /
dehyari fill the renewal form from the file, print both, and the dehyari and the technical manager (the technical expert) sign
and stamp the renewal by hand. The system keeps the dates: when the permit expires, the renewal terms, who issued each one.
"""
import jdatetime
from django.db import transaction
from django.utils import timezone

from main.accounting.parse import digits
from main.models import PermitFile
from main.notifications import notify
from main.office import permit_form, permit_step2, permit_step7, permits
from main.office.errors import Conflict, Forbidden, Invalid
from main.office.permits import may_open

MAX_RENEWALS = 2
SOON_DAYS = 30
TERMS = {1: 'نوبت اول', 2: 'نوبت دوم'}
REQUEST_KEYS = ('name', 'father', 'id_number', 'address', 'phone', 'request_no', 'request_date')
FORM_KEYS = ('number', 'date', 'village', 'section', 'code', 'fee_slip_no', 'finish_date', 'ins_slip_no', 'owner', 'registry_plot',
             'from_date', 'period', 'dehyari_name', 'tech_name')


def _clean(value, limit=120):
    return ' '.join(str(value or '').split())[:limit]


def _jd(text):
    parts = permit_form._jalali(text)             # pylint: disable=protected-access
    return jdatetime.date(*(int(p) for p in parts.split('/'))) if parts else None


def _plus_years(day, years):
    try:
        return day.replace(year=day.year + years)
    except ValueError:                              # 30 Esfand of a leap year
        return day.replace(year=day.year + years, day=day.day - 1)


def _fmt(day):
    return day.strftime('%Y/%m/%d')


def issued_extensions(permit):
    return [e for e in permit.extensions or [] if e.get('state') == 'issued']


def open_extension(permit):
    return next((e for e in permit.extensions or [] if e.get('state') == 'requested'), None)


def expiry(permit):
    """``{'date', 'days', 'state'}``: when the permit's current term ends (state valid / soon / expired); None while no permit was issued."""
    if permit.licence_state != 'issued':
        return None
    issue = _jd(((permit.licence or {}).get('f') or {}).get('issue_date', ''))
    if issue is None:
        return None
    end = _plus_years(issue, 1)
    for ext in issued_extensions(permit):
        start, years = _jd((ext.get('form') or {}).get('from_date', '')) or end, int(ext.get('years') or 1)
        end = _plus_years(start, years)
    days = (end - jdatetime.date.today()).days
    return {'date': _fmt(end), 'days': days, 'state': 'expired' if days < 0 else 'soon' if days <= SOON_DAYS else 'valid',
            'renewals': len(issued_extensions(permit))}


def can_request(permit):
    info = expiry(permit)
    return bool(info and info['state'] != 'valid' and info['renewals'] < MAX_RENEWALS and open_extension(permit) is None)


def status_line(permit):
    if open_extension(permit):
        return 'درخواست تمدید پروانه منتظر دهیاری'
    info = expiry(permit)
    if info and info['state'] == 'expired':
        return 'مهلت پروانه تمام شده؛ تمدید لازم است'
    if info and info['state'] == 'soon':
        return f'پروانه صادر شد؛ {info["days"]} روز تا پایان مهلت'
    return 'پروانه صادر و تحویل شد'


def defaults(permit, ext):
    """Starting values of the request and the renewal form from the file and the permit form."""
    f = (permit.licence or {}).get('f') or {}
    owner = permit.people.first()
    village = permit_step2._village(permit)         # pylint: disable=protected-access
    info = expiry(permit)
    dehyari, tech = permit_step7._signers(village)  # pylint: disable=protected-access
    req = {'name': owner.full_name if owner else '', 'father': owner.father_name if owner else '', 'id_number': owner.national_id if owner else '',
           'address': f.get('address', ''), 'phone': owner.phone if owner else '', 'request_no': permit_step2._next_number(village),   # pylint: disable=protected-access
           'request_date': permit_step2.today()}
    form = {'number': '', 'date': permit_step2.today(), 'village': village, 'section': f.get('section', ''), 'code': f.get('ins_code', ''),
            'fee_slip_no': f.get('fee_slip_no', ''), 'finish_date': f.get('finish_date', ''), 'ins_slip_no': f.get('ins_slip_no', ''),
            'owner': req['name'], 'registry_plot': f.get('registry_plot', ''), 'from_date': info['date'] if info else '', 'period': 'یک سال',
            'dehyari_name': dehyari, 'tech_name': tech}
    form['number'] = permit_step2._next_number(village, after=req['request_no'])     # pylint: disable=protected-access
    return {'req': {**req, **(ext.get('req') or {})}, 'form': {**form, **(ext.get('form') or {})}}


def _open(permit):
    ext = open_extension(permit)
    if ext is None:
        raise Conflict('درخواست تمدید بازی وجود ندارد.')
    return ext


@transaction.atomic
def request(actor, permit):
    """The owner (or the staff for a walk-in owner) opens a renewal request once the permit is near its end or past it."""
    if not (permit.request.user_id == actor.id or may_open(actor, permit)):
        raise Forbidden('اجازه‌ی درخواست تمدید را ندارید.')
    if permit.licence_state != 'issued':
        raise Conflict('هنوز پروانه‌ای صادر نشده است.')
    info = expiry(permit)
    if info and info['renewals'] >= MAX_RENEWALS:
        raise Conflict('پروانه دو بار تمدید شده و بیش از آن تمدید نمی‌شود.')
    if not can_request(permit):
        raise Conflict('تمدید فقط در ۳۰ روز آخر مهلت یا پس از پایان آن ممکن است (یا درخواست بازی دارید).')
    term = len(issued_extensions(permit)) + 1
    extensions = list(permit.extensions or [])
    extensions.append({'term': term, 'state': 'requested', 'asked_by': actor.get_full_name() or actor.username,
                       'asked_at': timezone.localtime().strftime('%Y/%m/%d %H:%M')})
    permit.extensions = extensions
    permit.save(update_fields=['extensions', 'updated_at'])
    sr = permit.request
    sr.add_workflow_step(action=f'درخواست تمدید مهلت پروانه ({TERMS[term]})', from_user=actor, to_role='clerk')
    sr.save(update_fields=['workflow_history', 'updated_at'])
    if sr.user_id == actor.id:
        for staff in permits._staff_to_tell(permit_step2._village(permit)):      # pylint: disable=protected-access
            notify(staff, 'درخواست تمدید پروانه', f'متقاضی پرونده {permit.pk} درخواست تمدید مهلت پروانه را باز کرد.', request=sr)
    return permit


def _collect(post):
    req = {key: _clean(post.get(f'q_{key}'), 150) for key in REQUEST_KEYS}
    form = {key: _clean(post.get(f'e_{key}'), 150) for key in FORM_KEYS}
    return req, form


@transaction.atomic
def save(actor, permit, post):
    if not may_open(actor, permit):
        raise Forbidden('فرم تمدید را کارکنان دهیاری پر می‌کنند.')
    ext = _open(permit)
    ext['req'], ext['form'] = _collect(post)
    permit.extensions = list(permit.extensions)
    permit.save(update_fields=['extensions', 'updated_at'])
    return permit


@transaction.atomic
def issue(actor, permit, post):
    """The signed renewal is recorded: a new term starts at the end of the previous one."""
    if not may_open(actor, permit):
        raise Forbidden('ثبت تمدید با کارکنان دهیاری است.')
    ext = _open(permit)
    req, form = _collect(post)
    if not digits(form['number']):
        raise Invalid('شماره‌ی نامه‌ی تمدید را وارد کنید.')
    if not _jd(form['date']) or not _jd(form['from_date']):
        raise Invalid('تاریخ نامه و تاریخ شروع مهلت را شمسی و درست وارد کنید.')
    if post.get('req_signed') != 'on' or post.get('signed') != 'on':
        raise Invalid('هر دو تیک (درخواست با امضا و اثر انگشت متقاضی؛ فرم تمدید با مهر و امضای دهیار و مسئول فنی) را بزنید.')
    years = 1
    ext.update({'req': req, 'form': {**form, 'date': permit_form._jalali(form['date']), 'from_date': permit_form._jalali(form['from_date'])},  # pylint: disable=protected-access
                'state': 'issued', 'years': years, 'issued_by': actor.get_full_name() or actor.username,
                'issued_at': timezone.localtime().strftime('%Y/%m/%d %H:%M')})
    permit.extensions = list(permit.extensions)
    permit.save(update_fields=['extensions', 'updated_at'])
    info = expiry(permit)
    sr = permit.request
    sr.add_workflow_step(action=f'تمدید مهلت پروانه ({TERMS.get(ext["term"], "")}) تا {info["date"]}', from_user=actor, to_role='citizen')
    sr.save(update_fields=['workflow_history', 'updated_at'])
    notify(sr.user, 'پروانه‌ی شما تمدید شد', f'مهلت پروانه تا {info["date"]} تمدید شد. فرم تمدید را از دهیاری تحویل بگیرید.', request=sr)
    return permit


def notify_expiring():
    """Tell owners (once per term and kind) whose permit ends within a month or has ended; run daily."""
    sent = 0
    for permit in PermitFile.objects.filter(licence_state='issued').select_related('request', 'request__user'):
        info = expiry(permit)
        if not info or info['state'] == 'valid' or info['renewals'] >= MAX_RENEWALS or open_extension(permit):
            continue
        key = f'{info["state"]}:{info["date"]}'
        licence = dict(permit.licence or {})
        if key in (licence.get('notified') or []):
            continue
        text = 'مهلت پروانه‌ی ساختمان شما تمام شده؛ برای تمدید به دهیاری مراجعه کنید.' if info['state'] == 'expired' else \
            f'مهلت پروانه‌ی ساختمان شما {info["days"]} روز دیگر ({info["date"]}) تمام می‌شود؛ برای تمدید اقدام کنید.'
        notify(permit.request.user, 'مهلت پروانه‌ی ساختمان', text, request=permit.request)
        licence['notified'] = (licence.get('notified') or []) + [key]
        permit.licence = licence
        permit.save(update_fields=['licence'])
        sent += 1
    return sent
