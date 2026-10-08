"""Access policy: the single place that decides which role may do what.

Views declare an *action* (``@policy_required('payment.review')``); the role
matrix below is the only place that maps actions to roles. Admins (profile
role ``admin`` or Django superusers) are allowed everything.
"""
from functools import wraps

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect

from main.models import UserProfile

ADMIN_ROLES = {'admin'}

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
