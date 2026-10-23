"""One inbox for chats and official letters (the data behind the messenger shown inside every panel).

A *thread* is a chat (``Conversation``, key ``c<id>``) or a chain of letters (a root ``Letter`` and its replies, key
``l<id>``). Every message carries the identity of the person behind it: name, position and organization.
"""
import dataclasses
from datetime import timedelta

from django.db.models import Count, Max, OuterRef, Q, Subquery
from django.utils import timezone

from main.models import Conversation, ConversationState, Letter, LetterRecipient, Message, MessageRecipient, Notification
from main.office import letters
from main.office.directory import Identity, allowed_recipients, identity
from main.office.errors import Forbidden, Invalid, NotFound, RateLimited

DIRECT_SUBJECT = 'گفتگوی مستقیم'
CHAT_HOURLY_CAP = 300
MAX_BODY = 4000
MAX_THREADS = 60


@dataclasses.dataclass
class Thread:
    key: str
    kind: str                  # 'chat' | 'letter'
    who: Identity              # the other side
    extra: int                 # how many more people are in the thread
    subject: str
    preview: str
    when: object
    unread: int
    priority: str = 'normal'
    confidential: bool = False
    number: str = ''


def parse_key(key):
    kind, number = (key or '')[:1], (key or '')[1:]
    if kind not in ('c', 'l') or not number.isdigit():
        raise NotFound('گفتگو پیدا نشد.')
    return ('chat' if kind == 'c' else 'letter'), int(number)


# ---------- chats ----------

def _chats(user):
    archived = ConversationState.objects.filter(user=user, is_archived=True).values('conversation_id')
    last = Message.objects.filter(conversation=OuterRef('pk')).order_by('-created_at')
    return (Conversation.objects.filter(participants=user).exclude(pk__in=archived)
            .annotate(last_body=Subquery(last.values('body')[:1]), last_at=Max('messages__created_at'),
                      last_sender=Subquery(last.values('sender_id')[:1]),
                      unread=Count('messages__recipients', filter=Q(messages__recipients__recipient=user,
                                                                      messages__recipients__is_read=False), distinct=True))
            .prefetch_related('participants__profile').order_by('-updated_at'))


def chat_threads(user):
    rows = []
    for c in _chats(user)[:MAX_THREADS]:
        others = [p for p in c.participants.all() if p.pk != user.pk]
        if not others:
            continue
        mine = c.last_sender == user.pk
        rows.append(Thread(key=f'c{c.pk}', kind='chat', who=identity(others[0]), extra=len(others) - 1,
                           subject='' if c.subject == DIRECT_SUBJECT else c.subject,
                           preview=(('شما: ' if mine else '') + (c.last_body or ''))[:90], when=c.last_at or c.created_at,
                           unread=c.unread))
    return rows


# ---------- letters ----------

def _root_map(visible):
    """letter id -> id of the first letter of its chain."""
    parents = {l.pk: l.parent_id for l in visible}
    missing = {p for p in parents.values() if p and p not in parents}
    while missing:
        fetched = dict(Letter.objects.filter(pk__in=missing).values_list('pk', 'parent_id'))
        parents.update(fetched)
        missing = {p for p in fetched.values() if p and p not in parents}
    roots = {}
    for pk in parents:
        node, hops = pk, 0
        while parents.get(node) and hops < 50:
            node, hops = parents[node], hops + 1
        roots[pk] = node
    return roots


