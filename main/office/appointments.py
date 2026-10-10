"""Appointments (وقت‌دهی): weekly office hours, booking, decisions."""
from datetime import datetime, time, timedelta

import jdatetime
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.utils import timezone

from main.models import Appointment, AvailabilityRule
from main.notifications import notify
from main.office.errors import Conflict, Forbidden, Invalid, NotFound, RateLimited
from main.office.letters import STAFF_ROLES, village_of
from main.office.roles import is_admin

PROVIDER_ROLES = STAFF_ROLES
WEEKDAYS = ['شنبه', 'یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنج‌شنبه', 'جمعه']
HORIZON_DAYS = 14
LEAD = timedelta(hours=1)
OPEN_CAP = 5
MAX_RULES = 7


def weekday_of(date):
    """0 = Saturday ... 6 = Friday (Iranian week)."""
    return (date.weekday() + 2) % 7


def jalali_label(date):
    j = jdatetime.date.fromgregorian(date=date)
    return f'{WEEKDAYS[weekday_of(date)]} {j.day} {j.j_months_fa[j.month - 1]}'


def providers_for(user):
    people = User.objects.filter(is_active=True, profile__is_active=True, profile__role__in=PROVIDER_ROLES) \
        .exclude(pk=user.pk).select_related('profile')
    if is_admin(user):
        return people
    return people.filter(profile__city_village=village_of(user))


def _aware(naive):
    return timezone.make_aware(naive, timezone.get_current_timezone())


def _grid(provider, date):
    """Every slot the weekly hours define for that date (no filtering)."""
    rule = AvailabilityRule.objects.filter(provider=provider, weekday=weekday_of(date)).first()
    if rule is None:
        return []
    step, slots = timedelta(minutes=rule.slot_minutes), []
    cursor = datetime.combine(date, rule.start_time)
    close = datetime.combine(date, rule.end_time)
    while cursor + step <= close:
        slots.append((_aware(cursor), _aware(cursor + step)))
        cursor += step
    return slots


def _bookable(provider, date):
    today = timezone.localdate()
    if not (today <= date <= today + timedelta(days=HORIZON_DAYS)):
        return []
    earliest = timezone.now() + LEAD
    return [(s, e) for s, e in _grid(provider, date) if s >= earliest]


def free_slots(provider, date):
    grid = _bookable(provider, date)
    if not grid:
        return []
    busy = list(Appointment.objects.filter(provider=provider, status__in=Appointment.ACTIVE,
                                           start__lt=grid[-1][1], end__gt=grid[0][0]).values_list('start', 'end'))
    return [(s, e) for s, e in grid if not any(bs < e and be > s for bs, be in busy)]


def day_strip(provider):
    """Next days with their number of free slots, for the date picker."""
    today = timezone.localdate()
    return [{'date': d, 'iso': d.isoformat(), 'label': jalali_label(d), 'free': len(free_slots(provider, d))}
            for d in (today + timedelta(days=i) for i in range(HORIZON_DAYS + 1))]


def parse_date(raw, default=None):
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return default


def book(client, provider_id, start_raw, subject, notes=''):
    """Returns (appointment, created)."""
    if str(provider_id) == str(client.id):
        raise Invalid('نمی‌توانید از خودتان وقت بگیرید.')
    provider = providers_for(client).filter(pk=provider_id).first()
    if provider is None:
        raise NotFound('کارمند مورد نظر پیدا نشد.')
    subject, notes = (subject or '').strip(), (notes or '').strip()
    if not subject or len(subject) > 200:
        raise Invalid('موضوع ملاقات الزامی است و باید حداکثر ۲۰۰ نویسه باشد.')
    if len(notes) > 1000:
        raise Invalid('توضیحات حداکثر ۱۰۰۰ نویسه است.')
    try:
        start = _aware(datetime.strptime(start_raw or '', '%Y-%m-%dT%H:%M'))
    except ValueError:
        raise Invalid('زمان انتخاب‌شده معتبر نیست.')

    mine = Appointment.objects.filter(provider=provider, client=client, start=start, status__in=Appointment.ACTIVE).first()
    if mine:
        return mine, False
    date = timezone.localtime(start).date()
    free, grid = dict(free_slots(provider, date)), dict(_bookable(provider, date))
    if start not in grid:
        raise Invalid('این زمان در ساعات قابل رزرو نیست.')
    if start not in free:
        raise Conflict('این وقت همین حالا رزرو شد؛ زمان دیگری انتخاب کنید.')
    if Appointment.objects.filter(client=client, status__in=Appointment.ACTIVE, end__gt=timezone.now()).count() >= OPEN_CAP:
        raise RateLimited(f'حداکثر {OPEN_CAP} وقت باز می‌توانید داشته باشید؛ ابتدا یکی را لغو یا تکمیل کنید.')
    try:
        with transaction.atomic():
            appointment = Appointment.objects.create(provider=provider, client=client, start=start, end=free[start],
                                                     subject=subject, notes=notes)
    except IntegrityError:
        raise Conflict('این وقت همین حالا رزرو شد؛ زمان دیگری انتخاب کنید.')
    when = timezone.localtime(start)
    notify(provider, 'درخواست وقت ملاقات',
           f'{client.get_full_name() or client.username} برای {jalali_label(when.date())} ساعت {when:%H:%M} وقت خواسته است.')
    return appointment, True


