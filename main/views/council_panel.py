"""Council panel pieces that live inside the single-page council dashboard: polls, meetings, messages, settings."""
import re
from datetime import datetime, timedelta

import jdatetime
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from main.access import policy_required
from main.accounting.parse import digits, parse_jalali
from main.models import (Conversation, CouncilMeeting, CouncilPoll, CouncilPollVote, Message, MessageRecipient,
                         Notification, UserProfile)
from main.office.errors import Invalid

__all__ = ['council_poll_create', 'council_poll_vote', 'council_poll_close', 'council_meeting_save',
           'council_meeting_cancel', 'council_message_new', 'council_message_reply', 'council_settings_save']

PANEL_ROLES = ('council', 'dehyari')
MOBILE = re.compile(r'^09\d{9}$')
MONTHS = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند']


def village_of(user):
    return (user.profile.city_village or '').strip()


def panel_url(tab, **params):
    query = '&'.join([f'tab={tab}'] + [f'{k}={v}' for k, v in params.items()])
    return f"{reverse('main:council_dashboard')}?{query}"


def colleagues(user):
    """Council members and the dehyar of the same village (excluding the user)."""
    return User.objects.filter(profile__role__in=PANEL_ROLES, profile__city_village=village_of(user), is_active=True).exclude(id=user.id)


def polls_for(user):
    return CouncilPoll.objects.filter(village=village_of(user))


def meetings_for(user):
    return CouncilMeeting.objects.filter(village=village_of(user))


def say(request, ok, text):
    (messages.success if ok else messages.error)(request, text)


@policy_required('council.vote')
@require_POST
def council_poll_create(request):
    title = request.POST.get('title', '').strip()
    description = request.POST.get('description', '').strip()
    if not title or len(title) > 200 or len(description) > 2000:
        say(request, False, 'موضوع رای‌گیری را وارد کنید (حداکثر ۲۰۰ نویسه) و توضیحات از ۲۰۰۰ نویسه بیشتر نباشد.')
    else:
        CouncilPoll.objects.create(title=title, description=description, village=village_of(request.user), created_by=request.user)
        say(request, True, 'رای‌گیری جدید ایجاد شد.')
    return redirect(panel_url('voting'))


@policy_required('council.vote')
@require_POST
def council_poll_vote(request, poll_id):
    poll = get_object_or_404(polls_for(request.user), id=poll_id)
    choice = request.POST.get('choice')
    if choice not in dict(CouncilPollVote.CHOICES):
        say(request, False, 'نوع رای نامعتبر است.')
    elif poll.status != 'open':
        say(request, False, 'این رای‌گیری بسته شده است.')
    else:
        _, created = CouncilPollVote.objects.get_or_create(poll=poll, member=request.user, defaults={'choice': choice})
        say(request, created, 'رای شما ثبت شد.' if created else 'شما قبلاً در این رای‌گیری رای داده‌اید.')
    return redirect(panel_url('voting'))


@policy_required('council.vote')
@require_POST
def council_poll_close(request, poll_id):
    poll = get_object_or_404(polls_for(request.user), id=poll_id)
    if poll.status == 'open':
        poll.status, poll.closed_at = 'closed', timezone.now()
        poll.save(update_fields=['status', 'closed_at'])
        say(request, True, 'رای‌گیری بسته شد.')
    return redirect(panel_url('voting'))


def _meeting_time(date_text, time_text):
    day = parse_jalali(date_text)
    match = re.fullmatch(r'(\d{1,2}):(\d{2})', digits(time_text))
    if not match or int(match.group(1)) > 23 or int(match.group(2)) > 59:
        raise Invalid('ساعت را به صورت ۱۰:۳۰ وارد کنید.')
    naive = datetime(day.year, day.month, day.day, int(match.group(1)), int(match.group(2)))
    return timezone.make_aware(naive)


@policy_required('council.vote')
@require_POST
def council_meeting_save(request):
    post = request.POST
    meeting = None
    if post.get('meeting_id'):
        meeting = get_object_or_404(meetings_for(request.user), id=post.get('meeting_id') if post.get('meeting_id').isdigit() else 0)
    title = post.get('title', '').strip()
    location = post.get('location', '').strip()
    agenda = post.get('agenda', '').strip()
    try:
        if not title or len(title) > 200 or len(location) > 200 or len(agenda) > 3000:
            raise Invalid('عنوان جلسه را وارد کنید و طول متن‌ها را رعایت کنید.')
        starts_at = _meeting_time(post.get('date', ''), post.get('time', ''))
    except Invalid as error:
        say(request, False, str(error))
        return redirect(panel_url('calendar'))
    if meeting is None:
        meeting = CouncilMeeting(village=village_of(request.user), created_by=request.user)
    meeting.title, meeting.location, meeting.agenda, meeting.starts_at = title, location, agenda, starts_at
    meeting.save()
    attendee_ids = [int(i) for i in post.getlist('attendees') if i.isdigit()]
    meeting.attendees.set(colleagues(request.user).filter(id__in=attendee_ids))
    say(request, True, 'جلسه ذخیره شد.')
    return redirect(panel_url('calendar', ym=jdatetime.date.fromgregorian(date=starts_at.date()).strftime('%Y-%m')))


@policy_required('council.vote')
@require_POST
def council_meeting_cancel(request, meeting_id):
    meeting = get_object_or_404(meetings_for(request.user), id=meeting_id)
    meeting.status = 'cancelled'
    meeting.save(update_fields=['status'])
    say(request, True, 'جلسه لغو شد.')
    return redirect(panel_url('calendar'))