def letter_threads(user):
    visible = list(letters.visible_to(user).select_related('sender', 'sender__profile', 'sender_org')
                   .order_by('-sent_at', '-created_at')[:400])
    roots = _root_map(visible)
    unread_ids = set(LetterRecipient.objects.filter(user=user, read_at__isnull=True, archived=False, letter__status='sent')
                     .values_list('letter_id', flat=True))
    groups = {}
    for letter in visible:                          # newest first: the first one met is the latest of its chain
        groups.setdefault(roots[letter.pk], []).append(letter)
    rows = []
    for chain in list(groups.values())[:MAX_THREADS]:
        latest = chain[0]
        if latest.sender_id == user.pk:
            first = latest.recipients.select_related('user', 'user__profile').first()
            side, extra = (first.user if first else user), max(latest.recipients.count() - 1, 0)
        else:
            side, extra = latest.sender, 0
        rows.append(Thread(key=f'l{roots[latest.pk]}', kind='letter', who=identity(side), extra=extra, subject=latest.subject,
                           preview=(('شما: ' if latest.sender_id == user.pk else '') + latest.body.replace('\n', ' '))[:90],
                           when=latest.sent_at or latest.created_at, unread=sum(1 for l in chain if l.pk in unread_ids),
                           priority=latest.priority, confidential=latest.confidential,
                           number=latest.number or 'پیش‌نویس'))
    return rows


def threads(user, kind='all', q='', unread=False):
    rows = (chat_threads(user) if kind in ('all', 'chat') else []) + (letter_threads(user) if kind in ('all', 'letter') else [])
    q = (q or '').strip()
    if q:
        rows = [t for t in rows if q in t.who.name or q in t.subject or q in t.preview or q in t.who.org or q in t.number]
    if unread:
        rows = [t for t in rows if t.unread]
    return sorted(rows, key=lambda t: t.when, reverse=True)


# ---------- opening a thread ----------

def _mark_days(items):
    """Flag the first item of every day so the pane can draw a date separator."""
    previous = None
    for item in items:
        day = timezone.localtime(item['at']).date()
        item['show_day'], previous = day != previous, day

def _letter_chain(user, root_id):
    ids, frontier = {root_id}, {root_id}
    while frontier:
        frontier = set(Letter.objects.filter(parent_id__in=frontier).values_list('pk', flat=True)) - ids
        ids |= frontier
    return (letters.visible_to(user).filter(pk__in=ids).select_related('sender', 'sender__profile', 'sender_org')
            .prefetch_related('attachments', 'recipients__user__profile').order_by('sent_at', 'created_at'))


def open_thread(user, key):
    """Everything the thread pane needs; marks what the user sees as read."""
    kind, number = parse_key(key)
    if kind == 'chat':
        chat = Conversation.objects.filter(pk=number, participants=user).prefetch_related('participants__profile').first()
        if chat is None:
            raise NotFound('گفتگو پیدا نشد.')
        MessageRecipient.objects.filter(message__conversation=chat, recipient=user, is_read=False) \
            .update(is_read=True, read_at=timezone.now())
        others = [p for p in chat.participants.all() if p.pk != user.pk]
        msgs = list(chat.messages.select_related('sender', 'sender__profile'))
        items = [{'mine': m.sender_id == user.pk, 'who': identity(m.sender), 'body': m.body, 'at': m.created_at}
                 for m in msgs]
        _mark_days(items)
        return {'key': key, 'kind': 'chat', 'who': identity(others[0]) if others else identity(user),
                'extra': max(len(others) - 1, 0), 'subject': '' if chat.subject == DIRECT_SUBJECT else chat.subject,
                'items': items, 'last_id': msgs[-1].pk if msgs else 0}
    chain = list(_letter_chain(user, number))
    if not chain:
        raise NotFound('نامه پیدا نشد.')
    for letter in chain:
        letters.open_letter(user, letter)
    items = []
    for letter in chain:
        org = identity(letter.sender)
        if letter.sender_org is not None:
            org = dataclasses.replace(org, org=letter.sender_org.name)
        items.append({'letter': letter, 'at': letter.sent_at or letter.created_at, 'mine': letter.sender_id == user.pk, 'who': org,
                      'to': [identity(r.user) for r in letter.recipients.all() if r.kind == 'to'],
                      'cc': [identity(r.user) for r in letter.recipients.all() if r.kind == 'cc'],
                      'attachments': list(letter.attachments.all())})
    _mark_days(items)
    latest = next((i for i in reversed(items) if i['letter'].status == 'sent'), None)
    can_reply = latest is not None
    return {'key': key, 'kind': 'letter', 'who': items[-1]['who'] if not items[-1]['mine'] else (items[-1]['to'] or [items[-1]['who']])[0],
            'extra': 0, 'subject': chain[0].subject, 'items': items, 'last_id': chain[-1].pk, 'can_reply': can_reply,
            'reply_parent': latest['letter'].pk if latest else None}


