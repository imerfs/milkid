"""Appointments: only citizens book; the technical staff and the council receive. Everything lives inside the panels."""
from datetime import time, timedelta

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from main.models import Appointment, AvailabilityRule, Notification
from main.office import visits
from main.tests.helpers import client_for, make_municipality, make_user

VILLAGE = 'روستای الف'
OTHER = 'روستای ب'


def day(n):
    return timezone.localdate() + timedelta(days=n)


def jalali_weekday(d):          # 0 = Saturday ... 6 = Friday
    return (d.weekday() + 2) % 7


def flash(response):
    return [str(m) for m in get_messages(response.wsgi_request)]


class Clinic(TestCase):
    """The engineer receives visitors on one weekday, 09:00-12:00 in 30 minute slots."""

    def setUp(self):
        self.dehyari = make_user('dehyari', city_village=VILLAGE)
        self.municipality = make_municipality(self.dehyari, VILLAGE)
        self.engineer = make_user('engineer', city_village=VILLAGE)
        self.inspector = make_user('inspector', city_village=VILLAGE)
        self.council = make_user('council', city_village=VILLAGE)
        self.clerk = make_user('clerk', city_village=VILLAGE)
        self.accountant = make_user('accountant', city_village=VILLAGE)
        self.citizen = make_user('citizen', city_village=VILLAGE)
        self.citizen2 = make_user('owner', city_village=VILLAGE)
        self.stranger = make_user('engineer', city_village=OTHER)
        # make_user updates the profile row behind the cached object; reload so direct calls see the real role
        for name in ('dehyari', 'engineer', 'inspector', 'council', 'clerk', 'accountant', 'citizen', 'citizen2', 'stranger'):
            setattr(self, name, User.objects.get(pk=getattr(self, name).pk))
        self.target = day(3)
        AvailabilityRule.objects.create(provider=self.engineer, weekday=jalali_weekday(self.target),
                                        start_time=time(9), end_time=time(12), slot_minutes=30)

    def start(self, hh=9, mm=0, date=None):
        return f'{(date or self.target).isoformat()}T{hh:02d}:{mm:02d}'

    def book(self, who=None, provider=None, hh=9, mm=0, date=None, subject='مشاوره‌ی نقشه'):
        return client_for(who or self.citizen).post(
            reverse('main:appointment_book', args=[(provider or self.engineer).id]),
            {'start': self.start(hh, mm, date), 'subject': subject, 'notes': ''})

    def panel(self, who, **params):
        """The panel page of ``who`` opened on the appointment section."""
        url = visits.panel_url(who, **params).split('#')[0]
        return client_for(who).get(url)

    def slots_page(self, who=None, provider=None, date=None):
        return self.panel(who or self.citizen, provider=(provider or self.engineer).id,
                          date=(date or self.target).isoformat()).content.decode()


class Availability(Clinic):
    def post_rules(self, who, **days):
        data = {}
        for d in range(7):
            on = days.get(f'd{d}')
            if on:
                data.update({f'd{d}_on': 'on', f'd{d}_from': on[0], f'd{d}_to': on[1], f'd{d}_len': on[2]})
        return client_for(who).post(reverse('main:availability'), data)

    def test_engineer_inspector_and_council_save_weekly_hours(self):
        for who in (self.engineer, self.inspector, self.council):
            r = self.post_rules(who, d0=('08:00', '12:00', '20'), d2=('14:00', '16:00', '30'))
            self.assertEqual(r.status_code, 302)
            rules = {x.weekday: (x.start_time, x.end_time, x.slot_minutes) for x in AvailabilityRule.objects.filter(provider=who)}
            self.assertEqual(rules, {0: (time(8), time(12), 20), 2: (time(14), time(16), 30)})   # replaces the old set

    def test_invalid_hours_are_refused_and_nothing_changes(self):
        before = AvailabilityRule.objects.count()
        for bad in (('12:00', '09:00', '30'), ('09:00', '09:00', '30'), ('09:00', '12:00', '5'),
                    ('09:00', '12:00', '500'), ('xx', '12:00', '30')):
            response = self.post_rules(self.engineer, d1=bad)
            self.assertEqual(response.status_code, 302)
            self.assertTrue(flash(response), bad)
        self.assertEqual(AvailabilityRule.objects.count(), before)

    def test_only_technical_staff_and_council_have_office_hours(self):
        for who in (self.citizen, self.dehyari, self.clerk, self.accountant):
            self.post_rules(who, d1=('09:00', '12:00', '30'))
            self.assertFalse(AvailabilityRule.objects.filter(provider=who).exists(), who.profile.role)

    def test_the_engineers_panel_shows_the_current_rules(self):
        page = self.panel(self.engineer).content.decode()
        self.assertIn('value="09:00"', page)
        self.assertIn('ساعت‌های حضور من', page)


