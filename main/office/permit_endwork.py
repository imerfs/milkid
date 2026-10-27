"""Building permit, the last step: the owner's request for the end-of-work certificate (گواهی پایان ساخت) and its issue.

Once forms 8-13 are confirmed (file at stage 9) the owner asks the dehyari for the certificate. Any of the clerk, the technical expert
and the dehyari answers the request: they either reject it with a reason or approve it, which gives the certificate its number and date;
the system fills the certificate (owner, plot, permit, the supervising engineer, limits, floors) from the file, the staff print it, the
dehyari and the technical manager (the technical expert) sign and stamp it by hand, and the staff record that it was handed over.
"""
from django.db import transaction
from django.utils import timezone

from main.accounting.parse import digits
from main.notifications import notify
from main.office import permit_form, permit_services, permit_step2, permit_step7, permit_supervision, permits
from main.office.errors import Conflict, Forbidden, Invalid
from main.office.permits import may_open

KEYS = ('number', 'date', 'village', 'section', 'owner', 'req_no', 'req_date', 'plot', 'address', 'permit_no', 'permit_date', 'report_date', 'sup_name',
        'sup_sign', 'form_no', 'use', 'code', 'floors_count', 'total_area', 'notes', 'dehyari_name', 'tech_name')
SIDES = ('north', 'east', 'south', 'west')
FLOORS = permit_step7.FLOORS
LABELS = {'number': 'شماره‌ی گواهی', 'date': 'تاریخ گواهی', 'village': 'روستا', 'section': 'بخش', 'owner': 'خانم/آقای (مالک)', 'req_no': 'در پاسخ به درخواست شماره',
          'req_date': 'مورخ', 'plot': 'پلاک ثبتی شماره', 'address': 'به نشانی', 'permit_no': 'دارای پروانه ساختمان شماره', 'permit_date': 'مورخ',
          'report_date': 'طبق گزارش مورخ', 'sup_name': 'تحت نظارت خانم/آقای (مهندس ناظر)', 'sup_sign': 'به شماره امضا', 'form_no': 'تایید ایشان به شماره برگ',
          'use': 'کاربری زمین', 'code': 'کد', 'floors_count': 'جمعاً (تعداد طبقات)', 'total_area': 'با کل زیربنای (م²)', 'notes': 'ملاحظات',
          'dehyari_name': 'نام دهیار', 'tech_name': 'نام مسئول فنی دهیاری'}
STATE_TEXT = {'': 'درخواست ثبت نشده', 'requested': 'منتظر پاسخ دهیاری', 'approved': 'تایید شد؛ چاپ و امضای دهیار و مسئول فنی', 'issued': 'صادر و تحویل شد', 'rejected': 'رد شد'}


def _clean(value, limit=150):
    return ' '.join(str(value or '').split())[:limit]


def _tidy(value):
    """'10.0' -> '10' for lengths and areas that came through a float."""
    text = str(value if value is not None else '')
    return text[:-2] if text.endswith('.0') else text


def _plain(value):
    return int(value) if isinstance(value, float) and value == int(value) else value


def available(permit):
    """The request opens when the supervision is complete (the file reached stage 9)."""
    return permit.stage_no >= 9


