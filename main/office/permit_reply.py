"""Construction without a permit, step 6: the judiciary expert's reply.

After the visit the expert gives the owner two papers: the covering letter and the «جدول شماره ۲» (areas, floors, structure, occupation, strength of the
building). The owner hands the originals to the dehyari and uploads the scan of both here, typing the letter's number and date and what the table says
about the strength of the building (the later steps depend on it). Any of the clerk / technical expert / dehyari confirms the papers (or sends them back
with a reason) and then the step; the file goes on to step 7.
"""
from django.db import transaction
from django.utils import timezone

from main.office import permit_request, step_flow
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



def _tell_the_officer(permit):
    from main.office import permit_dues       # pylint: disable=import-outside-toplevel
    permit_dues.tell_the_officer(permit)


STEP = step_flow.Step(
    stage=6, state_field='reply_state', data_path=('commit', 'reply'),
    not_here='پرونده در مرحله‌ی جوابیه‌ی کارشناس نیست.', nothing_to_verify='جوابیه‌ای برای تایید نیست.',
    verify_tick='تیک «دو برگه را با اصل تحویل‌شده به دهیاری مقایسه و بررسی کردم» لازم است.',
    verified_title='جوابیه‌های کارشناس تایید شد', verified_text='جوابیه‌های کارشناس پرونده {pk} تایید شد.',
    nothing_to_send_back='جوابیه‌ای برای برگرداندن نیست.', reason_needed='بنویسید مشکل جوابیه‌ها چیست.', back_prefix='جوابیه‌های کارشناس',
    blocking_text='جوابیه‌های کارشناس هنوز تایید نشده است.', history='تایید مرحله ۶ (جوابیه‌ی کارشناس دادگستری)',
    done_title='مرحله‌ی ۶ تایید شد', done_text='جوابیه‌های کارشناس پرونده {pk} تایید شد؛ پرونده به مرحله‌ی ۷ رفت.', after=_tell_the_officer)
at_step, verify, send_back, blocking, finish = STEP.at_step, STEP.verify, STEP.send_back, STEP.blocking, STEP.finish
