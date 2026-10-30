"""Access policy: the single place that decides which role may do what.

Views declare an *action* (``@policy_required('payment.review')``); the role
matrix below is the only place that maps actions to roles. Admins (profile
role ``admin`` or Django superusers) are allowed everything.
"""
from functools import wraps

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect

from main import roles
from main.models import UserProfile

ADMIN_ROLES = set(roles.ADMIN_ROLES)

POLICY = {
    # money
    'payment.review': {'accountant', 'dehyari'},
    # service-request lifecycle
    'request.update_status': {'dehyari', 'engineer'},
    # village council
    'council.vote': {'council'},
    'council.view': {'council', 'dehyari'},
    # municipality management ("mayor_*" views)
    'mayor.manage': {'dehyari'},
    # building-permit files (step 1): the staff who see the identity papers / who may open a file
    'permit.view': {'dehyari', 'engineer', 'clerk', 'inspector'},
    'permit.open': {'dehyari', 'engineer', 'clerk'},
    'permit.sign': {'dehyari'},                  # the dehyari's own signature on the plans (step 4)
    'permit.fees': {'accountant', 'dehyari'},    # the fee rows of a permit file (step 5) and the payments received (step 6)
    # the shamim sketch the technical expert draws for an owner without a shamim file: its fee, the payment and the delivery
    'permit.sketch': {'engineer', 'dehyari'},
    # the technical expert's visit report of an unlicensed building (step 4)
    'permit.report': {'engineer', 'dehyari'},
    # the list of judiciary experts the dehyari introduces owners of unlicensed buildings to (step 5)
    'permit.experts': {'dehyari'},
    # the administrative expert's desk (letters and follow-ups of the village)
    'clerk.desk': {'clerk', 'dehyari'},
    # the admin panel (pages and JSON endpoints): admins only, so no other role is listed
    'admin.manage': set(),
    # village web-GIS map and plot archives: the village's technical expert, dehyari and administrative expert (the village match is
    # in main/gis/access.py); locking a plot out of the municipal services stays with the technical expert and the dehyari
    'gis.view': {'engineer', 'dehyari', 'clerk'},
    'gis.edit': {'engineer', 'dehyari', 'clerk'},
    'gis.lock': {'engineer', 'dehyari'},          # lock a plot out of municipal services / release it
    # technical staff dashboards and tools
    'staff.engineer': {'engineer', 'dehyari'},
    'staff.inspector': {'inspector', 'dehyari'},
    'staff.accountant': {'accountant', 'dehyari'},
    'staff.any': {'engineer', 'inspector', 'accountant', 'dehyari'},
}


def role_of(user):
    """Role of an authenticated user, or None if unknown."""
    if not user.is_authenticated:
        return None
    try:
        return user.profile.role
    except UserProfile.DoesNotExist:
        return None


def can(user, action):
    """True if ``user`` may perform ``action``."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    role = role_of(user)
    if role in ADMIN_ROLES:
        return True
    return role in POLICY[action]


def policy_required(action, api=False):
    """Guard a view with ``action``.

    ``api=True`` answers machine clients with 401/403 JSON; otherwise users are
    redirected (login / dashboard) with a message, like the old ``role_required``.
    """
    if action not in POLICY:
        raise KeyError(f'Unknown access action: {action}')

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                if api:
                    return JsonResponse({'success': False, 'error': 'Authentication required'}, status=401)
                return redirect('main:login')
            if not can(request.user, action):
                if api:
                    return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
                messages.error(request, 'شما دسترسی لازم برای این صفحه را ندارید.')
                return redirect('main:dashboard')
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator
