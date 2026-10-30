"""Construction without a permit, step 6: the judiciary expert's reply.

After the visit the expert gives the owner two papers: the covering letter and the «جدول شماره ۲» (areas, floors, structure, occupation, strength of the
building). The owner hands the originals to the dehyari and uploads the scan of both here, typing the letter's number and date and what the table says
about the strength of the building (the later steps depend on it). Any of the clerk / technical expert / dehyari confirms the papers (or sends them back
with a reason) and then the step; the file goes on to step 7.
"""
from django.db import transaction
from django.utils import timezone

from main import lifecycle
from main.models import PermitDocument
from main.notifications import notify
from main.office import permit_commit, permit_form, permit_step2
from main.office.errors import Conflict, Forbidden, Invalid, NotFound
from main.office.permits import may_open

LETTER_KIND, TABLE_KIND = 'expert_letter', 'expert_table'
STRENGTH = {'has': 'ساختمان استحکام دارد', 'lacks': 'ساختمان فاقد استحکام است'}
MAX_FILES = 6


def find(user, file_id):
    return permit_commit.find(user, file_id)


def at_step(permit):
    return permit.unlicensed and permit.stage_no == 6 and permit.state == 'done'


def documents(permit, kind):
    return list(permit.documents.filter(kind=kind))


def defaults(permit):
    """What the page shows: the expert chosen in step 5, and what was typed before."""
    saved = (permit.commit or {}).get('reply') or {}
    expert = (permit.commit or {}).get('expert') or {}
    return {'expert': saved.get('expert') or expert.get('name', ''), 'letter_no': saved.get('letter_no', ''), 'letter_date': saved.get('letter_date', ''),
            'strength': saved.get('strength', ''), 'notes': saved.get('notes', '')}


def _owner_check(user, permit):
    if permit.request.user_id != user.id:
        raise NotFound('پرونده پیدا نشد.')
    if not at_step(permit):
        raise Conflict('پرونده در مرحله‌ی جوابیه‌ی کارشناس نیست.')


def _replace(permit, kind, found, user):
    for old in documents(permit, kind):
        old.document.delete(save=False)
        old.delete()
    for upload in found:
        PermitDocument.objects.create(file=permit, kind=kind, document=upload, original_name=upload.name[:200], size=upload.size, uploaded_by=user)


def _scans(permit, files, field, kind, label):
    found, error = permit_form._uploads(files, field, permit_form.ID_EXTENSIONS)         # pylint: disable=protected-access
    if error:
        raise Invalid(error)
    if not found and not documents(permit, kind):
        raise Invalid(f'تصویر {label} را بارگذاری کنید.')
    if len(found) > MAX_FILES:
        raise Invalid(f'حداکثر {MAX_FILES} فایل برای هر برگه می‌توانید بفرستید.')
    return found


@transaction.atomic
def upload(user, permit, post, files):
    _owner_check(user, permit)
    if permit.reply_state not in ('', 'returned'):
        raise Conflict('جوابیه‌ها قبلاً فرستاده شده است.')
    letters = _scans(permit, files, 'letter', LETTER_KIND, 'نامه‌ی کارشناس')
    tables = _scans(permit, files, 'table', TABLE_KIND, 'جدول شماره ۲')
    number = permit_commit._clean(post.get('letter_no'), 40)            # pylint: disable=protected-access
    date = permit_form._jalali(post.get('letter_date', ''))              # pylint: disable=protected-access
    strength = post.get('strength', '')
    if not number:
        raise Invalid('شماره‌ی نامه‌ی کارشناس را وارد کنید.')
    if not date or date > permit_step2.today():
        raise Invalid('تاریخ نامه را به شکل ۱۴۰۵/۰۷/۰۵ وارد کنید (نمی‌تواند در آینده باشد).')
    if strength not in STRENGTH:
        raise Invalid('نظر کارشناس درباره‌ی استحکام بنا را انتخاب کنید.')
    if post.get('delivered') != 'on':
        raise Invalid('تیک «اصل دو برگه را به دهیاری تحویل داده‌ام» لازم است.')
    if letters:
        _replace(permit, LETTER_KIND, letters, user)
    if tables:
        _replace(permit, TABLE_KIND, tables, user)
    commit = dict(permit.commit or {})
    commit['reply'] = {'expert': permit_commit._clean(post.get('expert'), 120), 'letter_no': number, 'letter_date': date, 'strength': strength,      # pylint: disable=protected-access
                       'notes': permit_commit._clean(post.get('notes'), 300), 'at': permit_commit._now()}                                             # pylint: disable=protected-access
    was_returned = permit.reply_state == 'returned'
    permit.commit, permit.reply_state = commit, 'uploaded'
    permit.save(update_fields=['commit', 'reply_state', 'updated_at'])
    permit_commit._announce(permit, user, 'جوابیه‌های کارشناس دادگستری', was_returned)       # pylint: disable=protected-access
    return permit


