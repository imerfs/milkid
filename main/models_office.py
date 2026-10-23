"""Models of the office system (role grants, letters, appointments). Imported at the end of main/models.py."""
from django.conf import settings
from django.db import models
from django.db.models import Q


class RoleGrant(models.Model):
    """History of staff roles given by a dehyari. UserProfile.role stays the live source of truth."""
    municipality = models.ForeignKey('main.Municipality', on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='role_grants', verbose_name='دهیاری')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='role_grants',
                             verbose_name='کاربر')
    role = models.CharField(max_length=20, verbose_name='نقش اعطاشده')
    previous_role = models.CharField(max_length=20, verbose_name='نقش قبلی')
    granted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                   related_name='role_grants_given', verbose_name='اعطاکننده')
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='role_grants_revoked')

    class Meta:
        verbose_name = 'اعطای نقش'
        verbose_name_plural = 'اعطای نقش‌ها'
        ordering = ['-created_at']
        constraints = [
            # a user has at most one live grant
            models.UniqueConstraint(fields=['user'], condition=Q(revoked_at__isnull=True),
                                    name='one_active_role_grant_per_user'),
        ]

    def __str__(self):
        return f'{self.user} → {self.role}'


class Letter(models.Model):
    """An official letter between users of one village (مکاتبه‌ی اداری)."""
    PRIORITIES = [('normal', 'عادی'), ('urgent', 'فوری'), ('immediate', 'آنی')]
    STATUSES = [('draft', 'پیش‌نویس'), ('sent', 'ارسال‌شده')]

    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='letters_sent')
    village = models.CharField(max_length=100, blank=True, db_index=True, verbose_name='روستا/شهر')
    sender_org = models.ForeignKey('main.Municipality', on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='letters_sent', verbose_name='سازمان فرستنده')
    subject = models.CharField(max_length=200, verbose_name='موضوع')
    body = models.TextField(max_length=20000, verbose_name='متن نامه')
    priority = models.CharField(max_length=10, choices=PRIORITIES, default='normal', verbose_name='اولویت')
    confidential = models.BooleanField(default=False, verbose_name='محرمانه')
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='replies')
    status = models.CharField(max_length=10, choices=STATUSES, default='draft')
    year = models.PositiveIntegerField(null=True, blank=True, verbose_name='سال شمسی')
    sequence = models.PositiveIntegerField(null=True, blank=True, verbose_name='شماره ترتیب')
    client_token = models.UUIDField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'نامه'
        verbose_name_plural = 'نامه‌ها'
        ordering = ['-sent_at', '-created_at']
        constraints = [
            models.UniqueConstraint(fields=['sender', 'client_token'], condition=Q(client_token__isnull=False),
                                    name='letter_idempotency_token'),
            models.UniqueConstraint(fields=['village', 'year', 'sequence'], condition=Q(sequence__isnull=False),
                                    name='letter_number_unique_per_village_year'),
            models.CheckConstraint(condition=Q(status='draft') | Q(sequence__isnull=False, sent_at__isnull=False),
                                   name='sent_letter_has_number'),
        ]

    @property
    def number(self):
        return f'{self.year}/{self.sequence:04d}' if self.sequence else ''

    def __str__(self):
        return f'{self.number or "پیش‌نویس"} {self.subject}'


class LetterRecipient(models.Model):
    KINDS = [('to', 'گیرنده'), ('cc', 'رونوشت')]

    letter = models.ForeignKey(Letter, on_delete=models.CASCADE, related_name='recipients')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='letters_received')
    kind = models.CharField(max_length=2, choices=KINDS, default='to')
    read_at = models.DateTimeField(null=True, blank=True)
    archived = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['letter', 'user'], name='one_row_per_letter_recipient')]
        indexes = [models.Index(fields=['user', 'archived', 'read_at'], name='letterrcpt_user_state')]


class LetterAttachment(models.Model):
    letter = models.ForeignKey(Letter, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='letters/%Y/%m/')
    original_name = models.CharField(max_length=255)
    size = models.PositiveIntegerField()


class AvailabilityRule(models.Model):
    """When a staff member receives visitors: one rule per weekday (0 = Saturday ... 6 = Friday)."""
    provider = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='availability_rules')
    weekday = models.PositiveSmallIntegerField(verbose_name='روز هفته')
    start_time = models.TimeField(verbose_name='از ساعت')
    end_time = models.TimeField(verbose_name='تا ساعت')
    slot_minutes = models.PositiveSmallIntegerField(default=30, verbose_name='مدت هر وقت (دقیقه)')

    class Meta:
        verbose_name = 'ساعت کاری'
        verbose_name_plural = 'ساعات کاری'
        ordering = ['weekday']
        constraints = [
            models.UniqueConstraint(fields=['provider', 'weekday'], name='one_rule_per_provider_weekday'),
            models.CheckConstraint(condition=Q(weekday__lte=6), name='rule_weekday_0_to_6'),
            models.CheckConstraint(condition=Q(end_time__gt=models.F('start_time')), name='rule_ends_after_start'),
            models.CheckConstraint(condition=Q(slot_minutes__gte=10, slot_minutes__lte=120), name='rule_slot_10_to_120'),
        ]


class Appointment(models.Model):
    STATUSES = [('pending', 'در انتظار تایید'), ('confirmed', 'تایید شده'), ('rejected', 'رد شده'),
                ('cancelled', 'لغو شده'), ('completed', 'انجام شده')]
    ACTIVE = ('pending', 'confirmed')

    provider = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='appointments_received')
    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='appointments_booked')
    start = models.DateTimeField(verbose_name='شروع')
    end = models.DateTimeField(verbose_name='پایان')
    subject = models.CharField(max_length=200, verbose_name='موضوع')
    notes = models.TextField(max_length=1000, blank=True, verbose_name='توضیحات')
    status = models.CharField(max_length=10, choices=STATUSES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='appointments_cancelled')

    class Meta:
        verbose_name = 'وقت ملاقات'
        verbose_name_plural = 'وقت‌های ملاقات'
        ordering = ['start']
        constraints = [
            # the guard against double booking: an active slot has one owner
            models.UniqueConstraint(fields=['provider', 'start'], condition=Q(status__in=['pending', 'confirmed']),
                                    name='one_active_appointment_per_slot'),
            models.CheckConstraint(condition=Q(end__gt=models.F('start')), name='appointment_ends_after_start'),
            models.CheckConstraint(condition=~Q(provider=models.F('client')), name='appointment_not_with_self'),
        ]
        indexes = [models.Index(fields=['client', 'start'], name='appt_client_start'),
                   models.Index(fields=['provider', 'start'], name='appt_provider_start')]
