from datetime import datetime, time, timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from main.models import Appointment, AvailabilityRule, Notification
from main.tests.helpers import client_for, make_municipality, make_user

VILLAGE = 'روستای الف'


def day(n):
    return timezone.localdate() + timedelta(days=n)


def jalali_weekday(d):          # 0 = Saturday ... 6 = Friday
    return (d.weekday() + 2) % 7


class Clinic(TestCase):
    """An engineer receives visitors on one weekday, 09:00-12:00 in 30 minute slots."""

    def setUp(self):
        self.dehyari = make_user('dehyari', city_village=VILLAGE)
        make_municipality(self.dehyari, VILLAGE)
        self.engineer = make_user('engineer', city_village=VILLAGE)
        self.citizen = make_user('citizen', city_village=VILLAGE)
        self.citizen2 = make_user('citizen', city_village=VILLAGE)
        self.stranger = make_user('engineer', city_village='روستای ب')
        self.target = day(3)
        AvailabilityRule.objects.create(provider=self.engineer, weekday=jalali_weekday(self.target),
                                        start_time=time(9), end_time=time(12), slot_minutes=30)

    def start(self, hh=9, mm=0, date=None):
        d = date or self.target
        return f'{d.isoformat()}T{hh:02d}:{mm:02d}'

    def book(self, who=None, provider=None, hh=9, mm=0, date=None, subject='مشاوره‌ی نقشه'):
        return client_for(who or self.citizen).post(
            reverse('main:appointment_book', args=[(provider or self.engineer).id]),
            {'start': self.start(hh, mm, date), 'subject': subject, 'notes': ''})

    def slots_page(self, who=None, provider=None, date=None):
        return client_for(who or self.citizen).get(
            reverse('main:appointment_book', args=[(provider or self.engineer).id]),
            {'date': (date or self.target).isoformat()}).content.decode()


class Availability(Clinic):
    def post_rules(self, who, **days):
        data = {}
        for d in range(7):
            on = days.get(f'd{d}')
            if on:
                data.update({f'd{d}_on': 'on', f'd{d}_from': on[0], f'd{d}_to': on[1], f'd{d}_len': on[2]})
        return client_for(who).post(reverse('main:availability'), data)

    def test_staff_saves_weekly_hours(self):
        r = self.post_rules(self.engineer, d0=('08:00', '12:00', '20'), d2=('14:00', '16:00', '30'))
        self.assertEqual(r.status_code, 302)
        rules = {x.weekday: (x.start_time, x.end_time, x.slot_minutes) for x in AvailabilityRule.objects.filter(provider=self.engineer)}
        self.assertEqual(rules, {0: (time(8), time(12), 20), 2: (time(14), time(16), 30)})   # replaces the old set

    def test_invalid_hours_are_refused_and_nothing_changes(self):
        before = AvailabilityRule.objects.count()
        for bad in (('12:00', '09:00', '30'), ('09:00', '09:00', '30'), ('09:00', '12:00', '5'),
                    ('09:00', '12:00', '500'), ('xx', '12:00', '30')):
            self.assertEqual(self.post_rules(self.engineer, d1=bad).status_code, 400, bad)
        self.assertEqual(AvailabilityRule.objects.count(), before)

    def test_citizens_do_not_have_office_hours(self):
        self.assertIn(self.post_rules(self.citizen, d1=('09:00', '12:00', '30')).status_code, (302, 403))
        self.assertFalse(AvailabilityRule.objects.filter(provider=self.citizen).exists())

    def test_page_shows_current_rules(self):
        page = client_for(self.engineer).get(reverse('main:availability')).content.decode()
        self.assertIn('value="09:00"', page)