@transaction.atomic
def verify(actor, permit, post):
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی تایید را ندارید.')
    if not at_step(permit) or permit.reply_state != 'uploaded':
        raise Conflict('جوابیه‌ای برای تایید نیست.')
    if post.get('confirm') != 'on':
        raise Invalid('تیک «دو برگه را با اصل تحویل‌شده به دهیاری مقایسه و بررسی کردم» لازم است.')
    commit = dict(permit.commit or {})
    commit['reply'] = {**(commit.get('reply') or {}), 'checked': {'by': actor.get_full_name() or actor.username, 'at': permit_commit._now()}}      # pylint: disable=protected-access
    permit.commit, permit.reply_state = commit, 'verified'
    permit.save(update_fields=['commit', 'reply_state', 'updated_at'])
    notify(permit.request.user, 'جوابیه‌های کارشناس تایید شد', f'جوابیه‌های کارشناس پرونده {permit.pk} تایید شد.', request=permit.request)
    return permit


@transaction.atomic
def send_back(actor, permit, notes):
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی این کار را ندارید.')
    if not at_step(permit) or permit.reply_state != 'uploaded':
        raise Conflict('جوابیه‌ای برای برگرداندن نیست.')
    notes = (notes or '').strip()
    if not notes:
        raise Invalid('بنویسید مشکل جوابیه‌ها چیست.')
    lifecycle.request_documents(permit.request, actor, f'جوابیه‌های کارشناس: {notes}')
    permit.reply_state, permit.staff_notes = 'returned', notes[:2000]
    permit.save(update_fields=['reply_state', 'staff_notes', 'updated_at'])
    return permit


def blocking(permit):
    return [] if permit.reply_state == 'verified' else ['جوابیه‌های کارشناس هنوز تایید نشده است.']


@transaction.atomic
def finish(actor, permit, post):
    """Any of the three staff: the replies are confirmed; the file goes on to step 7."""
    if not may_open(actor, permit):
        raise Forbidden('اجازه‌ی تایید این مرحله را ندارید.')
    if not at_step(permit):
        raise Conflict('پرونده در مرحله‌ی جوابیه‌ی کارشناس نیست.')
    waiting = blocking(permit)
    if waiting:
        raise Conflict(waiting[0])
    if post.get('confirm') != 'on':
        raise Invalid('تیک «مدارک این مرحله را بررسی کردم» لازم است.')
    permit.stage_no = 7
    permit.staff_notes = (post.get('notes') or '')[:2000]
    permit.save()
    sr = permit.request
    sr.add_workflow_step(action='تایید مرحله ۶ (جوابیه‌ی کارشناس دادگستری)', from_user=actor, to_role='citizen', notes=permit.staff_notes)
    sr.save(update_fields=['workflow_history', 'updated_at'])
    notify(sr.user, 'مرحله‌ی ۶ تایید شد', f'جوابیه‌های کارشناس پرونده {permit.pk} تایید شد؛ پرونده به مرحله‌ی ۷ رفت.', request=sr)
    from main.office import permit_dues       # pylint: disable=import-outside-toplevel
    permit_dues.tell_the_officer(permit)
    return permit
