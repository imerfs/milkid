"""The messenger: chats and official letters in one Telegram-style inbox, embedded in every panel.

The page is one component (``_messenger.html``); the panels show it in a drawer or a tab and the pieces (thread list,
thread pane, directory) are HTML fragments the component loads and swaps.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from main.models import Municipality, UserProfile
from main.office import directory, letters, messenger
from main.office.errors import OfficeError
from main.office.roles import ROLE_ICONS

CITIZEN_ROLES = ('citizen', 'owner', 'resident')


def messenger_context(request):
    """Context for ``_messenger.html`` (also used by the clerk desk, which shows the messenger inline)."""
    user = request.user
    me = directory.identity(user)
    is_citizen = user.profile.role in CITIZEN_ROLES
    return {
        'me': me, 'threads': messenger.threads(user), 'open_key': request.GET.get('open', ''),
        'new_kind': request.GET.get('new', ''), 'is_citizen': is_citizen,
        'active_org': directory.effective_org(user) if is_citizen else None,
        'unread': messenger.unread_total(user), 'sig': messenger.signature(user),
        'priorities': letters.Letter.PRIORITIES, 'embed': bool(request.GET.get('embed')),
    }


def _error(exc):
    return JsonResponse({'error': str(exc)}, status=exc.status)


@login_required
def messenger_home(request):
    return render(request, 'main/messenger/page.html', messenger_context(request))


@login_required
@require_GET
def messenger_list(request):
    rows = messenger.threads(request.user, request.GET.get('kind', 'all'), request.GET.get('q', ''),
                             request.GET.get('unread') == '1')
    return render(request, 'main/messenger/_list.html', {'threads': rows, 'open_key': request.GET.get('open', '')})


def _thread_response(request, key):
    data = messenger.open_thread(request.user, key)
    response = render(request, 'main/messenger/_thread.html', {'t': data, 'priorities': letters.Letter.PRIORITIES})
    response['X-Last-Id'] = str(data['last_id'])
    return response


@login_required
@require_GET
def messenger_thread(request, key):
    try:
        return _thread_response(request, key)
    except OfficeError as exc:
        return _error(exc)


@login_required
@require_POST
def messenger_send(request, key):
    """A line in an open thread: a chat message, or a letter written as the answer to the latest letter."""
    try:
        kind, number = messenger.parse_key(key)
        if kind == 'chat':
            messenger.send_chat(request.user, number, request.POST.get('body'))
        else:
            messenger.reply_letter(request.user, request.POST.get('parent') or number, request.POST.get('body'),
                                   request.FILES.getlist('files'))
        return _thread_response(request, key)
    except OfficeError as exc:
        return _error(exc)


@login_required
@require_POST
def messenger_new(request):
    """Start a chat with one person or send a new letter to several."""
    post = request.POST
    try:
        if post.get('kind') == 'letter':
            letter = letters.compose(
                request.user, to=post.getlist('to'), cc=post.getlist('cc'), subject=post.get('subject'),
                body=post.get('body'), priority=post.get('priority', 'normal'), confidential=post.get('confidential') == '1',
                files=request.FILES.getlist('files'), token=post.get('token') or letters.new_token())
            return JsonResponse({'key': f'l{letter.pk}'})
        ids = post.getlist('to')
        if len(ids) != 1:
            return JsonResponse({'error': 'برای گفتگو یک گیرنده انتخاب کنید.'}, status=400)
        chat = messenger.start_chat(request.user, ids[0], post.get('body'))
        return JsonResponse({'key': f'c{chat.pk}'})
    except OfficeError as exc:
        return _error(exc)


@login_required
@require_GET
def messenger_directory(request):
    """Step one: organizations; step two (``org``): the people of that organization the user may write to."""
    q = request.GET.get('q', '')
    org = Municipality.objects.filter(pk=request.GET['org']).first() if request.GET.get('org', '').isdigit() else None
    ctx = {'q': q, 'role_icons': ROLE_ICONS}
    if org is None:
        ctx['orgs'] = directory.organizations(request.user, q)
    else:
        people = directory.people_of(request.user, org)
        if q.strip():
            people = people.filter(first_name__icontains=q.strip()) | people.filter(last_name__icontains=q.strip())
        ctx.update(org=org, people=[(p, directory.identity(p)) for p in people[:60]])
    return render(request, 'main/messenger/_directory.html', ctx)


@login_required
@require_GET
def messenger_poll(request):
    return JsonResponse({'unread': messenger.unread_total(request.user), 'sig': messenger.signature(request.user)})


@login_required
def my_municipality(request):
    """A citizen picks the dehyari or shahrdari that receives their requests and letters."""
    profile = request.user.profile
    if profile.role not in CITIZEN_ROLES:
        return redirect('main:dashboard')
    q = request.GET.get('q', '')
    return render(request, 'main/messenger/municipality.html', {
        'orgs': directory.organizations(request.user, q), 'q': q, 'active': directory.effective_org(request.user),
        'home': directory.org_of(request.user), 'next': request.GET.get('next', '')})


@login_required
@require_POST
def switch_municipality(request):
    profile = request.user.profile
    if profile.role not in CITIZEN_ROLES:
        return redirect('main:dashboard')
    org = Municipality.objects.filter(pk=request.POST.get('org') or 0, status='active').first()
    if request.POST.get('org') and org is None:
        messages.error(request, 'این دهیاری یا شهرداری پیدا نشد.')
        return redirect('main:my_municipality')
    UserProfile.objects.filter(user=request.user).update(active_municipality=org)    # empty = back to the home village
    messages.success(request, f'از این پس درخواست‌ها و نامه‌های شما به «{org.name}» می‌رود.' if org
                     else 'به دهیاری خودتان برگشتید.')
    target = request.POST.get('next', '')
    return redirect(target if target.startswith('/') and not target.startswith('//') else 'main:my_municipality')
