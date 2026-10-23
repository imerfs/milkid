"""The administrative expert's panel (کارشناس اداری): one desk with its own tabs.

Everything the clerk does happens on this page: today's overview, the messenger (chats and letters), visits (requests,
weekly hours, booking a colleague) and the follow-up of requests waiting for documents. The actions below redirect back
to the right tab, so nothing sends the clerk to a page with a different look.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from main.access import policy_required
from main.models import AvailabilityRule
from main.office import appointments as svc
from main.office import desk, messenger
from main.office.appointments import jalali_label
from main.office.errors import OfficeError
from main.views.messenger_views import messenger_context

TABS = ('today', 'messages', 'visits', 'follow')


def _back(tab, **params):
    query = ''.join(f'&{k}={v}' for k, v in params.items() if v)
    return redirect(f"{reverse('main:clerk_dashboard')}?tab={tab}{query}")


def _visits_context(request):
    user = request.user
    mine = svc.my_appointments(user)
    rules = {r.weekday: r for r in AvailabilityRule.objects.filter(provider=user)}
    colleagues = svc.providers_for(user).order_by('profile__role', 'last_name')
    chosen = colleagues.filter(pk=request.GET['provider']).first() if request.GET.get('provider', '').isdigit() else None
    ctx = {
        'incoming': mine['incoming'], 'booked': mine['upcoming'],
        'hours': [{'index': i, 'name': name, 'rule': rules.get(i)} for i, name in enumerate(svc.WEEKDAYS)],
        'colleagues': colleagues, 'chosen': chosen,
    }
    if chosen is not None:
        date = svc.parse_date(request.GET.get('date'), timezone.localdate())
        ctx.update(strip=svc.day_strip(chosen), date=date, date_label=svc.jalali_label(date),
                   slots=[s for s, _ in svc.free_slots(chosen, date)])
    return ctx


@login_required
@policy_required('clerk.desk')
def clerk_dashboard(request):
    user = request.user
    tab = request.GET.get('tab') if request.GET.get('tab') in TABS else 'today'
    context = {'tab': tab, 'greeting': desk.greeting(), 'today_label': jalali_label(timezone.localdate()),
               'stats': desk.summary(user)}
    if tab == 'today':
        year, month = desk.parse_month(request.GET.get('m', ''))
        context.update(agenda=desk.today_agenda(user), pending_visits=desk.pending_appointments(user),
                       latest=messenger.threads(user)[:6], calendar=desk.month_grid(user, year, month))
    elif tab == 'messages':
        context.update(messenger_context(request), embed=False)
    elif tab == 'visits':
        context.update(_visits_context(request))
    else:
        context['follow_ups'] = desk.follow_ups(user)
    return render(request, 'main/clerk/desk.html', context)


@login_required
@policy_required('clerk.desk')
@require_POST
def clerk_remind(request, request_id):
    try:
        sr = desk.remind(request.user, request_id)
        messages.success(request, f'یادآوری برای «{sr.user.get_full_name() or sr.user.username}» فرستاده شد.')
    except OfficeError as exc:
        messages.error(request, str(exc))
    return _back('follow')


@login_required
@policy_required('clerk.desk')
@require_POST
def clerk_visit_action(request, appointment_id):
    action = request.POST.get('action', '')
    try:
        _, changed = svc.decide(request.user, appointment_id, action)
        messages.success(request, svc.MESSAGES[action] if changed else 'این عملیات قبلاً انجام شده بود.')
    except OfficeError as exc:
        messages.error(request, str(exc))
    return _back('visits')


@login_required
@policy_required('clerk.desk')
@require_POST
def clerk_hours(request):
    try:
        svc.set_rules(request.user, request.POST)
        messages.success(request, 'ساعت‌های حضور ذخیره شد.')
    except OfficeError as exc:
        messages.error(request, str(exc))
    return _back('visits')


@login_required
@policy_required('clerk.desk')
@require_POST
def clerk_book(request):
    provider = request.POST.get('provider', '')
    try:
        _, created = svc.book(request.user, provider, request.POST.get('start'), request.POST.get('subject'),
                              request.POST.get('notes'))
        messages.success(request, 'درخواست وقت ثبت شد؛ پس از تایید همکار خبر می‌گیرید.' if created
                         else 'این وقت از قبل برای شما ثبت شده است.')
        return _back('visits')
    except OfficeError as exc:
        messages.error(request, str(exc))
        return _back('visits', provider=provider, date=(request.POST.get('start') or '')[:10])
