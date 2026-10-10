"""Views of the appointment system (وقت‌دهی)."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from main.access import policy_required
from main.models import AvailabilityRule
from main.office import appointments as svc
from main.office.errors import OfficeError
from main.office.roles import ROLE_ICONS


def _error_page(request, exc):
    return render(request, 'main/office/appointment_error.html', {'error': str(exc)}, status=exc.status)


@login_required
def appointments(request):
    return render(request, 'main/office/appointments.html', svc.my_appointments(request.user))


@login_required
def appointment_providers(request):
    people = svc.providers_for(request.user).order_by('profile__role', 'last_name')
    cards = []
    for person in people:
        has_hours = AvailabilityRule.objects.filter(provider=person).exists()
        cards.append({'user': person, 'has_hours': has_hours, 'icon': {**ROLE_ICONS, 'dehyari': 'fa-user-tie'}.get(person.profile.role, 'fa-user')})
    return render(request, 'main/office/appointment_providers.html', {'cards': cards})


def _book_page(request, provider, date, error=None, status=200, form=None):
    return render(request, 'main/office/appointment_book.html', {
        'provider': provider, 'strip': svc.day_strip(provider), 'date': date,
        'date_label': svc.jalali_label(date), 'slots': [s for s, _ in svc.free_slots(provider, date)],
        'error': error, 'form': form or {},
    }, status=status)


@login_required
def appointment_book(request, provider_id):
    provider = svc.providers_for(request.user).filter(pk=provider_id).first()
    if request.method == 'POST':
        try:
            appointment, created = svc.book(request.user, provider_id, request.POST.get('start'),
                                            request.POST.get('subject'), request.POST.get('notes'))
        except OfficeError as exc:
            if provider is None:
                return _error_page(request, exc)
            date = svc.parse_date((request.POST.get('start') or '')[:10], timezone.localdate())
            return _book_page(request, provider, date, str(exc), exc.status, request.POST)
        messages.success(request, 'درخواست وقت ثبت شد؛ پس از تایید کارمند خبر می‌گیرید.' if created
                         else 'این وقت از قبل برای شما ثبت شده است.')
        return redirect('main:appointments')
    if provider is None:
        return _error_page(request, svc.NotFound('کارمند مورد نظر پیدا نشد.'))
    return _book_page(request, provider, svc.parse_date(request.GET.get('date'), timezone.localdate()))


@login_required
@require_POST
def appointment_action(request, appointment_id):
    try:
        appointment, changed = svc.decide(request.user, appointment_id, request.POST.get('action', ''))
    except OfficeError as exc:
        return _error_page(request, exc)
    messages.success(request, svc.MESSAGES[request.POST['action']] if changed else 'این عملیات قبلاً انجام شده بود.')
    return redirect('main:appointments')


@policy_required('office.provide')
def availability(request):
    error = status = None
    if request.method == 'POST':
        try:
            svc.set_rules(request.user, request.POST)
        except OfficeError as exc:
            error, status = str(exc), exc.status
        else:
            messages.success(request, 'ساعات کاری ذخیره شد.')
            return redirect('main:availability')
    rules = {r.weekday: r for r in AvailabilityRule.objects.filter(provider=request.user)}
    rows = [{'index': i, 'name': name, 'rule': rules.get(i)} for i, name in enumerate(svc.WEEKDAYS)]
    return render(request, 'main/office/availability.html', {'rows': rows, 'error': error}, status=status or 200)
