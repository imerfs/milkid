"""Views of the official-letters system (مکاتبات اداری)."""
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from main.models import Letter, LetterAttachment
from main.office import letters
from main.office.errors import OfficeError

BOXES = {
    'inbox': ('صندوق ورودی', 'fa-inbox'),
    'sent': ('ارسال‌شده‌ها', 'fa-paper-plane'),
    'drafts': ('پیش‌نویس‌ها', 'fa-file-pen'),
    'archive': ('بایگانی', 'fa-box-archive'),
}


def _token(raw):
    try:
        return str(uuid.UUID(str(raw)))
    except (ValueError, AttributeError):
        return None


def _error_page(request, exc):
    return render(request, 'main/office/letter_missing.html', {'error': str(exc)}, status=exc.status)


def _list_page(request, box):
    unread_only = request.GET.get('unread') == '1'
    page = Paginator(letters.mailbox(request.user, box, q=request.GET.get('q', ''), unread=unread_only),
                     20).get_page(request.GET.get('page'))
    return render(request, 'main/office/letter_list.html', {
        'box': box, 'boxes': BOXES, 'page': page, 'q': request.GET.get('q', ''), 'unread_only': unread_only,
        'unread': letters.unread_count(request.user),
    })


@login_required
def letters_inbox(request):
    from main.views.citizen_panel import panel_tab_redirect
    if (moved := panel_tab_redirect(request, 'messages')):
        return moved
    return _list_page(request, 'inbox')


@login_required
def letters_sent(request):
    return _list_page(request, 'sent')


@login_required
def letters_drafts(request):
    return _list_page(request, 'drafts')


@login_required
def letters_archive(request):
    return _list_page(request, 'archive')


def _compose_page(request, *, data=None, parent=None, error=None, status=200):
    data = data or {}
    people = list(letters.allowed_recipients(request.user).order_by('profile__role', 'last_name')[:300])
    return render(request, 'main/office/letter_compose.html', {
        'people': people, 'parent': parent, 'error': error, 'data': data,
        'token': data.get('token') or letters.new_token(), 'priorities': Letter.PRIORITIES,
        'selected_to': {str(i) for i in data.get('to', [])}, 'selected_cc': {str(i) for i in data.get('cc', [])},
        'unread': letters.unread_count(request.user), 'boxes': BOXES, 'box': 'compose',
    }, status=status)


def _handle_compose(request, parent=None):
    data = {'to': request.POST.getlist('to'), 'cc': request.POST.getlist('cc'),
            'subject': request.POST.get('subject', ''), 'body': request.POST.get('body', ''),
            'priority': request.POST.get('priority', 'normal'),
            'confidential': request.POST.get('confidential') == 'on', 'token': _token(request.POST.get('token'))}
    if parent is not None and not data['to']:
        data['to'] = [parent.sender_id]          # a reply goes back to the sender unless changed
    try:
        letter = letters.compose(
            request.user, to=data['to'], cc=data['cc'], subject=data['subject'], body=data['body'],
            priority=data['priority'], confidential=data['confidential'],
            files=request.FILES.getlist('attachments'), parent=parent, token=data['token'],
            send=request.POST.get('action') != 'draft')
    except OfficeError as exc:
        return _compose_page(request, data=data, parent=parent, error=str(exc), status=exc.status)
    messages.success(request, 'نامه ارسال شد.' if letter.status == 'sent' else 'پیش‌نویس ذخیره شد.')
    return redirect('main:letter_detail', letter_id=letter.id)


@login_required
def letter_compose(request):
    if request.method == 'POST':
        return _handle_compose(request)
    return _compose_page(request)


@login_required
def letter_reply(request, letter_id):
    try:
        parent = letters.get_for(request.user, letter_id)
    except OfficeError as exc:
        return _error_page(request, exc)
    if parent.status != 'sent':
        return render(request, 'main/office/letter_missing.html', {'error': 'به پیش‌نویس نمی‌توان پاسخ داد.'}, status=400)
    if request.method == 'POST':
        return _handle_compose(request, parent=parent)
    subject = parent.subject if parent.subject.startswith('پاسخ:') else f'پاسخ: {parent.subject}'
    return _compose_page(request, parent=parent,
                         data={'to': [parent.sender_id], 'subject': subject, 'priority': parent.priority})


@login_required
def letter_detail(request, letter_id):
    try:
        letter = letters.get_for(request.user, letter_id)
    except OfficeError as exc:
        return _error_page(request, exc)
    letters.open_letter(request.user, letter)
    return render(request, 'main/office/letter_detail.html', {
        'letter': letter, 'recipients': letter.recipients.select_related('user', 'user__profile'),
        'attachments': letter.attachments.all(), 'mine': letter.recipients.filter(user=request.user).first(),
        'replies': letters.visible_to(request.user).filter(parent=letter),
        'is_sender': letter.sender_id == request.user.id,
        'unread': letters.unread_count(request.user), 'boxes': BOXES, 'box': 'detail',
    })


@login_required
@require_POST
def letter_send(request, letter_id):
    try:
        letter, changed = letters.send_draft(request.user, letter_id)
    except OfficeError as exc:
        return _error_page(request, exc)
    messages.success(request, 'نامه ارسال شد.' if changed else 'این نامه قبلاً ارسال شده است.')
    return redirect('main:letter_detail', letter_id=letter.id)


@login_required
@require_POST
def letter_archive(request, letter_id):
    try:
        archived = letters.toggle_archive(request.user, letter_id)
    except OfficeError as exc:
        return _error_page(request, exc)
    messages.success(request, 'نامه بایگانی شد.' if archived else 'نامه به صندوق ورودی برگشت.')
    return redirect('main:letters_archive' if archived else 'main:letters_inbox')


@login_required
def letter_attachment(request, attachment_id):
    attachment = get_object_or_404(LetterAttachment, pk=attachment_id)
    try:
        letters.get_for(request.user, attachment.letter_id)
    except OfficeError as exc:
        return _error_page(request, exc)
    return FileResponse(attachment.file.open('rb'), as_attachment=True, filename=attachment.original_name)
