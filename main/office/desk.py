"""The administrative expert's desk (کارشناس اداری): what needs attention today, in one place.

Read-only queries over letters, appointments and the village's service requests, plus one action: a reminder to a
citizen whose request waits for documents.
"""
from datetime import datetime, time, timedelta

import jdatetime
from django.utils import timezone

from main.models import Appointment, LetterRecipient, Notification, ServiceRequest
from main.notifications import notify
from main.office import letters
from main.office.errors import Forbidden, NotFound, RateLimited
from main.office.roles import is_admin

REMINDER_TITLE = 'یادآوری تکمیل مدارک درخواست'
REMINDER_GAP = timedelta(hours=24)
FOLLOW_UP_LIMIT = 30
MONTHS = jdatetime.date(1400, 1, 1).j_months_fa


def request_scope(user):
    """Service requests the user may see: those of citizens of the user's village (an admin sees all, no village sees none)."""
    rows = ServiceRequest.objects.select_related('user', 'user__profile', 'service')
    if is_admin(user):
        return rows
    village = letters.village_of(user)
    return rows.filter(user__profile__city_village=village) if village else rows.none()


def follow_ups(user):
    """Requests waiting for the citizen's documents, oldest first (the longest wait on top)."""
    return request_scope(user).filter(status='requires_documents').order_by('updated_at', 'created_at')[:FOLLOW_UP_LIMIT]


def remind(actor, request_id):
    """Notify the citizen to complete the documents. One reminder per request per day."""
    sr = request_scope(actor).filter(pk=request_id).first()
    if sr is None:
        raise NotFound('درخواست در حوزه‌ی شما پیدا نشد.')
    if sr.status != 'requires_documents':
        raise Forbidden('این درخواست دیگر منتظر مدارک نیست.')
    recent = Notification.objects.filter(user=sr.user, related_request=sr, title=REMINDER_TITLE,
                                         created_at__gte=timezone.now() - REMINDER_GAP)
    if recent.exists():
        raise RateLimited('امروز برای این درخواست یادآوری فرستاده شده است.')
    notify(sr.user, REMINDER_TITLE, f'برای درخواست «{sr.title[:80]}» مدارک لازم هنوز کامل نشده است. '
           'لطفاً از بخش «درخواست‌های من» آن‌ها را بارگذاری کنید.', request=sr)
    return sr


# ---------- appointments ----------

def _own_appointments(user):
    return Appointment.objects.filter(provider=user, status__in=Appointment.ACTIVE).select_related('client')


def today_agenda(user):
    start = timezone.make_aware(datetime.combine(timezone.localdate(), time.min))
    return _own_appointments(user).filter(start__gte=start, start__lt=start + timedelta(days=1)).order_by('start')


def pending_appointments(user):
    return _own_appointments(user).filter(status='pending', start__gte=timezone.now()).order_by('start')[:10]


# ---------- Jalali month calendar ----------

def parse_month(text, today=None):
    """``'1405-03'`` -> (1405, 3); anything unusable gives the month of ``today``."""
    today = today or jdatetime.date.today()
    try:
        year, month = (int(part) for part in str(text).split('-'))
        jdatetime.date(year, month, 1)
    except (ValueError, TypeError):
        return today.year, today.month
    return (year, month) if 1300 <= year <= 1500 else (today.year, today.month)


def shift_month(year, month, step):
    index = year * 12 + (month - 1) + step
    return index // 12, index % 12 + 1


def _month_key(year, month):
    return f'{year:04d}-{month:02d}'


def month_days(year, month):
    first = jdatetime.date(year, month, 1)
    ny, nm = shift_month(year, month, 1)
    return (jdatetime.date(ny, nm, 1) - first).days


def month_counts(user, year, month):
    """Gregorian date -> number of active appointments the user hosts that day, for one Jalali month."""
    first = jdatetime.date(year, month, 1).togregorian()
    last = first + timedelta(days=month_days(year, month))
    counts = {}
    rows = _own_appointments(user).filter(start__date__gte=first, start__date__lt=last).values_list('start', flat=True)
    for start in rows:
        day = timezone.localtime(start).date()
        counts[day] = counts.get(day, 0) + 1
    return counts


def month_grid(user, year, month, today=None):
    """Weeks (Saturday first) of day cells for the calendar card, plus the header and the prev/next month keys."""
    today = today or timezone.localdate()
    counts = month_counts(user, year, month)
    first = jdatetime.date(year, month, 1)
    cells = [None] * first.weekday()           # jdatetime: Saturday = 0
    for number in range(1, month_days(year, month) + 1):
        greg = jdatetime.date(year, month, number).togregorian()
        cells.append({'day': number, 'count': counts.get(greg, 0), 'today': greg == today, 'friday': greg.weekday() == 4})
    cells += [None] * (-len(cells) % 7)
    py, pm = shift_month(year, month, -1)
    ny, nm = shift_month(year, month, 1)
    return {
        'title': f'{MONTHS[month - 1]} {year}', 'weeks': [cells[i:i + 7] for i in range(0, len(cells), 7)],
        'prev': _month_key(py, pm), 'next': _month_key(ny, nm), 'total': sum(counts.values()),
    }


def summary(user):
    """Numbers for the top of the desk."""
    inbox = LetterRecipient.objects.filter(user=user, read_at__isnull=True, archived=False, letter__status='sent')
    return {
        'unread': inbox.count(),
        'drafts': letters.mailbox(user, 'drafts').count(),
        'today': today_agenda(user).count(),
        'pending_visits': _own_appointments(user).filter(status='pending', start__gte=timezone.now()).count(),
        'waiting_docs': request_scope(user).filter(status='requires_documents').count(),
    }


def greeting(now=None):
    hour = timezone.localtime(now or timezone.now()).hour
    return 'صبح بخیر' if hour < 12 else 'عصر بخیر' if hour < 18 else 'شب بخیر'

