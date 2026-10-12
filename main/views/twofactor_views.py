"""Two-step login: the verify page every 2FA user passes once per session, and the admin's setup actions."""
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from main import twofactor
from main.access import policy_required
from main.models import TwoFactorDevice

audit = logging.getLogger('django.security.twofactor')


def _accept(request, device, code):
    step = twofactor.matching_step(device.secret, code, last_step=device.last_step)
    if step is None:
        return False
    device.last_step = step
    device.save(update_fields=['last_step'])
    request.session[twofactor.SESSION_KEY] = True
    return True


@login_required
def two_factor_verify(request):
    device = twofactor.confirmed_device(request.user)
    if device is None or request.session.get(twofactor.SESSION_KEY):
        return redirect('main:dashboard')
    if request.method == 'POST':
        if _accept(request, device, request.POST.get('code')):
            audit.info('2fa: %s passed the second step', request.user.username)
            target = request.POST.get('next', '')
            if url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                return redirect(target)
            return redirect('main:dashboard')
        audit.warning('2fa: wrong code for %s', request.user.username)
        messages.error(request, 'کد واردشده درست نیست یا منقضی شده است.')
    return render(request, 'registration/two_factor_verify.html', {'next': request.GET.get('next', '')})


def _back():
    return redirect('/dashboard/admin/server/?tab=security')


@policy_required('admin.manage')
@require_POST
def admin_two_factor_start(request):
    if twofactor.confirmed_device(request.user):
        messages.error(request, 'ورود دو مرحله‌ای از قبل فعال است.')
    else:
        TwoFactorDevice.objects.update_or_create(
            user=request.user, defaults={'secret': twofactor.new_secret(), 'confirmed': False, 'last_step': None})
    return _back()


@policy_required('admin.manage')
@require_POST
def admin_two_factor_confirm(request):
    device = TwoFactorDevice.objects.filter(user=request.user, confirmed=False).first()
    if device is not None and _accept(request, device, request.POST.get('code')):
        device.confirmed = True
        device.save(update_fields=['confirmed'])
        audit.warning('2fa: enabled by %s', request.user.username)
        messages.success(request, 'ورود دو مرحله‌ای فعال شد.')
    else:
        messages.error(request, 'کد درست نیست؛ ساعت گوشی را بررسی کنید و دوباره امتحان کنید.')
    return _back()


@policy_required('admin.manage')
@require_POST
def admin_two_factor_disable(request):
    device = twofactor.confirmed_device(request.user)
    if device is not None and _accept(request, device, request.POST.get('code')):
        device.delete()
        audit.warning('2fa: disabled by %s', request.user.username)
        messages.success(request, 'ورود دو مرحله‌ای غیرفعال شد.')
    else:
        messages.error(request, 'برای غیرفعال کردن، کد فعلی برنامه را درست وارد کنید.')
    return _back()
