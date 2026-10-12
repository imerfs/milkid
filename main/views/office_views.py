"""Views of the office system: role grants, letters, appointments."""
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from main.access import policy_required
from main.office import roles
from main.office.errors import OfficeError


def _roles_page(request, status=200, error=None):
    try:
        staff, candidates = roles.staff_and_candidates(request.user, request.GET.get('q', ''))
    except OfficeError as exc:           # e.g. the dehyari has no municipality yet
        staff, candidates, error, status = [], [], error or str(exc), status if error else exc.status
    return render(request, 'main/office/roles.html', {
        'staff': staff, 'candidates': candidates, 'q': request.GET.get('q', '').strip(),
        'grantable': [(r, dict(roles.UserProfile.USER_ROLES)[r], roles.ROLE_ICONS[r]) for r in roles.GRANTABLE],
        'role_icons': roles.ROLE_ICONS, 'error': error,
    }, status=status)


@policy_required('mayor.manage')
def role_grants(request):
    """Staff of the village + search to give someone a role."""
    return _roles_page(request)


@policy_required('mayor.manage')
@require_POST
def role_grant(request):
    try:
        _, changed = roles.grant_role(request.user, request.POST.get('user_id') or 0, request.POST.get('role', ''))
    except OfficeError as exc:
        return _roles_page(request, exc.status, str(exc))
    messages.success(request, 'نقش با موفقیت اختصاص یافت.' if changed else 'این کاربر همین نقش را از قبل دارد.')
    return redirect('main:role_grants')


@policy_required('mayor.manage')
@require_POST
def role_revoke(request, user_id):
    try:
        changed = roles.revoke_role(request.user, user_id)
    except OfficeError as exc:
        return _roles_page(request, exc.status, str(exc))
    messages.success(request, 'نقش برداشته شد و کاربر به شهروند بازگشت.' if changed else 'این کاربر نقش سازمانی نداشت.')
    return redirect('main:role_grants')


@policy_required('mayor.manage')
@require_POST
def role_create_account(request):
    try:
        user, password = roles.create_staff_account(request.user, request.POST)
    except OfficeError as exc:
        return _roles_page(request, exc.status, str(exc))
    messages.success(request, f'حساب «{user.username}» ساخته شد. رمز موقت: «{password}» ' 
                              '(فقط همین بار نمایش داده می‌شود؛ آن را به کاربر بدهید تا پس از ورود تغییر دهد).')
    return redirect('main:role_grants')