class Slots(Clinic):
    def test_lists_free_slots_on_the_working_day(self):
        page = self.slots_page()
        for t in ('09:00', '09:30', '11:30'):
            self.assertIn(f'value="{self.start(int(t[:2]), int(t[3:]))}"', page)
        self.assertNotIn(f'value="{self.start(12, 0)}"', page)

    def test_day_without_hours_shows_the_empty_state(self):
        page = self.slots_page(date=day(4))
        self.assertIn('وقت آزادی', page)

    def test_taken_slot_disappears_for_everyone(self):
        self.book(self.citizen, hh=9)
        self.assertNotIn(f'value="{self.start(9, 0)}"', self.slots_page(self.citizen2))

    def test_beyond_two_weeks_and_past_days_have_no_slots(self):
        far = day(15)
        AvailabilityRule.objects.update_or_create(provider=self.engineer, weekday=jalali_weekday(far),
                                                  defaults=dict(start_time=time(9), end_time=time(10), slot_minutes=30))
        self.assertNotIn('name="start"', self.slots_page(date=far))   # no slot radios offered
        self.assertEqual(self.book(date=far).status_code, 400)

    def test_providers_page_lists_only_staff_of_my_village(self):
        page = client_for(self.citizen).get(reverse('main:appointment_providers')).content.decode()
        self.assertIn(self.engineer.username, page)
        self.assertNotIn(self.stranger.username, page)
        self.assertNotIn(self.citizen2.username, page)


class Booking(Clinic):
    def test_booking_creates_a_pending_appointment_in_tehran_time(self):
        r = self.book(hh=9, mm=30)
        self.assertEqual(r.status_code, 302)
        appt = Appointment.objects.get()
        local = timezone.localtime(appt.start)
        self.assertEqual((local.date(), local.hour, local.minute), (self.target, 9, 30))
        self.assertEqual(appt.end - appt.start, timedelta(minutes=30))
        self.assertEqual((appt.status, appt.client, appt.provider), ('pending', self.citizen, self.engineer))
        self.assertTrue(Notification.objects.filter(user=self.engineer).exists())

    def test_same_slot_by_another_person_is_a_conflict(self):
        self.book(self.citizen)
        self.assertEqual(self.book(self.citizen2).status_code, 409)
        self.assertEqual(Appointment.objects.count(), 1)

    def test_repeating_my_own_booking_is_harmless(self):
        for _ in range(3):
            self.assertEqual(self.book(self.citizen).status_code, 302)
        self.assertEqual(Appointment.objects.count(), 1)
        self.assertEqual(Notification.objects.filter(user=self.engineer).count(), 1)

    def test_times_off_the_grid_or_outside_hours_are_refused(self):
        for hh, mm in ((9, 10), (8, 30), (12, 0), (13, 0)):
            self.assertEqual(self.book(hh=hh, mm=mm).status_code, 400, (hh, mm))
        self.assertFalse(Appointment.objects.exists())

    def test_slots_less_than_an_hour_away_cannot_be_booked(self):
        now = timezone.localtime()
        today = now.date()
        AvailabilityRule.objects.update_or_create(provider=self.engineer, weekday=jalali_weekday(today),
                                                  defaults=dict(start_time=time(0, 0), end_time=time(23, 30), slot_minutes=30))
        soon = (now + timedelta(minutes=20)).replace(second=0, microsecond=0)
        soon = soon.replace(minute=0 if soon.minute < 30 else 30)
        r = client_for(self.citizen).post(reverse('main:appointment_book', args=[self.engineer.id]),
                                          {'start': soon.strftime('%Y-%m-%dT%H:%M'), 'subject': 'x'})
        self.assertEqual(r.status_code, 400)

    def test_validation(self):
        self.assertEqual(self.book(subject='  ').status_code, 400)
        self.assertEqual(self.book(subject='ا' * 201).status_code, 400)
        r = client_for(self.citizen).post(reverse('main:appointment_book', args=[self.engineer.id]), {'start': 'garbage', 'subject': 'x'})
        self.assertEqual(r.status_code, 400)

    def test_cannot_book_someone_from_another_village_or_a_citizen_or_yourself(self):
        AvailabilityRule.objects.create(provider=self.stranger, weekday=jalali_weekday(self.target), start_time=time(9), end_time=time(12))
        self.assertEqual(self.book(provider=self.stranger).status_code, 404)
        self.assertEqual(self.book(provider=self.citizen2).status_code, 404)
        self.assertEqual(self.book(who=self.engineer).status_code, 400)

    def test_open_appointment_cap(self):
        for hh in range(9, 12):
            self.assertEqual(self.book(hh=hh).status_code, 302)
        other = day(10)
        AvailabilityRule.objects.update_or_create(provider=self.engineer, weekday=jalali_weekday(other),
                                                  defaults=dict(start_time=time(9), end_time=time(12), slot_minutes=30))
        for hh, mm in ((9, 0), (9, 30)):
            self.assertEqual(self.book(date=other, hh=hh, mm=mm).status_code, 302)
        self.assertEqual(self.book(date=other, hh=10).status_code, 429)

    def test_database_itself_refuses_a_double_booking(self):
        self.book(self.citizen)
        existing = Appointment.objects.get()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Appointment.objects.create(provider=self.engineer, client=self.citizen2, start=existing.start,
                                       end=existing.end, subject='x')

    def test_anonymous_must_log_in(self):
        self.assertEqual(self.client.get(reverse('main:appointments')).status_code, 302)


