"""The numbers that show the office system is actually used: how fast letters are read and how many
appointments end in a real meeting (not decorative counters).

    python manage.py office_metrics [--days 30]
"""
from datetime import timedelta
from statistics import median

from django.core.management.base import BaseCommand
from django.utils import timezone

from main.models import Appointment, Letter, LetterRecipient


def collect(days=30, now=None):
    now = now or timezone.now()
    since = now - timedelta(days=days)
    rows = LetterRecipient.objects.filter(letter__status='sent', letter__sent_at__gte=since, kind='to') \
        .select_related('letter')
    hours = [(r.read_at - r.letter.sent_at).total_seconds() / 3600 for r in rows if r.read_at]
    unread_48h = sum(1 for r in rows if not r.read_at and now - r.letter.sent_at > timedelta(hours=48))
    appts = Appointment.objects.filter(created_at__gte=since)
    decided = appts.exclude(status='pending').exclude(status='rejected').exclude(status='cancelled')
    closed = appts.filter(status__in=['completed', 'rejected', 'cancelled'])
    done = appts.filter(status='completed').count()
    return {
        'days': days,
        'letters_sent': Letter.objects.filter(status='sent', sent_at__gte=since).count(),
        'letters_median_hours_to_read': round(median(hours), 1) if hours else None,
        'letters_unread_over_48h': unread_48h,
        'appointments_requested': appts.count(),
        'appointments_completed': done,
        'appointments_completion_rate': round(100 * done / closed.count(), 1) if closed.count() else None,
        'appointments_waiting_over_48h': appts.filter(status='pending', created_at__lt=now - timedelta(hours=48)).count(),
    }


class Command(BaseCommand):
    help = 'Print the office-system outcome numbers.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=30)

    def handle(self, *args, **options):
        data = collect(options['days'])
        labels = {
            'letters_sent': 'نامه‌های ارسال‌شده',
            'letters_median_hours_to_read': 'میانه‌ی ساعت تا خوانده‌شدن نامه (عدد اصلی)',
            'letters_unread_over_48h': 'نامه‌های بیش از ۴۸ ساعت خوانده‌نشده',
            'appointments_requested': 'درخواست‌های وقت',
            'appointments_completed': 'ملاقات‌های انجام‌شده',
            'appointments_completion_rate': 'درصد وقت‌های بسته‌شده که واقعاً انجام شد',
            'appointments_waiting_over_48h': 'درخواست‌های وقتِ بی‌پاسخ بیش از ۴۸ ساعت',
        }
        self.stdout.write(f'گزارش {data["days"]} روز گذشته')
        for key, label in labels.items():
            self.stdout.write(f'  {label}: {"—" if data[key] is None else data[key]}')
