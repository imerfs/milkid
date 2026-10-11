"""Admin oversight of official letters and chats (read-only)."""
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render

from main.access import policy_required
from main.models import Conversation, Message
from main.models_office import Letter

PER_PAGE = 25


@policy_required('admin.manage')
def admin_monitoring(request):
    tab = 'chats' if request.GET.get('tab') == 'chats' else 'letters'
    q = request.GET.get('q', '').strip()
    if tab == 'letters':
        rows = Letter.objects.filter(status='sent').select_related('sender').prefetch_related('recipients__user')
        if q:
            rows = rows.filter(Q(subject__icontains=q) | Q(body__icontains=q) | Q(village__icontains=q) |
                               Q(sender__username__icontains=q) | Q(sender__last_name__icontains=q) |
                               Q(recipients__user__username__icontains=q) |
                               Q(recipients__user__last_name__icontains=q)).distinct()
    else:
        rows = Conversation.objects.annotate(message_count=Count('messages')).prefetch_related('participants').order_by('-updated_at')
        if q:
            # subqueries, not joins: a join would make message_count count only the matching messages
            rows = rows.filter(Q(subject__icontains=q) |
                               Q(id__in=Message.objects.filter(body__icontains=q).values('conversation')) |
                               Q(id__in=Conversation.participants.through.objects.filter(
                                   Q(user__username__icontains=q) | Q(user__last_name__icontains=q)
                               ).values('conversation')))
    page = Paginator(rows, PER_PAGE).get_page(request.GET.get('page'))
    return render(request, 'main/admin/monitoring.html', {'tab': tab, 'q': q, 'page': page})


@policy_required('admin.manage')
def admin_monitoring_letter(request, letter_id):
    letter = get_object_or_404(
        Letter.objects.select_related('sender').prefetch_related('recipients__user', 'attachments'),
        id=letter_id, status='sent')
    return render(request, 'main/admin/monitoring_detail.html', {'kind': 'letter', 'letter': letter})


@policy_required('admin.manage')
def admin_monitoring_chat(request, conversation_id):
    chat = get_object_or_404(Conversation.objects.prefetch_related('participants'), id=conversation_id)
    return render(request, 'main/admin/monitoring_detail.html',
                  {'kind': 'chat', 'chat': chat, 'chat_messages': chat.messages.select_related('sender')})