def defaults(permit):
    """Everything the certificate needs that the file knows: the owner, the plot, the permit, the supervision and the permit form's limits / floors."""
    lic = permit_step7.payload(permit) if permit.licence_state == 'issued' else {}
    village = permit_step2._village(permit)                       # pylint: disable=protected-access
    owner = permit.people.first()
    forms = permit_supervision.forms(permit)
    saved = permit.endwork or {}
    dehyari, tech = permit_step7._signers(village)                # pylint: disable=protected-access
    data = {'number': '', 'date': permit_step2.today(), 'village': village, 'section': lic.get('section', '') or 'مرکزی', 'owner': owner.full_name if owner else '',
            'req_no': saved.get('req_no', ''), 'req_date': saved.get('req_date', ''), 'plot': lic.get('registry_plot', '') or permit.registry_plot,
            'address': permit_services._street(lic.get('address', '') or permit.address, village), 'permit_no': lic.get('permit_no', ''), 'permit_date': lic.get('issue_date', ''),
            'report_date': forms[12]['f'].get('date', '') or forms[13]['f'].get('date', ''), 'sup_name': lic.get('sup_name', ''), 'sup_sign': lic.get('sup_sign', '') or lic.get('sup_license', ''),
            'form_no': forms[13]['f'].get('number', ''), 'use': dict(permit_step7.CHOICES['usage']).get(lic.get('usage', ''), '') or 'مسکونی', 'code': '',
            'notes': '', 'dehyari_name': dehyari, 'tech_name': tech}
    count = total = 0.0
    for floor, _ in FLOORS:
        row = {f: _tidy(lic.get(f'fl_{floor}_{f}', '')) for f in ('count', 'area')}
        data[f'fl_{floor}_count'], data[f'fl_{floor}_area'] = row['count'], row['area']
        data[f'fl_{floor}_use'] = data['use'] if row['area'] != '' else ''
        for key, name in (('count', 'count'), ('area', 'total')):
            try:
                value = float(str(row[key]).replace(',', '.'))
            except ValueError:
                continue
            if key == 'count':
                count += value
            else:
                total += value
    data['floors_count'], data['total_area'] = _plain(count) or '', _plain(round(total, 2)) or ''
    for side in SIDES:
        data[f'sd_{side}_deed'], data[f'sd_{side}_after'] = _tidy(lic.get(f'sd_{side}_actual', '')), _tidy(lic.get(f'sd_{side}_after', ''))
    return data


def keys():
    out = list(KEYS)
    for floor, _ in FLOORS:
        out += [f'fl_{floor}_count', f'fl_{floor}_area', f'fl_{floor}_use']
    for side in SIDES:
        out += [f'sd_{side}_deed', f'sd_{side}_after']
    return out


def payload(permit):
    return {**defaults(permit), **{k: v for k, v in ((permit.endwork or {}).get('f') or {}).items() if v != ''}}


def _collect(post):
    return {key: _clean(post.get(f'f_{key}')) for key in keys()}


def _staff_to_tell(permit):
    return list(permits._staff_to_tell(permit_step2._village(permit)))       # pylint: disable=protected-access


def _save(permit, state=None, **changes):
    endwork = dict(permit.endwork or {})
    endwork.update(changes)
    permit.endwork = endwork
    update = ['endwork', 'updated_at']
    if state is not None:
        permit.endwork_state = state
        update.append('endwork_state')
    permit.save(update_fields=update)


@transaction.atomic
def request(actor, permit):
    """The owner (or the staff for a walk-in owner) asks for the end-of-work certificate."""
    if not (permit.request.user_id == actor.id or may_open(actor, permit)):
        raise Forbidden('اجازه‌ی درخواست ندارید.')
    if not available(permit):
        raise Conflict('درخواست پایان کار پس از تایید همه‌ی فرم‌های نظارت (۸ تا ۱۳) ممکن است.')
    if permit.endwork_state in ('requested', 'approved', 'issued'):
        raise Conflict('درخواست پایان کار قبلا ثبت شده است.')
    village = permit_step2._village(permit)                       # pylint: disable=protected-access
    _save(permit, 'requested', req_no=permit_step2._next_number(village), req_date=permit_step2.today(), reason='',          # pylint: disable=protected-access
          asked_by=actor.get_full_name() or actor.username, asked_at=timezone.localtime().strftime('%Y/%m/%d %H:%M'))
    sr = permit.request
    sr.add_workflow_step(action='درخواست گواهی پایان کار', from_user=actor, to_role='clerk')
    sr.save(update_fields=['workflow_history', 'updated_at'])
    if sr.user_id == actor.id:
        for staff in _staff_to_tell(permit):
            notify(staff, 'درخواست گواهی پایان کار', f'متقاضی پرونده {permit.pk} درخواست گواهی پایان کار کرد؛ پاسخ دهید.', request=sr)
    return permit


