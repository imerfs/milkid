"""Village scope of a staff member over service requests: the one place that answers "may this person see this request?".

The rule itself is ``directory.requests_for``; here it is applied to a user. A dehyari / expert / inspector sees only the requests of their own village,
an admin sees everything, and staff whose profile names no village see none. Lists (``visible_requests``), single requests (``in_scope``) and permit
files (``main.office.permits.files_for``) all use the same rule, so they cannot disagree.
"""
from django.http import Http404

from main.models import ServiceRequest
from main.office.directory import requests_for, village_of


def is_unscoped(user):
    profile = getattr(user, 'profile', None)
    return user.is_superuser or (profile is not None and profile.role == 'admin')


def visible_requests(user):
    """Queryset of the requests ``user`` may see as staff."""
    if is_unscoped(user):
        return ServiceRequest.objects.all()
    village = village_of(user)
    return ServiceRequest.objects.filter(requests_for(village)) if village else ServiceRequest.objects.none()


def in_scope(user, sr):
    return is_unscoped(user) or visible_requests(user).filter(pk=sr.pk).exists()


def scoped_request_or_404(user, request_id):
    """The service request, or 404 when it belongs to another village than the staff member's."""
    sr = ServiceRequest.objects.select_related('user__profile', 'target_municipality', 'city_village').filter(pk=request_id).first()
    if sr is None or not in_scope(user, sr):
        raise Http404('Request not found')
    return sr