# ---------- sending ----------

def _check_body(body):
    body = (body or '').strip()
    if not body:
        raise Invalid('متن پیام خالی است.')
    if len(body) > MAX_BODY:
        raise Invalid(f'پیام حداکثر {MAX_BODY} نویسه است.')
    return body


def _rate(user):
    since = timezone.now() - timedelta(hours=1)
    if Message.objects.filter(sender=user, created_at__gte=since).count() >= CHAT_HOURLY_CAP:
        raise RateLimited(f'در هر ساعت حداکثر {CHAT_HOURLY_CAP} پیام می‌توانید بفرستید.')


def send_chat(user, conversation_id, body):
    body = _check_body(body)
    chat = Conversation.objects.filter(pk=conversation_id, participants=user).first()
    if chat is None:
        raise NotFound('گفتگو پیدا نشد.')
    _rate(user)
    message = Message.objects.create(conversation=chat, sender=user, body=body)
    sender_name = user.get_full_name() or user.username
    for other in chat.participants.exclude(pk=user.pk):
        quiet = MessageRecipient.objects.filter(message__conversation=chat, recipient=other, is_read=False).exists()
        MessageRecipient.objects.create(message=message, recipient=other)
        if not quiet:                      # one notification per run of unread messages, not one per message
            Notification.objects.create(user=other, notification_type='new_message', title='پیام جدید',
                                        message=f'پیام تازه از {sender_name}')
    chat.save(update_fields=['updated_at'])
    return message


def start_chat(user, to_id, body):
    """Send ``body`` to one person, in the existing direct chat with them if there is one."""
    other = allowed_recipients(user).filter(pk=to_id).first() if str(to_id).isdigit() else None
    if other is None:
        raise Forbidden('این گیرنده برای شما مجاز نیست.')
    body = _check_body(body)
    for chat in Conversation.objects.filter(participants=user, subject=DIRECT_SUBJECT).filter(participants=other):
        if chat.participants.count() == 2:
            break
    else:
        chat = Conversation.objects.create(subject=DIRECT_SUBJECT)
        chat.participants.add(user, other)
    send_chat(user, chat.pk, body)
    return chat


def reply_letter(user, parent_id, body, files=()):
    """Answer the letter ``parent_id`` (to its sender, or to its recipients when the user wrote it)."""
    parent = letters.get_for(user, parent_id)
    if parent.status != 'sent':
        raise Invalid('به پیش‌نویس نمی‌توان پاسخ داد.')
    if parent.sender_id == user.pk:
        to = [r.user_id for r in parent.recipients.filter(kind='to')]
    else:
        to = [parent.sender_id]
    subject = parent.subject if parent.subject.startswith('پاسخ:') else f'پاسخ: {parent.subject}'
    return letters.compose(user, to=to, subject=subject, body=body, priority=parent.priority,
                           confidential=parent.confidential, files=files, parent=parent, token=letters.new_token())


# ---------- counters ----------

def unread_chats(user):
    return MessageRecipient.objects.filter(recipient=user, is_read=False).count()


def unread_total(user):
    return letters.unread_count(user) + unread_chats(user)


def signature(user):
    """Changes whenever the inbox changes; the page polls it to know when to reload."""
    last_message = MessageRecipient.objects.filter(recipient=user).aggregate(m=Max('message_id'))['m'] or 0
    last_sent = Message.objects.filter(conversation__participants=user).aggregate(m=Max('id'))['m'] or 0
    last_letter = letters.visible_to(user).aggregate(m=Max('id'))['m'] or 0
    return f'{unread_total(user)}.{last_message}.{last_sent}.{last_letter}'
