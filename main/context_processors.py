from django.conf import settings
from django.db import DatabaseError
from django.utils import timezone

from main.seo import page_context


def seo(request):
    return {'seo': page_context(request)}


def contact(request):
    """The support address shown on public pages (settings.SUPPORT_EMAIL)."""
    return {'support_email': settings.SUPPORT_EMAIL}


def office(request):
    """Counters for the letters / appointments shortcuts (navbar and dashboards)."""
    user = request.user
    if not user.is_authenticated:
        return {}
    from main.models import Appointment
    from main.office.appointments import PROVIDER_ROLES
    from main.office.letters import unread_count
    role = getattr(getattr(user, 'profile', None), 'role', None)
    try:
        pending = (Appointment.objects.filter(provider=user, status='pending', end__gte=timezone.now()).count()
                   if role in PROVIDER_ROLES else 0)
        unread = unread_count(user)
    except DatabaseError:        # e.g. migrations not applied yet: the counters are optional, the page is not
        pending = unread = 0
    return {'office': {'letters_unread': unread, 'appointments_pending': pending,
                       'can_grant_roles': role == 'dehyari' or user.is_superuser or role == 'admin'}}
