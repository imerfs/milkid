"""Construction without a permit, step 9: form 16 and the file summary for the Article 99 commission.

The dehyari's staff (any of the clerk / technical expert / dehyari) fill **form 16** («گزارش تخلف به کمیسیون ماده ۹۹», the report of the violation) from the file:
the owner and the village, the land use, whether the building was built or only started without a permit, the violations ticked on the form, what the commission
is asked for, the notice number and date and how it was served. They also fill the **file summary** («خلاصه‌ی پرونده», table 5, the covering letter to the
members of the commission): the owner, the built area, the judiciary expert's confirmation of the strength, the structure and the year. Both are typeset in the
browser, printed, signed by the dehyari (and the governor's office for form 16) and added to the file (with the signed scan when there is one). Any of the three
staff then confirms the step and the file goes on to step 10.
"""
from django.db import transaction
from django.utils import timezone

from main.accounting.parse import digits
from main.models import PermitDocument
from main.notifications import notify
from main.office import permit_commit, permit_form, permit_report, permit_step2
from main.office.errors import Conflict, Forbidden, Invalid
from main.office.permits import may_open

SCAN_KIND = 'form16_scan'
USES = (('residential', 'مسکونی'), ('commercial', 'تجاری'), ('mixed', 'مسکونی - تجاری'), ('industrial', 'صنعتی'), ('administrative', 'اداری'),
        ('agricultural', 'کشاورزی'), ('other', 'سایر'))
LAND_USE_MAP = {'residential': 'residential', 'commercial': 'commercial', 'administrative': 'administrative', 'services': 'other'}
BUILT = (('built', 'احداث کرده'), ('started', 'شروع کرده'))
SETBACKS = (('roads', 'راهها'), ('rivers', 'رودخانه‌ها'), ('canals', 'نهرهای عمومی، قنوات و چاهها'), ('floodways', 'مسیل‌ها'), ('power', 'خطوط و پایه‌های انتقال نیروی برق'),
            ('telecom', 'خطوط و پایه‌ها و تاسیسات مخابراتی'), ('oil_gas', 'لوله‌های انتقال نفت و گاز'), ('water', 'خطوط و لوله‌های آبرسانی'),
            ('military', 'تاسیسات نظامی و انتظامی و امنیتی'), ('sewage', 'تصفیه‌خانه‌های آب و فاضلاب'), ('other', 'سایر'))
OTHER_VIOLATIONS = (('b2', 'عدم رعایت کاربری'), ('b3', 'عدم رعایت مقررات ملی ساختمان'), ('b4', 'عدم رعایت قانون حفظ و گسترش فضاهای سبز'),
                    ('b5', 'عدم رعایت تراکم ساختمانی'), ('b6', 'عدم رعایت ضوابط تفکیک اراضی (ماده ۳) آیین‌نامه احداث بنا در خارج از محدوده قانونی و حریم شهرها'),
                    ('b7', 'عدم رعایت تعداد واحدهای مجاز جهت احداث'), ('b8', 'عدم رعایت تعداد پارکینگ مورد نیاز'))
REQUESTS = (('demolish', 'تقاضای رأی تخریب بنا را دارد'), ('demolish_extra', 'تقاضای رأی تخریب برای بنای مازاد و یا تجاوز شده به حریم‌ها را دارد'),
            ('max_fine', 'تقاضای رأی حداکثر جرایم تعیین شده را دارد'))
SERVED = (('owner', 'تحویل مالک'), ('dependents', 'بستگان مالک'), ('absent', 'مالک و بستگان و عوامل وی در محل حضور نداشته'), ('posted', 'اخطار در محل نصب گردید'))
NOTICE_SERVED = {'handed': ['owner'], 'posted': ['posted']}


def _text(value, limit=150):
    return ' '.join(str(value or '').split())[:limit]


def at_step(permit):
    return permit.unlicensed and permit.stage_no == 9 and permit.state == 'done'


def find(user, file_id):
    return permit_commit.find(user, file_id)


def documents(permit):
    return list(permit.documents.filter(kind=SCAN_KIND))


