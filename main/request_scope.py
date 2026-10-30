"""Village scope of a staff member over service requests.

A dehyari / expert / inspector may only open and act on requests of his own village (the same match the expert dashboard
lists). Admins see everything. Staff whose profile names no village see no request at all.
"""
from django.http import Http404

from main.models import ServiceRequest


def _village_of(user):
    profile = getattr(user, 'profile', None)
    if profile is None:
        return ''
    return (profile.city_village or profile.city_village_name or '').strip()


def request_villages(sr):
    """Every village name the request is filed under (target municipality, chosen village, requester's village)."""
    names = set()
    if sr.target_municipality_id:
        names.add(sr.target_municipality.city_village)
    if sr.city_village_id:
        names.add(sr.city_village.name)
    owner = getattr(sr.user, 'profile', None)
    if owner is not None:
        names.update([owner.city_village, owner.city_village_name])
    return {n.strip() for n in names if n}


def in_scope(user, sr):
    if user.is_superuser:
        return True
    profile = getattr(user, 'profile', None)
    if profile is not None and profile.role == 'admin':
        return True
    village = _village_of(user)
    if not village:             # staff whose profile names no village see nothing until an admin sets one
        return False
    return village in request_villages(sr)


def scoped_request_or_404(user, request_id):
    """The service request, or 404 when it belongs to another village than the staff member's."""
    sr = ServiceRequest.objects.select_related('user__profile', 'target_municipality', 'city_village').filter(
        pk=request_id).first()
    if sr is None or not in_scope(user, sr):
        raise Http404('Request not found')
    return sr