class Decisions(Clinic):
    def setUp(self):
        super().setUp()
        self.book(self.citizen)
        self.appt = Appointment.objects.get()

    def act(self, who, action):
        return client_for(who).post(reverse('main:appointment_action', args=[self.appt.id]), {'action': action})

    def status(self):
        self.appt.refresh_from_db()
        return self.appt.status

    def test_provider_confirms_and_client_is_told(self):
        self.assertEqual(self.act(self.engineer, 'confirm').status_code, 302)
        self.assertEqual(self.status(), 'confirmed')
        self.assertTrue(Notification.objects.filter(user=self.citizen).exists())

    def test_rejecting_frees_the_slot(self):
        self.act(self.engineer, 'reject')
        self.assertEqual(self.status(), 'rejected')
        self.assertEqual(self.book(self.citizen2).status_code, 302)

    def test_either_side_can_cancel_and_the_slot_reopens(self):
        self.act(self.citizen, 'cancel')
        self.assertEqual((self.status(), self.appt.cancelled_by), ('cancelled', self.citizen))
        self.assertEqual(self.book(self.citizen2).status_code, 302)

    def test_client_cannot_confirm_and_strangers_see_nothing(self):
        self.assertEqual(self.act(self.citizen, 'confirm').status_code, 403)
        self.assertEqual(self.act(self.citizen2, 'cancel').status_code, 404)
        self.assertEqual(self.act(self.stranger, 'confirm').status_code, 404)
        self.assertEqual(self.status(), 'pending')

    def test_final_states_do_not_change_again(self):
        self.act(self.engineer, 'reject')
        self.assertEqual(self.act(self.engineer, 'confirm').status_code, 409)
        self.assertEqual(self.status(), 'rejected')

    def test_repeating_the_same_action_is_harmless(self):
        self.act(self.engineer, 'confirm')
        self.assertEqual(self.act(self.engineer, 'confirm').status_code, 302)
        self.assertEqual(Notification.objects.filter(user=self.citizen).count(), 1)

    def test_complete_only_after_it_started(self):
        self.act(self.engineer, 'confirm')
        self.assertEqual(self.act(self.engineer, 'complete').status_code, 409)
        Appointment.objects.filter(pk=self.appt.pk).update(start=timezone.now() - timedelta(hours=2),
                                                           end=timezone.now() - timedelta(hours=1, minutes=30))
        self.assertEqual(self.act(self.engineer, 'complete').status_code, 302)
        self.assertEqual(self.status(), 'completed')

    def test_unknown_action(self):
        self.assertEqual(self.act(self.engineer, 'explode').status_code, 400)


class MyAppointments(Clinic):
    def test_client_and_provider_see_the_same_appointment(self):
        self.book(self.citizen)
        mine = client_for(self.citizen).get(reverse('main:appointments')).content.decode()
        theirs = client_for(self.engineer).get(reverse('main:appointments')).content.decode()
        self.assertIn('مشاوره‌ی نقشه', mine)
        self.assertIn('مشاوره‌ی نقشه', theirs)
        self.assertNotIn('مشاوره‌ی نقشه', client_for(self.citizen2).get(reverse('main:appointments')).content.decode())

    def test_empty_state(self):
        self.assertIn('وقتی ندارید', client_for(self.citizen2).get(reverse('main:appointments')).content.decode())