def defaults(permit, actor=None):
    """Everything the file already knows, laid out for form 16 and the summary."""
    report = permit_report.data(permit)
    totals = permit_report.totals(report)
    sr = permit.request
    profile = getattr(sr.user, 'profile', None)
    notice = permit.notice or {}
    reply = (permit.commit or {}).get('reply') or {}
    expert = (permit.commit or {}).get('expert') or {}
    visit = permit.visit or {}
    return {
        'number': '', 'date': permit_step2.today(), 'visit_date': report.get('visit_date') or visit.get('date') or '',
        'owner': report['name'], 'father': report['father'], 'phone': report['phone'], 'national_id': report['national_id'],
        'village': permit_step2._village(permit),                                        # pylint: disable=protected-access
        'dehestan': (permit.details or {}).get('dehestan') or (getattr(profile, 'dehestan_name', '') or ''),
        'district': sr.district.name if sr.district else (getattr(profile, 'district', '') or ''),
        'county': sr.county.name if sr.county else (getattr(profile, 'county', '') or ''),
        'use': LAND_USE_MAP.get(permit.land_use, 'residential'), 'built': 'built', 'b1': [], 'b': [], 'b5_area': '',
        'requests': ['max_fine'], 'notice_no': notice.get('number', ''), 'notice_date': notice.get('date', ''), 'served': NOTICE_SERVED.get(notice.get('delivery'), []),
        'notes': 'پیوست', 'dehyar': (actor.get_full_name() or actor.username) if actor is not None and actor.is_authenticated else '', 'governor': '',
        'summary': {'number': '', 'date': permit_step2.today(), 'area': permit_report._fmt(totals['total']), 'expert': reply.get('expert') or expert.get('name', ''),         # pylint: disable=protected-access
                    'expert_no': reply.get('letter_no', ''), 'expert_date': reply.get('letter_date', ''), 'structure': report['structure'], 'year': report['year'],
                    'strength': reply.get('strength', ''), 'contact': report['phone'], 'widening': False,
                    'use': dict(USES).get(LAND_USE_MAP.get(permit.land_use, 'residential'), 'مسکونی')},
    }


def data(permit, actor=None):
    base = defaults(permit, actor)
    saved = (permit.form16 or {}).get('values') or {}
    merged = {**base, **{k: v for k, v in saved.items() if k in base and k != 'summary'}}
    merged['summary'] = {**base['summary'], **(saved.get('summary') or {})}
    return merged


def clean(post):
    """The form's fields from a POST: only the known choices survive."""
    def pick(name, allowed):
        return [k for k in post.getlist(name) if k in dict(allowed)] if hasattr(post, 'getlist') else [k for k in post.get(name, []) if k in dict(allowed)]

    use = post.get('use') if post.get('use') in dict(USES) else 'residential'
    built = post.get('built') if post.get('built') in dict(BUILT) else 'built'
    values = {
        'number': _text(digits(post.get('number', '')).replace('٫', '/'), 40), 'date': permit_form._jalali(post.get('date', '')) or permit_step2.today(),         # pylint: disable=protected-access
        'visit_date': permit_form._jalali(post.get('visit_date', '')) or '',                                                                                   # pylint: disable=protected-access
        'owner': _text(post.get('owner'), 120), 'father': _text(post.get('father'), 60), 'phone': digits(post.get('phone', ''))[:11],
        'national_id': digits(post.get('national_id', ''))[:10], 'village': _text(post.get('village'), 80), 'dehestan': _text(post.get('dehestan'), 80),
        'district': _text(post.get('district'), 80), 'county': _text(post.get('county'), 80), 'use': use, 'built': built,
        'b1': pick('b1', SETBACKS), 'b': pick('b', OTHER_VIOLATIONS), 'b5_area': _text(digits(post.get('b5_area', '')), 12),
        'requests': pick('requests', REQUESTS), 'notice_no': _text(digits(post.get('notice_no', '')).replace('٫', '/'), 40),
        'notice_date': permit_form._jalali(post.get('notice_date', '')) or '', 'served': pick('served', SERVED),                                              # pylint: disable=protected-access
        'notes': _text(post.get('notes'), 200), 'dehyar': _text(post.get('dehyar'), 80), 'governor': _text(post.get('governor'), 80),
        'summary': {'number': _text(digits(post.get('s_number', '')).replace('٫', '/'), 40), 'date': permit_form._jalali(post.get('s_date', '')) or permit_step2.today(),   # pylint: disable=protected-access
                    'area': _text(digits(post.get('s_area', '')), 12), 'expert': _text(post.get('s_expert'), 120), 'expert_no': _text(digits(post.get('s_expert_no', '')), 40),
                    'expert_date': permit_form._jalali(post.get('s_expert_date', '')) or '', 'structure': _text(post.get('s_structure'), 60),         # pylint: disable=protected-access
                    'year': _text(digits(post.get('s_year', '')), 4), 'strength': post.get('s_strength') if post.get('s_strength') in ('has', 'lacks') else '',
                    'contact': digits(post.get('s_contact', ''))[:11], 'widening': post.get('s_widening') == 'on', 'use': dict(USES)[use]},
    }
    if not values['owner']:
        raise Invalid('نام مالک را وارد کنید.')
    return values