class Slots(Clinic):
    def test_lists_free_slots_on_the_working_day(self):
        page = self.slots_page()
        for t in ('09:00', '09:30', '11:30'):
            self.assertIn(f'value="{self.start(int(t[:2]), int(t[3:]))}"', page)
        self.assertNotIn(f'value="{self.start(12, 0)}"', page)

    def test_day_without_hours_shows_the_empty_state(self):
        self.assertIn('وقت آزادی نیست', self.slots_page(date=day(4)))

    def test_taken_slot_disappears_for_everyone(self):
        self.book(self.citizen, hh=9)
        self.assertNotIn(f'value="{self.start(9, 0)}"', self.slots_page(self.citizen2))

    def test_beyond_two_weeks_and_past_days_have_no_slots(self):
        far = day(15)
        AvailabilityRule.objects.update_or_create(provider=self.engineer, weekday=jalali_weekday(far),
                                                  defaults=dict(start_time=time(9), end_time=time(10), slot_minutes=30))
        self.assertNotIn('name="start"', self.slots_page(date=far))
        response = self.book(date=far)
        self.assertFalse(Appointment.objects.exists())
        self.assertTrue(flash(response))

    def test_a_citizen_is_offered_the_technical_staff_and_the_council_of_the_village_only(self):
        page = self.panel(self.citizen).content.decode()
        for who in (self.engineer, self.inspector, self.council):
            self.assertIn(who.username, page)
        for who in (self.dehyari, self.clerk, self.accountant, self.stranger, self.citizen2):
            self.assertNotIn(who.username, page, who.profile.role)

    def test_after_switching_municipality_that_villages_staff_are_offered(self):
        other_dehyari = make_user('dehyari', city_village=OTHER)
        other = make_municipality(other_dehyari, OTHER)
        self.assertNotIn(self.stranger.username, self.panel(self.citizen).content.decode())
        type(self.citizen.profile).objects.filter(pk=self.citizen.profile.pk).update(active_municipality=other)
        citizen = type(self.citizen).objects.get(pk=self.citizen.pk)
        page = self.panel(citizen).content.decode()
        self.assertIn(self.stranger.username, page)
        self.assertIn(self.engineer.username, page)                         # the home village stays bookable


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

    def test_the_inspector_and_a_council_member_can_be_booked_too(self):
        for who in (self.inspector, self.council):
            AvailabilityRule.objects.create(provider=who, weekday=jalali_weekday(self.target), start_time=time(9), end_time=time(12))
            self.book(provider=who)
        self.assertEqual(Appointment.objects.count(), 2)

    def test_same_slot_by_another_person_is_a_conflict(self):
        self.book(self.citizen)
        response = self.book(self.citizen2)
        self.assertEqual(Appointment.objects.count(), 1)
        self.assertIn('رزرو شد', ' '.join(flash(response)))

    def test_repeating_my_own_booking_is_harmless(self):
        for _ in range(3):
            self.assertEqual(self.book(self.citizen).status_code, 302)
        self.assertEqual(Appointment.objects.count(), 1)
        self.assertEqual(Notification.objects.filter(user=self.engineer).count(), 1)

    def test_times_off_the_grid_or_outside_hours_are_refused(self):
        for hh, mm in ((9, 10), (8, 30), (12, 0), (13, 0)):
            self.assertTrue(flash(self.book(hh=hh, mm=mm)), (hh, mm))
        self.assertFalse(Appointment.objects.exists())

    def test_slots_less_than_an_hour_away_cannot_be_booked(self):
        now = timezone.localtime()
        today = now.date()
        AvailabilityRule.objects.update_or_create(provider=self.engineer, weekday=jalali_weekday(today),
                                                  defaults=dict(start_time=time(0, 0), end_time=time(23, 30), slot_minutes=30))
        soon = (now + timedelta(minutes=20)).replace(second=0, microsecond=0)
        soon = soon.replace(minute=0 if soon.minute < 30 else 30)
        client_for(self.citizen).post(reverse('main:appointment_book', args=[self.engineer.id]),
                                      {'start': soon.strftime('%Y-%m-%dT%H:%M'), 'subject': 'x'})
        self.assertFalse(Appointment.objects.exists())

    def test_validation(self):
        self.book(subject='  ')
        self.book(subject='ا' * 201)
        client_for(self.citizen).post(reverse('main:appointment_book', args=[self.engineer.id]), {'start': 'garbage', 'subject': 'x'})
        self.assertFalse(Appointment.objects.exists())

    def test_a_refused_booking_keeps_what_was_typed(self):
        client = client_for(self.citizen)
        client.post(reverse('main:appointment_book', args=[self.engineer.id]),
                    {'start': self.start(9, 10), 'subject': 'نقشه‌ی خانه', 'notes': ''})
        page = client.get(visits.panel_url(self.citizen, provider=self.engineer.id, date=self.target.isoformat()).split('#')[0]).content.decode()
        self.assertIn('نقشه‌ی خانه', page)

    def test_cannot_book_another_village_a_citizen_or_a_non_provider_role(self):
        AvailabilityRule.objects.create(provider=self.stranger, weekday=jalali_weekday(self.target), start_time=time(9), end_time=time(12))
        for target in (self.stranger, self.citizen2, self.dehyari, self.clerk, self.accountant):
            self.book(provider=target)
        self.assertFalse(Appointment.objects.exists())

    def test_staff_cannot_book(self):
        AvailabilityRule.objects.create(provider=self.council, weekday=jalali_weekday(self.target), start_time=time(9), end_time=time(12))
        for who in (self.engineer, self.inspector, self.dehyari, self.clerk, self.accountant):
            self.book(who, provider=self.council)
        self.assertFalse(Appointment.objects.exists())

    def test_open_appointment_cap(self):
        for hh in range(9, 12):
            self.book(hh=hh)
        other = day(10)
        AvailabilityRule.objects.update_or_create(provider=self.engineer, weekday=jalali_weekday(other),
                                                  defaults=dict(start_time=time(9), end_time=time(12), slot_minutes=30))
        for hh, mm in ((9, 0), (9, 30)):
            self.book(date=other, hh=hh, mm=mm)
        self.assertEqual(Appointment.objects.count(), 5)
        response = self.book(date=other, hh=10)
        self.assertEqual(Appointment.objects.count(), 5)
        self.assertIn('حداکثر', ' '.join(flash(response)))

    def test_database_itself_refuses_a_double_booking(self):
        self.book(self.citizen)
        existing = Appointment.objects.get()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Appointment.objects.create(provider=self.engineer, client=self.citizen2, start=existing.start,
                                       end=existing.end, subject='x')

    def test_anonymous_must_log_in(self):
        self.assertEqual(self.client.get(reverse('main:appointments')).status_code, 302)
        self.assertIn('login', self.client.get(reverse('main:appointments'))['Location'])


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
        self.book(self.citizen2)
        self.assertEqual(Appointment.objects.filter(client=self.citizen2).count(), 1)

    def test_either_side_can_cancel_and_the_slot_reopens(self):
        self.act(self.citizen, 'cancel')
        self.assertEqual((self.status(), self.appt.cancelled_by), ('cancelled', self.citizen))
        self.book(self.citizen2)
        self.assertEqual(Appointment.objects.filter(client=self.citizen2).count(), 1)

    def test_client_cannot_confirm_and_strangers_see_nothing(self):
        self.assertIn('فقط کارمند', ' '.join(flash(self.act(self.citizen, 'confirm'))))
        self.act(self.citizen2, 'cancel')
        self.act(self.stranger, 'confirm')
        self.act(self.council, 'confirm')
        self.assertEqual(self.status(), 'pending')

    def test_final_states_do_not_change_again(self):
        self.act(self.engineer, 'reject')
        self.act(self.engineer, 'confirm')
        self.assertEqual(self.status(), 'rejected')

    def test_repeating_the_same_action_is_harmless(self):
        self.act(self.engineer, 'confirm')
        self.assertEqual(self.act(self.engineer, 'confirm').status_code, 302)
        self.assertEqual(Notification.objects.filter(user=self.citizen).count(), 1)

    def test_complete_only_after_it_started(self):
        self.act(self.engineer, 'confirm')
        self.act(self.engineer, 'complete')
        self.assertEqual(self.status(), 'confirmed')
        Appointment.objects.filter(pk=self.appt.pk).update(start=timezone.now() - timedelta(hours=2),
                                                           end=timezone.now() - timedelta(hours=1, minutes=30))
        self.act(self.engineer, 'complete')
        self.assertEqual(self.status(), 'completed')

    def test_unknown_action(self):
        self.act(self.engineer, 'explode')
        self.assertEqual(self.status(), 'pending')


