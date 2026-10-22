"""The administrative expert's panel (کارشناس اداری): one desk page and the reminder action."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from main.access import policy_required
from main.office import desk, letters
from main.office.appointments import jalali_label
from main.office.errors import OfficeError


@login_required
@policy_required('clerk.desk')
def clerk_dashboard(request):
    year, month = desk.parse_month(request.GET.get('m', ''))
    user = request.user
    return render(request, 'main/clerk/desk.html', {
        'greeting': desk.greeting(), 'today_label': jalali_label(timezone.localdate()),
        'stats': desk.summary(user),
        'agenda': desk.today_agenda(user), 'pending_visits': desk.pending_appointments(user),
        'inbox': letters.mailbox(user, 'inbox')[:6],
        'calendar': desk.month_grid(user, year, month),
        'follow_ups': desk.follow_ups(user),
    })


@login_required
@policy_required('clerk.desk')
@require_POST
def clerk_remind(request, request_id):
    try:
        sr = desk.remind(request.user, request_id)
        messages.success(request, f'یادآوری برای «{sr.user.get_full_name() or sr.user.username}» فرستاده شد.')
    except OfficeError as exc:
        messages.error(request, str(exc))
    return redirect('main:clerk_dashboard')