def _send(conversation, sender, body):
    message = Message.objects.create(conversation=conversation, sender=sender, body=body)
    for person in conversation.participants.exclude(id=sender.id):
        MessageRecipient.objects.create(message=message, recipient=person)
        Notification.objects.create(
            user=person, notification_type='new_message', title='پیام جدید',
            message=f'پیام جدیدی از {sender.get_full_name() or sender.username} دریافت کردید.')
    conversation.save()  # bumps updated_at


@policy_required('council.view')
@require_POST
def council_message_new(request):
    rid = request.POST.get('recipient_id', '')
    subject = request.POST.get('subject', '').strip()
    body = request.POST.get('message_body', '').strip()
    recipient = colleagues(request.user).filter(id=rid).first() if rid.isdigit() else None
    if not recipient or not subject or not body or len(subject) > 200 or len(body) > 5000:
        say(request, False, 'گیرنده، موضوع و متن پیام را درست وارد کنید.')
        return redirect(panel_url('messages'))
    conversation = Conversation.objects.create(subject=subject)
    conversation.participants.add(request.user, recipient)
    _send(conversation, request.user, body)
    say(request, True, 'پیام ارسال شد.')
    return redirect(panel_url('messages', conv=conversation.id))


@policy_required('council.view')
@require_POST
def council_message_reply(request, conversation_id):
    conversation = get_object_or_404(Conversation, id=conversation_id, participants=request.user)
    body = request.POST.get('message_body', '').strip()
    if body and len(body) <= 5000:
        _send(conversation, request.user, body)
    else:
        say(request, False, 'متن پیام را وارد کنید.')
    return redirect(panel_url('messages', conv=conversation.id))


@policy_required('council.view')
@require_POST
def council_settings_save(request):
    user, post = request.user, request.POST
    first, last = post.get('first_name', '').strip(), post.get('last_name', '').strip()
    email = post.get('email', '').strip()
    mobile = digits(post.get('mobile_number', ''))
    p1, p2 = post.get('new_password1', ''), post.get('new_password2', '')
    try:
        if not first or not last or len(first) > 30 or len(last) > 30:
            raise ValidationError('نام و نام خانوادگی را وارد کنید.')
        if email:
            validate_email(email)
        if mobile and not MOBILE.match(mobile):
            raise ValidationError('شماره موبایل صحیح وارد کنید (مثال: ۰۹۱۲۳۴۵۶۷۸۹).')
        if p1 or p2:
            if p1 != p2:
                raise ValidationError('رمز عبور و تکرار آن یکسان نیست.')
            validate_password(p1, user)
    except ValidationError as error:
        say(request, False, ' '.join(error.messages))
        return redirect(panel_url('settings'))
    user.first_name, user.last_name, user.email = first, last, email
    if p1:
        user.set_password(p1)
    user.save()
    UserProfile.objects.filter(user=user).update(mobile_number=mobile or None)
    if p1:
        update_session_auth_hash(request, user)
    say(request, True, 'تنظیمات ذخیره شد.')
    return redirect(panel_url('settings'))


def poll_cards(user):
    mine = set(CouncilPollVote.objects.filter(member=user).values_list('poll_id', flat=True))
    cards = []
    for poll in polls_for(user).select_related('created_by')[:50]:
        cards.append({'poll': poll, 'tally': poll.tally(), 'voted': poll.id in mine})
    return cards


def calendar_context(user, ym):
    today = jdatetime.date.today()
    match = re.fullmatch(r'(\d{4})-(\d{1,2})', ym or '')
    year, month = (int(match.group(1)), int(match.group(2))) if match else (today.year, today.month)
    if not 1 <= month <= 12 or not 1300 <= year <= 1700:
        year, month = today.year, today.month
    first = jdatetime.date(year, month, 1)
    nxt = jdatetime.date(year + (month == 12), month % 12 + 1, 1)
    length = (nxt - first).days
    start = timezone.make_aware(datetime.combine(first.togregorian(), datetime.min.time()))
    end = start + timedelta(days=length)
    meetings = meetings_for(user).filter(starts_at__gte=start, starts_at__lt=end).exclude(status='cancelled')
    by_day = {}
    for m in meetings:
        by_day.setdefault(jdatetime.date.fromgregorian(date=timezone.localtime(m.starts_at).date()).day, []).append(m)
    cells = [None] * first.weekday() + [
        {'day': d, 'meetings': by_day.get(d, []), 'today': (year, month, d) == (today.year, today.month, today.day)}
        for d in range(1, length + 1)]
    cells += [None] * (-len(cells) % 7)
    prev = jdatetime.date(year - (month == 1), (month - 2) % 12 + 1, 1)
    return {
        'label': f'{MONTHS[month - 1]} {year}', 'weeks': [cells[i:i + 7] for i in range(0, len(cells), 7)],
        'prev': prev.strftime('%Y-%m'), 'next': nxt.strftime('%Y-%m'),
    }


def conversation_context(user, conv_id):
    conversations = Conversation.objects.filter(participants=user).annotate(
        unread=Count('messages__recipients', filter=Q(messages__recipients__recipient=user, messages__recipients__is_read=False))
    ).prefetch_related('participants').order_by('-updated_at')[:30]
    active = None
    if conv_id and str(conv_id).isdigit():
        active = Conversation.objects.filter(id=conv_id, participants=user).first()
    thread = []
    if active:
        thread = list(active.messages.select_related('sender'))
        MessageRecipient.objects.filter(message__conversation=active, recipient=user, is_read=False).update(is_read=True, read_at=timezone.now())
    return {'conversations': conversations, 'active_conversation': active, 'thread': thread}
