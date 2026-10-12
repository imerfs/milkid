"""Views of the office system: role grants, letters, appointments."""
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
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
        user = roles.create_staff_account(request.user, request.POST)
    except OfficeError as exc:
        return _roles_page(request, exc.status, str(exc))
    messages.success(request, f'حساب «{user.username}» ساخته شد. رمز اولیه همان کد ملی کاربر است و '
                              'کاربر در اولین ورود باید آن را تغییر دهد.')
    return redirect('main:role_grants')


@login_required
def password_change(request):
    """Change own password; also the forced first-login step for accounts created by a dehyari."""
    user, error = request.user, None
    if request.method == 'POST':
        old, new = request.POST.get('old_password', ''), request.POST.get('new_password', '')
        if not user.check_password(old):
            error = 'رمز فعلی درست نیست.'
        elif new == old or new == user.profile.national_id:
            error = 'رمز جدید نباید با رمز قبلی یا کد ملی یکسان باشد.'
        elif new != request.POST.get('new_password2', ''):
            error = 'تکرار رمز جدید یکسان نیست.'
        else:
            try:
                validate_password(new, user)
            except ValidationError as exc:
                error = ' '.join(exc.messages)
        if error is None:
            user.set_password(new)
            user.save(update_fields=['password'])
            user.profile.must_change_password = False
            user.profile.save(update_fields=['must_change_password'])
            update_session_auth_hash(request, user)
            messages.success(request, 'رمز عبور شما تغییر کرد.')
            return redirect('main:home')
    return render(request, 'main/password_change.html', {'error': error,
                  'forced': user.profile.must_change_password}, status=400 if error else 200)
