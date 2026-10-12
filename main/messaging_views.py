"""
Views مربوط به سیستم پیام‌رسانی
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone
from functools import wraps
import json

from .models import (
    UserProfile, Conversation, Message, MessageRecipient, 
    Notification, ServiceRequest, Announcement, ConversationState
)
from django.http import HttpResponse

def role_required(allowed_roles):
    """Decorator for role-based access control"""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('main:login')
            try:
                user_role = request.user.profile.role
                if user_role not in allowed_roles:
                    messages.error(request, 'شما دسترسی لازم برای این صفحه را ندارید.')
                    return redirect('main:dashboard')
            except UserProfile.DoesNotExist:
                messages.error(request, 'پروفایل کاربری یافت نشد.')
                return redirect('main:home')
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def announcements_for(role):
    """Active announcements addressed to ``role`` or to everyone.

    Filtered in Python on purpose: JSONField ``contains`` is not supported by SQLite
    (it raised NotSupportedError on every messaging page)."""
    ids = [a.id for a in Announcement.objects.filter(is_active=True).only('id', 'target_roles')
           if not a.target_roles or role in a.target_roles]
    return Announcement.objects.filter(id__in=ids)

@login_required
def messaging_dashboard(request):
    """داشبورد اصلی پیام‌رسانی"""
    user_profile = request.user.profile
    
    # دریافت مکالمات کاربر
    conversations = Conversation.objects.filter(
        participants=request.user
    ).annotate(
        message_count=Count('messages'),
        unread_count=Count('messages__recipients', 
                          filter=Q(messages__recipients__recipient=request.user, 
                                  messages__recipients__is_read=False))
    ).order_by('-updated_at')[:10]
    
    # آخرین پیام‌های دریافتی
    recent_messages = Message.objects.filter(
        conversation__participants=request.user
    ).exclude(
        sender=request.user
    ).select_related('sender', 'conversation').order_by('-created_at')[:5]
    
    # اطلاعیه‌های عمومی
    announcements = announcements_for(user_profile.role).order_by('-created_at')[:5]
    
    # آمار پیام‌رسانی
    stats = {
        'total_conversations': conversations.count(),
        'unread_messages': MessageRecipient.objects.filter(
            recipient=request.user, is_read=False
        ).count(),
        'sent_messages': Message.objects.filter(sender=request.user).count(),
        'announcements_count': announcements.count(),
    }
    
    context = {
        'user_profile': user_profile,
        'conversations': conversations,
        'recent_messages': recent_messages,
        'announcements': announcements,
        'stats': stats,
    }
    
    return render(request, 'main/messaging/dashboard.html', context)

@login_required
def conversation_list(request):
    """لیست تمام مکالمات"""
    conversations = Conversation.objects.filter(
        participants=request.user
    ).annotate(
        message_count=Count('messages'),
        unread_count=Count('messages__recipients', 
                          filter=Q(messages__recipients__recipient=request.user, 
                                  messages__recipients__is_read=False))
    ).order_by('-updated_at')

    show_archived = request.GET.get('archived') == '1'
    archived_ids = ConversationState.objects.filter(
        user=request.user, is_archived=True
    ).values_list('conversation_id', flat=True)
    if show_archived:
        conversations = conversations.filter(id__in=archived_ids)
    else:
        conversations = conversations.exclude(id__in=archived_ids)
    
    # جستجو
    search_query = request.GET.get('search', '')
    if search_query:
        conversations = conversations.filter(
            Q(subject__icontains=search_query) |
            Q(messages__body__icontains=search_query)
        ).distinct()
    
    # صفحه‌بندی
    paginator = Paginator(conversations, 15)
    page_number = request.GET.get('page')
    conversations_page = paginator.get_page(page_number)
    
    context = {
        'conversations': conversations_page,
        'search_query': search_query,
        'show_archived': show_archived,
    }
    
    return render(request, 'main/messaging/conversation_list.html', context)

@login_required
def conversation_detail(request, conversation_id):
    """جزئیات مکالمه و پیام‌ها"""
    conversation = get_object_or_404(
        Conversation, 
        id=conversation_id, 
        participants=request.user
    )
    
    # دریافت پیام‌ها
    messages_list = conversation.messages.select_related('sender').order_by('created_at')
    
    # علامت‌گذاری پیام‌ها به عنوان خوانده شده
    MessageRecipient.objects.filter(
        message__conversation=conversation,
        recipient=request.user,
        is_read=False
    ).update(is_read=True, read_at=timezone.now())
    
    # ارسال پیام جدید
    if request.method == 'POST':
        message_body = request.POST.get('message_body', '').strip()
        if message_body:
            # ایجاد پیام جدید
            new_message = Message.objects.create(
                conversation=conversation,
                sender=request.user,
                body=message_body
            )
            
            # ایجاد MessageRecipient برای سایر شرکت‌کنندگان
            muted_ids = set(ConversationState.objects.filter(
                conversation=conversation, is_muted=True
            ).values_list('user_id', flat=True))
            for participant in conversation.participants.exclude(id=request.user.id):
                MessageRecipient.objects.create(
                    message=new_message,
                    recipient=participant,
                    is_read=False
                )
                
                if participant.id in muted_ids:
                    continue
                # ایجاد نوتیفیکیشن
                Notification.objects.create(
                    user=participant,
                    notification_type='new_message',
                    title='پیام جدید',
                    message=f'پیام جدیدی از {request.user.get_full_name()} دریافت کردید.',
                    related_request=conversation.related_request
                )
            
            # به‌روزرسانی زمان مکالمه
            conversation.updated_at = timezone.now()
            conversation.save()
            
            messages.success(request, 'پیام شما ارسال شد.')
            return redirect('main:conversation_detail', conversation_id=conversation.id)
    
    state = ConversationState.objects.filter(conversation=conversation, user=request.user).first()
    context = {
        'conversation': conversation,
        'is_muted': bool(state and state.is_muted),
        'messages': messages_list,
        'participants': conversation.participants.exclude(id=request.user.id),
    }
    
    return render(request, 'main/messaging/conversation_detail.html', context)

@login_required
def start_conversation(request):
    """شروع مکالمه جدید"""
    if request.method == 'POST':
        recipient_id = request.POST.get('recipient_id')
        subject = request.POST.get('subject', '').strip()
        message_body = request.POST.get('message_body', '').strip()
        related_request_id = request.POST.get('related_request_id')
        
        if not recipient_id or not subject or not message_body:
            messages.error(request, 'لطفاً تمام فیلدهای ضروری را پر کنید.')
            return redirect('main:start_conversation')
        
        try:
            recipient = User.objects.get(id=recipient_id)
            
            # بررسی وجود مکالمه قبلی
            existing_conversation = Conversation.objects.filter(
                participants=request.user
            ).filter(
                participants=recipient
            ).filter(
                subject=subject
            ).first()
            
            if existing_conversation:
                messages.info(request, 'مکالمه‌ای با این موضوع قبلاً وجود دارد.')
                return redirect('main:conversation_detail', conversation_id=existing_conversation.id)
            
            # ایجاد مکالمه جدید
            conversation = Conversation.objects.create(subject=subject)
            
            # اضافه کردن شرکت‌کنندگان
            conversation.participants.add(request.user, recipient)
            
            # اضافه کردن درخواست مرتبط (اگر وجود دارد)
            if related_request_id:
                try:
                    related_request = ServiceRequest.objects.get(id=related_request_id)
                    conversation.related_request = related_request
                    conversation.save()
                except ServiceRequest.DoesNotExist:
                    pass
            
            # ایجاد پیام اول
            first_message = Message.objects.create(
                conversation=conversation,
                sender=request.user,
                body=message_body
            )
            
            # ایجاد MessageRecipient
            MessageRecipient.objects.create(
                message=first_message,
                recipient=recipient,
                is_read=False
            )
            
            # ایجاد نوتیفیکیشن
            Notification.objects.create(
                user=recipient,
                notification_type='new_message',
                title='مکالمه جدید',
                message=f'مکالمه جدیدی با موضوع "{subject}" از {request.user.get_full_name()} دریافت کردید.',
                related_request=conversation.related_request
            )
            
            messages.success(request, 'مکالمه جدید ایجاد شد.')
            return redirect('main:conversation_detail', conversation_id=conversation.id)
            
        except User.DoesNotExist:
            messages.error(request, 'کاربر مورد نظر یافت نشد.')
    
    # دریافت لیست کاربران قابل پیام
    user_profile = request.user.profile
    
    # کاربران قابل پیام بر اساس نقش
    if user_profile.role in ['citizen', 'owner', 'resident']:
        # شهروندان می‌توانند به کارمندان پیام بدهند
        available_users = User.objects.filter(
            profile__role__in=['dehyari', 'engineer', 'inspector', 'accountant', 'council', 'admin'],
            profile__city_village=user_profile.city_village,
            is_active=True
        ).select_related('profile')
    
    elif user_profile.role in ['dehyari', 'engineer', 'inspector', 'accountant', 'council']:
        # کارمندان می‌توانند به همه پیام بدهند
        available_users = User.objects.filter(
            profile__city_village=user_profile.city_village,
            is_active=True
        ).exclude(id=request.user.id).select_related('profile')
    
    elif user_profile.role == 'admin':
        # مدیر می‌تواند به همه پیام بدهد
        available_users = User.objects.filter(
            is_active=True
        ).exclude(id=request.user.id).select_related('profile')
    
    else:
        available_users = User.objects.none()
    
    # درخواست‌های مرتبط برای انتخاب
    related_requests = ServiceRequest.objects.filter(
        Q(user=request.user) | Q(assigned_to=request.user)
    ).order_by('-created_at')[:10]
    
    context = {
        'available_users': available_users,
        'related_requests': related_requests,
    }
    
    return render(request, 'main/messaging/start_conversation.html', context)

@login_required
@role_required(['dehyari', 'admin'])
def create_announcement(request):
    """ایجاد اطلاعیه عمومی (فقط دهیار و مدیر)"""
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        content = request.POST.get('content', '').strip()
        priority = request.POST.get('priority', 'medium')
        target_roles = request.POST.getlist('target_roles')
        expires_at = request.POST.get('expires_at')
        
        if not title or not content:
            messages.error(request, 'لطفاً عنوان و متن اطلاعیه را وارد کنید.')
            return redirect('main:create_announcement')
        
        # ایجاد اطلاعیه
        announcement = Announcement.objects.create(
            title=title,
            content=content,
            priority=priority,
            target_roles=target_roles if target_roles else [],
            created_by=request.user,
            expires_at=expires_at if expires_at else None
        )
        
        # ایجاد نوتیفیکیشن برای کاربران هدف
        if target_roles:
            target_users = User.objects.filter(
                profile__role__in=target_roles,
                is_active=True
            )
        else:
            # همه کاربران
            target_users = User.objects.filter(is_active=True)
        
        # محدود کردن به شهر/روستای کاربر (اگر دهیار باشد)
        if request.user.profile.role == 'dehyari':
            target_users = target_users.filter(
                profile__city_village=request.user.profile.city_village
            )
        
        # ایجاد نوتیفیکیشن‌ها
        notifications = []
        for user in target_users.exclude(id=request.user.id):
            notifications.append(
                Notification(
                    user=user,
                    notification_type='admin_notice',
                    title=f'اطلاعیه جدید: {title}',
                    message=content[:200] + ('...' if len(content) > 200 else '')
                )
            )
        
        # ایجاد دسته‌جمعی نوتیفیکیشن‌ها
        Notification.objects.bulk_create(notifications)
        
        messages.success(request, f'اطلاعیه برای {len(notifications)} کاربر ارسال شد.')
        return redirect('main:announcement_list')
    
    # نقش‌های قابل انتخاب
    role_choices = UserProfile.USER_ROLES
    
    context = {
        'role_choices': role_choices,
    }
    
    return render(request, 'main/messaging/create_announcement.html', context)

@login_required
def announcement_list(request):
    """لیست اطلاعیه‌ها"""
    user_profile = request.user.profile
    
    # اطلاعیه‌های مربوط به کاربر
    announcements = announcements_for(user_profile.role).order_by('-created_at')
    
    # فیلتر اولویت
    priority_filter = request.GET.get('priority')
    if priority_filter:
        announcements = announcements.filter(priority=priority_filter)
    
    # صفحه‌بندی
    paginator = Paginator(announcements, 10)
    page_number = request.GET.get('page')
    announcements_page = paginator.get_page(page_number)
    
    context = {
        'announcements': announcements_page,
        'priority_filter': priority_filter,
        'priority_choices': Announcement.PRIORITY_CHOICES,
    }
    
    return render(request, 'main/messaging/announcement_list.html', context)

@login_required
def announcement_detail(request, announcement_id):
    """جزئیات اطلاعیه"""
    announcement = get_object_or_404(Announcement, id=announcement_id, is_active=True)
    
    # بررسی دسترسی
    user_profile = request.user.profile
    if announcement.target_roles and user_profile.role not in announcement.target_roles:
        messages.error(request, 'شما دسترسی لازم برای مشاهده این اطلاعیه را ندارید.')
        return redirect('main:announcement_list')
    
    related = announcements_for(user_profile.role).exclude(id=announcement.id)
    related = related.order_by('-created_at')[:5]

    context = {
        'announcement': announcement,
        'related_announcements': related,
        'can_manage': _can_manage_announcement(request.user, announcement),
    }
    
    return render(request, 'main/messaging/announcement_detail.html', context)

def _can_manage_announcement(user, announcement):
    return announcement.created_by_id == user.id or user.profile.role == 'admin'


@login_required
@require_http_methods(["GET", "POST"])
def announcement_edit(request, announcement_id):
    """ویرایش اطلاعیه (سازنده یا مدیر)"""
    announcement = get_object_or_404(Announcement, id=announcement_id, is_active=True)
    if not _can_manage_announcement(request.user, announcement):
        messages.error(request, 'شما اجازه ویرایش این اطلاعیه را ندارید.')
        return redirect('main:announcement_detail', announcement_id=announcement.id)

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        content = request.POST.get('content', '').strip()
        priority = request.POST.get('priority', announcement.priority)
        if not title or not content:
            messages.error(request, 'لطفاً عنوان و متن اطلاعیه را وارد کنید.')
        elif priority not in dict(Announcement.PRIORITY_CHOICES):
            messages.error(request, 'اولویت نامعتبر است.')
        else:
            announcement.title = title
            announcement.content = content
            announcement.priority = priority
            announcement.target_roles = request.POST.getlist('target_roles')
            announcement.expires_at = request.POST.get('expires_at') or None
            announcement.save()
            messages.success(request, 'اطلاعیه ویرایش شد.')
            return redirect('main:announcement_detail', announcement_id=announcement.id)

    return render(request, 'main/messaging/edit_announcement.html', {
        'announcement': announcement,
        'role_choices': UserProfile.USER_ROLES,
        'expires_value': announcement.expires_at.strftime('%Y-%m-%dT%H:%M') if announcement.expires_at else '',
    })


@login_required
@require_http_methods(["POST"])
def announcement_delete(request, announcement_id):
    """حذف اطلاعیه (غیرفعال‌سازی؛ سازنده یا مدیر)"""
    announcement = get_object_or_404(Announcement, id=announcement_id, is_active=True)
    if not _can_manage_announcement(request.user, announcement):
        return JsonResponse({'success': False, 'error': 'دسترسی ندارید'}, status=403)
    announcement.is_active = False
    announcement.save(update_fields=['is_active'])
    return JsonResponse({'success': True, 'redirect': reverse('main:announcement_list')})


def _own_conversation(request, conversation_id):
    return get_object_or_404(Conversation, id=conversation_id, participants=request.user)


def _toggle_state(request, conversation_id, field):
    conversation = _own_conversation(request, conversation_id)
    state, _ = ConversationState.objects.get_or_create(conversation=conversation, user=request.user)
    setattr(state, field, not getattr(state, field))
    state.save(update_fields=[field])
    return JsonResponse({'success': True, field: getattr(state, field)})


@login_required
@require_http_methods(["POST"])
def conversation_mute(request, conversation_id):
    """بی‌صدا/فعال کردن اعلان‌های مکالمه"""
    return _toggle_state(request, conversation_id, 'is_muted')


@login_required
@require_http_methods(["POST"])
def conversation_archive(request, conversation_id):
    """بایگانی/خروج از بایگانی مکالمه"""
    return _toggle_state(request, conversation_id, 'is_archived')


@login_required
@require_http_methods(["POST"])
def conversation_leave(request, conversation_id):
    """ترک مکالمه"""
    conversation = _own_conversation(request, conversation_id)
    conversation.participants.remove(request.user)
    ConversationState.objects.filter(conversation=conversation, user=request.user).delete()
    return JsonResponse({'success': True, 'redirect': reverse('main:conversation_list')})


@login_required
@require_http_methods(["GET"])
def conversation_export(request, conversation_id):
    """دانلود مکالمه به صورت فایل متنی"""
    conversation = _own_conversation(request, conversation_id)
    lines = [f'موضوع: {conversation.subject}', '=' * 40]
    for m in conversation.messages.select_related('sender').order_by('created_at'):
        stamp = timezone.localtime(m.created_at).strftime('%Y-%m-%d %H:%M')
        lines.append(f'[{stamp}] {m.sender.get_full_name() or m.sender.username}:')
        lines.append(m.body)
        lines.append('')
    response = HttpResponse('\n'.join(lines), content_type='text/plain; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="conversation-{conversation.id}.txt"'
    return response


# API Endpoints برای AJAX

@login_required
@require_http_methods(["GET"])
def api_unread_count(request):
    """تعداد پیام‌های خوانده نشده"""
    unread_count = MessageRecipient.objects.filter(
        recipient=request.user,
        is_read=False
    ).count()
    
    return JsonResponse({'unread_count': unread_count})

@login_required
@require_http_methods(["POST"])
def api_mark_message_read(request, message_id):
    """علامت‌گذاری پیام به عنوان خوانده شده"""
    try:
        message_recipient = MessageRecipient.objects.get(
            message_id=message_id,
            recipient=request.user,
            is_read=False
        )
        message_recipient.is_read = True
        message_recipient.read_at = timezone.now()
        message_recipient.save()
        
        return JsonResponse({'success': True})
    except MessageRecipient.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'پیام یافت نشد'})

@login_required
@require_http_methods(["POST"])
def api_send_quick_message(request):
    """ارسال سریع پیام"""
    try:
        data = json.loads(request.body)
        recipient_id = data.get('recipient_id')
        message_body = data.get('message_body', '').strip()
        
        if not recipient_id or not message_body:
            return JsonResponse({'success': False, 'error': 'اطلاعات ناکافی'})
        
        recipient = User.objects.get(id=recipient_id)
        
        # ایجاد مکالمه جدید یا استفاده از موجود
        conversation, created = Conversation.objects.get_or_create(
            subject=f'پیام سریع از {request.user.get_full_name()}',
            defaults={'created_at': timezone.now()}
        )
        
        if created:
            conversation.participants.add(request.user, recipient)
        
        # ایجاد پیام
        message = Message.objects.create(
            conversation=conversation,
            sender=request.user,
            body=message_body
        )
        
        # ایجاد MessageRecipient
        MessageRecipient.objects.create(
            message=message,
            recipient=recipient,
            is_read=False
        )
        
        # ایجاد نوتیفیکیشن
        Notification.objects.create(
            user=recipient,
            notification_type='new_message',
            title='پیام جدید',
            message=f'پیام جدیدی از {request.user.get_full_name()} دریافت کردید.'
        )
        
        return JsonResponse({'success': True, 'conversation_id': conversation.id})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})