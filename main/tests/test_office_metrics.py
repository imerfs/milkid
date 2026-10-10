import uuid
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from main.management.commands.office_metrics import collect
from main.models import Appointment, LetterRecipient
from main.office import letters
from main.tests.helpers import make_municipality, make_user

VILLAGE = 'روستای الف'


class Metrics(TestCase):
    def test_numbers_reflect_reading_speed_and_completed_meetings(self):
        boss = make_user('dehyari', city_village=VILLAGE)
        make_municipality(boss, VILLAGE)
        staff = make_user('accountant', city_village=VILLAGE)
        boss = type(boss).objects.get(pk=boss.pk)     # the cached profile predates the role update
        letter = letters.compose(boss, to=[staff.id], subject='s', body='b', token=str(uuid.uuid4()))
        LetterRecipient.objects.filter(letter=letter).update(read_at=letter.sent_at + timedelta(hours=3))
        late = letters.compose(boss, to=[staff.id], subject='t', body='b', token=str(uuid.uuid4()))
        type(late).objects.filter(pk=late.pk).update(sent_at=timezone.now() - timedelta(hours=60))
        now = timezone.now() + timedelta(days=2)
        Appointment.objects.create(provider=staff, client=boss, start=now, end=now + timedelta(minutes=30), subject='x', status='completed')
        m = collect(30)
        self.assertEqual(m['letters_sent'], 2)
        self.assertEqual(m['letters_median_hours_to_read'], 3.0)
        self.assertEqual(m['letters_unread_over_48h'], 1)
        self.assertEqual((m['appointments_completed'], m['appointments_completion_rate']), (1, 100.0))

    def test_empty_system_prints_without_error(self):
        call_command('office_metrics', stdout=StringIO())
