"""Actions of the appointment system (وقت‌گیری). The section itself is drawn inside each role's panel
(``main/office/visits.py``); these views only act and send the user back to it. The old stand-alone page URLs redirect there too.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from main.office import appointments as svc
from main.office import visits
from main.office.errors import OfficeError


@login_required
def appointments(request):
    return redirect(visits.panel_url(request.user))


@login_required
def appointment_providers(request):
    return redirect(visits.panel_url(request.user))


@login_required
def appointment_book(request, provider_id):
    user = request.user
    if request.method != 'POST':
        return redirect(visits.panel_url(user, provider=provider_id, date=request.GET.get('date')))
    start = request.POST.get('start') or ''
    try:
        _, created = svc.book(user, provider_id, start, request.POST.get('subject'), request.POST.get('notes'))
    except OfficeError as exc:
        messages.error(request, str(exc))
        request.session['visit_form'] = {'start': start, 'subject': request.POST.get('subject', ''),
                                         'notes': request.POST.get('notes', '')}
        date = svc.parse_date(start[:10], timezone.localdate())
        return redirect(visits.panel_url(user, provider=provider_id, date=date.isoformat()))
    messages.success(request, 'درخواست وقت ثبت شد؛ پس از تایید خبر می‌گیرید.' if created
                     else 'این وقت از قبل برای شما ثبت شده است.')
    return redirect(visits.panel_url(user))


@login_required
@require_POST
def appointment_action(request, appointment_id):
    action = request.POST.get('action', '')
    try:
        _, changed = svc.decide(request.user, appointment_id, action)
    except OfficeError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, svc.MESSAGES[action] if changed else 'این عملیات قبلاً انجام شده بود.')
    return redirect(visits.panel_url(request.user))


@login_required
def availability(request):
    if request.method == 'POST':
        try:
            svc.set_rules(request.user, request.POST)
        except OfficeError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, 'ساعات کاری ذخیره شد.')
    return redirect(visits.panel_url(request.user))