@transaction.atomic
def save(actor, permit, post):
    if not may_open(actor, permit):
        raise Forbidden('گواهی را کارکنان دهیاری پر می‌کنند.')
    if permit.endwork_state not in ('requested', 'approved'):
        raise Conflict('درخواستی برای ویرایش وجود ندارد.')
    _save(permit, f=_collect(post))
    return permit


@transaction.atomic
def approve(actor, permit, post):
    """Any of the clerk / technical expert / dehyari: the certificate gets its number and date and may be printed."""
    if not may_open(actor, permit):
        raise Forbidden('پاسخ به درخواست با کارکنان دهیاری است.')
    if permit.endwork_state != 'requested':
        raise Conflict('درخواستی برای تایید وجود ندارد.')
    fields = _collect(post)
    if not digits(fields['number']):
        raise Invalid('شماره‌ی گواهی را وارد کنید.')
    date = permit_form._jalali(fields['date'])                    # pylint: disable=protected-access
    if not date:
        raise Invalid('تاریخ گواهی را شمسی و درست وارد کنید.')
    fields['date'] = date
    _save(permit, 'approved', f=fields, approved_by=actor.get_full_name() or actor.username, approved_at=timezone.localtime().strftime('%Y/%m/%d %H:%M'))
    sr = permit.request
    sr.add_workflow_step(action=f'تایید درخواست پایان کار؛ گواهی شماره {fields["number"]}', from_user=actor, to_role='citizen')
    sr.save(update_fields=['workflow_history', 'updated_at'])
    notify(sr.user, 'گواهی پایان کار آماده است', 'درخواست شما تایید شد؛ گواهی را چاپ کنید و برای مهر و امضای دهیار و مسئول فنی به دهیاری ببرید.', request=sr)
    return permit


@transaction.atomic
def reject(actor, permit, reason):
    if not may_open(actor, permit):
        raise Forbidden('پاسخ به درخواست با کارکنان دهیاری است.')
    if permit.endwork_state != 'requested':
        raise Conflict('درخواستی برای رد وجود ندارد.')
    reason = _clean(reason, 600)
    if not reason:
        raise Invalid('دلیل رد را بنویسید.')
    _save(permit, 'rejected', reason=reason)
    notify(permit.request.user, 'درخواست پایان کار رد شد', reason, request=permit.request)
    return permit


@transaction.atomic
def issue(actor, permit, post):
    """The dehyari and the technical manager signed and stamped the printed certificate and it was handed to the owner."""
    if not may_open(actor, permit):
        raise Forbidden('ثبت تحویل با کارکنان دهیاری است.')
    if permit.endwork_state != 'approved':
        raise Conflict('گواهی‌ای برای ثبت تحویل وجود ندارد.')
    if post.get('signed') != 'on':
        raise Invalid('تیک «گواهی با مهر و امضای دهیار و مسئول فنی به متقاضی تحویل شد» را بزنید.')
    _save(permit, 'issued', issued_by=actor.get_full_name() or actor.username, issued_at=timezone.localtime().strftime('%Y/%m/%d %H:%M'))
    sr = permit.request
    sr.add_workflow_step(action='صدور و تحویل گواهی پایان ساخت - پایان پرونده', from_user=actor, to_role='citizen')
    sr.save(update_fields=['workflow_history', 'updated_at'])
    notify(sr.user, 'گواهی پایان ساخت صادر شد', 'گواهی پایان ساخت با مهر و امضای دهیار و مسئول فنی تحویل شد؛ پرونده‌ی شما به پایان رسید.', request=sr)
    return permit