def _store(permit, values):
    form = dict(permit.form16 or {})
    form['values'] = values
    permit.form16 = form


@transaction.atomic
def save(actor, permit, post):
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی این کار را ندارید.')
    if not at_step(permit):
        raise Conflict('پرونده در مرحله‌ی فرم ۱۶ نیست.')
    _store(permit, clean(post))
    permit.save(update_fields=['form16', 'updated_at'])
    return permit


@transaction.atomic
def file_form(actor, permit, post, files=None):
    """Put form 16 and the summary in the file (with the signed scan when there is one); the staff of the village are told."""
    save(actor, permit, post)
    found, error = permit_form._uploads(files or {}, 'scan', permit_form.ID_EXTENSIONS)         # pylint: disable=protected-access
    if error:
        raise Invalid(error)
    if found:
        for old in documents(permit):
            old.document.delete(save=False)
            old.delete()
        for upload in found[:4]:
            PermitDocument.objects.create(file=permit, kind=SCAN_KIND, document=upload, original_name=upload.name[:200], size=upload.size, uploaded_by=actor)
    form = dict(permit.form16 or {})
    form['filed'] = {'by': actor.get_full_name() or actor.username, 'at': timezone.localtime().strftime('%Y/%m/%d %H:%M')}
    permit.form16, permit.form16_state = form, 'filed'
    permit.save(update_fields=['form16', 'form16_state', 'updated_at'])
    sr = permit.request
    sr.add_workflow_step(action='افزودن فرم ۱۶ و خلاصه‌ی پرونده به پرونده (مرحله ۹)', from_user=actor, to_role='clerk')
    sr.save(update_fields=['workflow_history', 'updated_at'])
    return permit


def blocking(permit):
    return [] if permit.form16_state == 'filed' else ['فرم ۱۶ هنوز به پرونده افزوده نشده است.']


@transaction.atomic
def finish(actor, permit, post):
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی تایید این مرحله را ندارید.')
    if not at_step(permit):
        raise Conflict('پرونده در مرحله‌ی فرم ۱۶ نیست.')
    waiting = blocking(permit)
    if waiting:
        raise Conflict(waiting[0])
    if post.get('confirm') != 'on':
        raise Invalid('تیک «فرم ۱۶ و خلاصه‌ی پرونده را بررسی کردم» لازم است.')
    permit.stage_no = 10
    permit.staff_notes = (post.get('notes') or '')[:2000]
    permit.save()
    sr = permit.request
    sr.add_workflow_step(action='تایید مرحله ۹ (فرم ۱۶ و خلاصه‌ی پرونده)', from_user=actor, to_role='citizen', notes=permit.staff_notes)
    sr.save(update_fields=['workflow_history', 'updated_at'])
    notify(sr.user, 'پرونده‌ی شما برای کمیسیون آماده شد', f'فرم ۱۶ و خلاصه‌ی پرونده {permit.pk} در پرونده قرار گرفت؛ پرونده به مرحله‌ی ۱۰ (کمیسیون ماده ۹۹) رفت.', request=sr)
    return permit
