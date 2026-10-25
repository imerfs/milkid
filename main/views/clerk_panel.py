"""The administrative expert's panel (کارشناس اداری): one desk with its own tabs.

Everything the clerk does happens on this page: today's overview, the messenger (chats and letters) and the follow-up of
requests waiting for documents. (Appointments are for citizens, the technical staff and the council: they live in those
panels.) The actions below redirect back to the right tab, so nothing sends the clerk to a page with a different look.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from main.access import policy_required
from main.office import desk, messenger
from main.office.appointments import jalali_label
from main.office.errors import OfficeError
from main.views.messenger_views import messenger_context

TABS = ('today', 'messages', 'follow')


def _back(tab, **params):
    query = ''.join(f'&{k}={v}' for k, v in params.items() if v)
    return redirect(f"{reverse('main:clerk_dashboard')}?tab={tab}{query}")


@login_required
@policy_required('clerk.desk')
def clerk_dashboard(request):
    user = request.user
    tab = request.GET.get('tab') if request.GET.get('tab') in TABS else 'today'
    context = {'tab': tab, 'greeting': desk.greeting(), 'today_label': jalali_label(timezone.localdate()),
               'stats': desk.summary(user)}
    if tab == 'today':
        context['latest'] = messenger.threads(user)[:6]
    elif tab == 'messages':
        context.update(messenger_context(request), embed=False)
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
