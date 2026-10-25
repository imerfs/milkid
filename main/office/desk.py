"""The administrative expert's desk (کارشناس اداری): what needs attention today, in one place.

Read-only queries over letters and the village's service requests, plus one action: a reminder to a citizen whose
request waits for documents.
"""
from datetime import timedelta

from django.utils import timezone

from main.models import Notification, ServiceRequest
from main.notifications import notify
from main.office import letters, messenger
from main.office.directory import requests_for
from main.office.errors import Forbidden, NotFound, RateLimited
from main.office.roles import is_admin

REMINDER_TITLE = 'یادآوری تکمیل مدارک درخواست'
REMINDER_GAP = timedelta(hours=24)
FOLLOW_UP_LIMIT = 30


def request_scope(user):
    """Service requests the user may see: those of citizens of the user's village (an admin sees all, no village sees none)."""
    rows = ServiceRequest.objects.select_related('user', 'user__profile', 'service')
    if is_admin(user):
        return rows
    village = letters.village_of(user)
    return rows.filter(requests_for(village)) if village else rows.none()


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


def summary(user):
    """Numbers for the top of the desk."""
    return {
        'unread': messenger.unread_total(user),
        'drafts': letters.mailbox(user, 'drafts').count(),
        'waiting_docs': request_scope(user).filter(status='requires_documents').count(),
    }


def greeting(now=None):
    hour = timezone.localtime(now or timezone.now()).hour
    return 'صبح بخیر' if hour < 12 else 'عصر بخیر' if hour < 18 else 'شب بخیر'