NEXT_STATUS = {'confirm': 'confirmed', 'reject': 'rejected', 'cancel': 'cancelled', 'complete': 'completed'}
FROM_STATUS = {'confirm': ('pending',), 'reject': ('pending',), 'cancel': ('pending', 'confirmed'), 'complete': ('confirmed',)}
MESSAGES = {'confirm': 'وقت ملاقات شما تایید شد.', 'reject': 'درخواست وقت ملاقات شما رد شد.',
            'cancel': 'وقت ملاقات لغو شد.', 'complete': 'وقت ملاقات انجام‌شده ثبت شد.'}


def decide(actor, appointment_id, action):
    """Returns (appointment, changed). Repeating an action that already happened changes nothing."""
    if action not in NEXT_STATUS:
        raise Invalid('عملیات نامعتبر است.')
    with transaction.atomic():
        appointment = (Appointment.objects.select_related('provider', 'client')
                       .filter(pk=appointment_id).filter(provider=actor).first()
                       or Appointment.objects.select_related('provider', 'client').filter(pk=appointment_id, client=actor).first())
        if appointment is None:
            raise NotFound('وقت ملاقات پیدا نشد.')
        is_provider = appointment.provider_id == actor.id
        if action in ('confirm', 'reject', 'complete') and not is_provider:
            raise Forbidden('فقط کارمند می‌تواند این کار را انجام دهد.')
        target = NEXT_STATUS[action]
        if appointment.status == target:
            return appointment, False
        if appointment.status not in FROM_STATUS[action]:
            raise Conflict('در وضعیت فعلی این عملیات ممکن نیست.')
        if action == 'complete' and appointment.start > timezone.now():
            raise Conflict('پیش از شروع وقت نمی‌توان آن را انجام‌شده ثبت کرد.')
        appointment.status, appointment.decided_at = target, timezone.now()
        if action == 'cancel':
            appointment.cancelled_by = actor
        appointment.save(update_fields=['status', 'decided_at', 'cancelled_by'])
    other = appointment.client if is_provider else appointment.provider
    notify(other, 'وقت ملاقات', MESSAGES[action])
    return appointment, True


def my_appointments(user):
    now = timezone.now()
    as_client = Appointment.objects.filter(client=user).select_related('provider', 'provider__profile')
    as_provider = Appointment.objects.filter(provider=user).select_related('client', 'client__profile') \
        if user.profile.role in PROVIDER_ROLES else Appointment.objects.none()
    return {
        'upcoming': as_client.filter(end__gte=now).order_by('start'), 'past': as_client.filter(end__lt=now).order_by('-start')[:20],
        'incoming': as_provider.filter(end__gte=now).order_by('start'), 'incoming_past': as_provider.filter(end__lt=now).order_by('-start')[:20],
        'is_provider': user.profile.role in PROVIDER_ROLES,
    }


def parse_rules(post):
    """Validated list of (weekday, start, end, minutes) from the weekly form."""
    rules = []
    for weekday in range(7):
        if post.get(f'd{weekday}_on') != 'on':
            continue
        try:
            start = datetime.strptime(post.get(f'd{weekday}_from', ''), '%H:%M').time()
            end = datetime.strptime(post.get(f'd{weekday}_to', ''), '%H:%M').time()
            minutes = int(post.get(f'd{weekday}_len', ''))
        except ValueError:
            raise Invalid(f'ساعت یا مدت روز {WEEKDAYS[weekday]} معتبر نیست.')
        if end <= start:
            raise Invalid(f'در روز {WEEKDAYS[weekday]} ساعت پایان باید بعد از شروع باشد.')
        if not 10 <= minutes <= 120:
            raise Invalid('مدت هر وقت باید بین ۱۰ تا ۱۲۰ دقیقه باشد.')
        rules.append((weekday, start, end, minutes))
    return rules


def set_rules(provider, post):
    rules = parse_rules(post)
    with transaction.atomic():
        AvailabilityRule.objects.filter(provider=provider).delete()
        AvailabilityRule.objects.bulk_create([
            AvailabilityRule(provider=provider, weekday=w, start_time=s, end_time=e, slot_minutes=m) for w, s, e, m in rules])
    return rules
