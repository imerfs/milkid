"""Tabs of the dehyari panel (employees, requests, announcements, profile) rendered in place.

Each tab is an HTML fragment loaded into the dashboard page; actions reuse the existing
endpoints, so access rules are unchanged. Old page URLs deep-link to the matching tab.
"""
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.validators import RegexValidator, validate_email
from django import forms
from django.core.exceptions import ValidationError
from main.widgets import BirthDateField
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode

from main.access import policy_required, role_of
from main.models import Announcement, Municipality, ServiceRequest, UserProfile
from main.office import roles
from main.office.directory import requests_for
from main.office.errors import OfficeError
from main.views.office_views import change_password

TABS = ('employees', 'requests', 'permits', 'announcements', 'profile')
_MOBILE = RegexValidator(r'^09\d{9}$', 'شماره موبایل صحیح وارد کنید (مثال: 09123456789)')


def tab_redirect(request, tab):
    """Send a dehyari who opens an old page URL to the same section inside the panel."""
    if request.method == 'GET' and not request.headers.get('X-Panel') and role_of(request.user) == 'dehyari':
        return redirect(f"{reverse('main:dehyari_dashboard')}?tab={tab}")
    return None


def _employees(request):
    q = request.GET.get('q', '')
    try:
        staff, candidates = roles.staff_and_candidates(request.user, q)
        error = None
    except OfficeError as exc:
        staff, candidates, error = [], [], str(exc)
    return {
        'staff': staff, 'candidates': candidates, 'q': q.strip(), 'error': error,
        'grantable': [(r, dict(UserProfile.USER_ROLES)[r], roles.ROLE_ICONS[r]) for r in roles.GRANTABLE],
        'role_icons': roles.ROLE_ICONS,
    }


def _requests(request):
    municipality = Municipality.objects.filter(admin_user=request.user).first()
    if municipality is None:
        return {'municipality': None, 'service_requests': [], 'status_choices': ServiceRequest.STATUS_CHOICES}
    scope = ServiceRequest.objects.filter(requests_for(municipality.city_village))
    status, search = request.GET.get('status', ''), request.GET.get('search', '').strip()[:100]
    rows = scope.select_related('user', 'user__profile', 'service')
    if status in dict(ServiceRequest.STATUS_CHOICES):
        rows = rows.filter(status=status)
    if search:
        rows = rows.filter(Q(title__icontains=search) | Q(user__first_name__icontains=search) |
                           Q(user__last_name__icontains=search) | Q(tracking_code__icontains=search))
    counts = {s: scope.filter(status=s).count() for s, _ in ServiceRequest.STATUS_CHOICES}
    return {
        'municipality': municipality, 'status': status, 'search': search,
        'service_requests': Paginator(rows.order_by('-created_at'), 10).get_page(request.GET.get('page')),
        'status_choices': ServiceRequest.STATUS_CHOICES,
        'staff_members': UserProfile.objects.filter(
            role__in=['engineer', 'inspector', 'accountant'], city_village=municipality.city_village
        ).select_related('user'),
        'stats': {'total': scope.count(), **counts},
        'extra': '&' + urlencode({'status': status, 'search': search}),
    }


def _announcements(request):
    mine = Announcement.objects.filter(created_by=request.user, is_active=True).order_by('-created_at')
    return {
        'announcements': Paginator(mine, 10).get_page(request.GET.get('page')),
        'priority_choices': Announcement.PRIORITY_CHOICES,
        'role_choices': [(r, label) for r, label in UserProfile.USER_ROLES if r not in roles.PROTECTED],
    }


def _profile(request):
    return {'user_profile': request.user.profile}


def _permits(request):
    from main.office import permits
    return {'permitlist': permits.panel_rows(request.user)}


_BUILDERS = {'employees': _employees, 'requests': _requests, 'permits': _permits, 'announcements': _announcements,
             'profile': _profile}


def _save_profile(request):
    post, user = request.POST, request.user
    first, last = post.get('first_name', '').strip(), post.get('last_name', '').strip()
    email, mobile = post.get('email', '').strip(), post.get('mobile_number', '').strip()
    errors = []
    if not first or len(first) > 30:
        errors.append('نام الزامی است و نباید بیش از ۳۰ نویسه باشد.')
    if not last or len(last) > 30:
        errors.append('نام خانوادگی الزامی است و نباید بیش از ۳۰ نویسه باشد.')
    try:
        if email:
            validate_email(email)
    except ValidationError:
        errors.append('ایمیل معتبر نیست.')
    try:
        _MOBILE(mobile)
    except ValidationError as exc:
        errors.extend(exc.messages)
    birth = ''
    try:
        birth = BirthDateField(required=False).clean(post.get('birth_date'))
    except forms.ValidationError as exc:
        errors.extend(exc.messages)
    if errors:
        return JsonResponse({'success': False, 'errors': errors}, status=400)
    user.first_name, user.last_name, user.email = first, last, email
    user.save(update_fields=['first_name', 'last_name', 'email'])
    UserProfile.objects.filter(user=user).update(mobile_number=mobile, **({'birth_date': birth} if birth else {}))
    return JsonResponse({'success': True, 'message': 'پروفایل ذخیره شد.', 'full_name': user.get_full_name()})


def _save_password(request):
    from django.contrib.auth import update_session_auth_hash
    error = change_password(request.user, request.POST)
    if error:
        return JsonResponse({'success': False, 'errors': [error]}, status=400)
    update_session_auth_hash(request, request.user)
    return JsonResponse({'success': True, 'message': 'رمز عبور تغییر کرد.'})


@policy_required('mayor.manage')
def mayor_panel(request, tab):
    if tab not in TABS:
        raise Http404
    if request.method == 'POST' and tab == 'profile':
        return _save_password(request) if request.POST.get('action') == 'password' else _save_profile(request)
    if request.method != 'GET':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    context = _BUILDERS[tab](request)
    context['flash'] = list(messages.get_messages(request))
    return render(request, f'main/mayor/panel/_{tab}.html', context)