class InsideThePanels(Clinic):
    """No page of its own: the section is a tab / block of each panel, and the old URLs lead there."""

    def setUp(self):
        super().setUp()
        for who in (self.inspector, self.council):
            AvailabilityRule.objects.create(provider=who, weekday=jalali_weekday(self.target), start_time=time(9), end_time=time(12))
        self.book(self.citizen, provider=self.engineer, subject='مشاوره‌ی نقشه')
        self.book(self.citizen, provider=self.inspector, subject='بازدید ساختمان')
        self.book(self.citizen, provider=self.council, subject='طرح در شورا')

    def test_the_citizens_panel_lists_their_appointments_in_its_own_tab(self):
        response = self.panel(self.citizen)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['initial_tab'], 'visits')
        page = response.content.decode()
        for subject in ('مشاوره‌ی نقشه', 'بازدید ساختمان', 'طرح در شورا'):
            self.assertIn(subject, page)
        self.assertIn('id="visits-tab"', page)

    def test_the_provider_panels_show_the_requests_they_received(self):
        for who, subject in ((self.engineer, 'مشاوره‌ی نقشه'), (self.inspector, 'بازدید ساختمان'), (self.council, 'طرح در شورا')):
            page = self.panel(who).content.decode()
            self.assertIn(subject, page, who.profile.role)
            self.assertIn('ساعت‌های حضور من', page, who.profile.role)

    def test_a_provider_decides_from_the_panel_and_comes_back_to_it(self):
        appt = Appointment.objects.get(provider=self.council)
        response = client_for(self.council).post(reverse('main:appointment_action', args=[appt.id]), {'action': 'confirm'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], visits.panel_url(self.council))
        self.assertIn(reverse('main:council_dashboard'), response['Location'])

    def test_where_each_role_lands(self):
        owner = reverse('main:owner_dashboard')
        self.assertTrue(visits.panel_url(self.citizen).startswith(owner))
        self.assertTrue(visits.panel_url(self.citizen2).startswith(owner))
        self.assertIn(reverse('main:inspector_dashboard'), visits.panel_url(self.inspector))
        self.assertIn(reverse('main:council_dashboard'), visits.panel_url(self.council))
        self.assertTrue(visits.panel_url(self.engineer).endswith('#visits-section'))
        for who in (self.dehyari, self.clerk, self.accountant):
            self.assertEqual(visits.panel_url(who), reverse('main:dashboard'))

    def test_the_old_pages_redirect_into_the_panel(self):
        for name, args in (('appointments', []), ('appointment_providers', []), ('availability', []),
                           ('appointment_book', [self.engineer.id])):
            for who in (self.citizen, self.engineer, self.council):
                response = client_for(who).get(reverse(f'main:{name}', args=args))
                self.assertEqual(response.status_code, 302, (name, who.profile.role))
                self.assertTrue(response['Location'].startswith(visits.panel_url(who).split('?')[0].split('#')[0]), name)

    def test_roles_without_appointments_get_no_section(self):
        for who, name in ((self.accountant, 'accountant_dashboard'), (self.dehyari, 'dehyari_dashboard'),
                          (self.clerk, 'clerk_dashboard')):
            page = client_for(who).get(reverse(f'main:{name}')).content.decode()
            self.assertNotIn('id="vp-title"', page, name)
            self.assertNotIn('گرفتن وقت ملاقات', page, name)

    def test_the_navbar_and_dock_link_only_for_roles_that_have_the_section(self):
        link = f'href="{visits.panel_url(self.citizen)}"'
        self.assertIn(link, client_for(self.citizen).get(reverse('main:my_requests'), follow=True).content.decode())
        for who in (self.clerk, self.accountant):
            page = client_for(who).get(reverse('main:my_requests'), follow=True).content.decode()
            self.assertNotIn('title="وقت‌های ملاقات"', page)
            self.assertNotIn(reverse('main:appointments'), page)

    def test_the_clerk_desk_has_no_visits_tab(self):
        page = client_for(self.clerk).get(reverse('main:clerk_dashboard'), {'tab': 'visits'}).content.decode()
        self.assertNotIn('وقت‌ملاقات', page)
        self.assertNotIn('ساعت‌های حضور من', page)
