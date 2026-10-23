"""The administrative expert (کارشناس اداری): giving the role, the desk page, the reminder, the Jalali calendar."""
from datetime import datetime, time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from main.models import Appointment, Notification, RoleGrant, UserProfile
from main.office import desk, letters
from main.tests.helpers import client_for, make_municipality, make_request, make_user

VILLAGE, OTHER = 'روستای الف', 'روستای ب'


class Village(TestCase):
    def setUp(self):
        self.dehyari = make_user('dehyari', city_village=VILLAGE)
        make_municipality(self.dehyari, VILLAGE)
        self.clerk = make_user('clerk', city_village=VILLAGE)
        self.citizen = make_user('citizen', city_village=VILLAGE)
        # make_user updates the profile row behind the cached object; reload so direct calls see the real role
        self.dehyari, self.clerk = (User.objects.get(pk=u.pk) for u in (self.dehyari, self.clerk))


class GivingTheRole(Village):
    def test_dehyari_grants_and_revokes_the_role(self):
        client = client_for(self.dehyari)
        client.post(reverse('main:role_grant'), {'user_id': self.citizen.id, 'role': 'clerk'})
        self.assertEqual(UserProfile.objects.get(user=self.citizen).role, 'clerk')
        self.assertTrue(RoleGrant.objects.filter(user=self.citizen, role='clerk', revoked_at__isnull=True).exists())
        client.post(reverse('main:role_revoke', args=[self.citizen.id]))
        self.assertEqual(UserProfile.objects.get(user=self.citizen).role, 'citizen')

    def test_dehyari_creates_a_clerk_account(self):
        response = client_for(self.dehyari).post(reverse('main:role_create_account'), {
            'first_name': 'سارا', 'last_name': 'احمدی', 'username': 'sara.clerk', 'national_id': '0012345678',
            'mobile_number': '09121234567', 'role': 'clerk'})
        self.assertLess(response.status_code, 400)
        self.assertEqual(UserProfile.objects.get(user__username='sara.clerk').role, 'clerk')

    def test_clerk_lands_on_the_desk_after_login(self):
        response = client_for(self.clerk).get(reverse('main:dashboard'))
        self.assertRedirects(response, reverse('main:clerk_dashboard'), fetch_redirect_response=False)


class WhoMayOpenTheDesk(Village):
    def test_clerk_and_dehyari_open_it(self):
        for user in (self.clerk, self.dehyari):
            self.assertEqual(client_for(user).get(reverse('main:clerk_dashboard')).status_code, 200, user)

    def test_other_roles_are_turned_away(self):
        for role in ('citizen', 'owner', 'engineer', 'inspector', 'accountant', 'council'):
            response = client_for(make_user(role)).get(reverse('main:clerk_dashboard'))
            self.assertRedirects(response, reverse('main:dashboard'), fetch_redirect_response=False)

    def test_anonymous_goes_to_login(self):
        response = client_for().get(reverse('main:clerk_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('main:login'), response.url)

    def test_reminder_is_closed_to_other_roles(self):
        sr = make_request(self.citizen, status='requires_documents')
        for role in ('citizen', 'accountant'):
            client_for(make_user(role, city_village=VILLAGE)).post(reverse('main:clerk_remind', args=[sr.id]))
        self.assertFalse(Notification.objects.filter(related_request=sr).exists())


class TheDeskPage(Village):
    def open(self, user=None, **params):
        return client_for(user or self.clerk).get(reverse('main:clerk_dashboard'), params)

    def test_empty_desk_renders(self):
        self.assertContains(self.open(), 'کار عقب‌افتاده‌ای ندارید')
        self.assertContains(self.open(tab='follow'), 'درخواستی منتظر مدارک نیست')

    def test_counts_unread_letters_and_lists_them(self):
        letters.compose(self.dehyari, to=[self.clerk.id], subject='گزارش ماهانه', body='متن')
        response = self.open()
        self.assertEqual(response.context['stats']['unread'], 1)
        self.assertContains(response, 'گزارش ماهانه')

    def test_todays_visit_is_on_the_agenda(self):
        start = timezone.now().replace(hour=12, minute=0, second=0, microsecond=0)
        if timezone.localdate() != timezone.localtime(start).date():
            start = timezone.now()
        Appointment.objects.create(provider=self.clerk, client=self.citizen, start=start, end=start + timedelta(minutes=30),
                                   subject='پرسش درباره پروانه', status='confirmed')
        response = self.open()
        self.assertContains(response, 'پرسش درباره پروانه')
        self.assertEqual(response.context['stats']['today'], 1)

    def test_follow_ups_are_limited_to_the_village(self):
        mine = make_request(self.citizen, status='requires_documents', title='نقشه ساختمان')
        foreign = make_request(make_user('citizen', city_village=OTHER), status='requires_documents', title='درخواست غریبه')
        make_request(self.citizen, status='pending', title='در جریان')
        response = self.open(tab='follow')
        self.assertContains(response, mine.title)
        self.assertNotContains(response, foreign.title)
        self.assertNotContains(response, 'در جریان')
        self.assertEqual(response.context['stats']['waiting_docs'], 1)

    def test_clerk_without_a_village_sees_no_requests(self):
        make_request(self.citizen, status='requires_documents')
        response = self.open(make_user('clerk'))
        self.assertEqual(response.context['stats']['waiting_docs'], 0)


class TheReminder(Village):
    def remind(self, sr, user=None):
        return client_for(user or self.clerk).post(reverse('main:clerk_remind', args=[sr.id]), follow=True)

    def test_citizen_is_notified_once_a_day(self):
        sr = make_request(self.citizen, status='requires_documents', title='نقشه ساختمان')
        self.remind(sr)
        self.assertEqual(Notification.objects.filter(user=self.citizen, title=desk.REMINDER_TITLE, related_request=sr).count(), 1)
        again = self.remind(sr)
        self.assertEqual(Notification.objects.filter(user=self.citizen, title=desk.REMINDER_TITLE).count(), 1)
        self.assertContains(again, 'یادآوری فرستاده شده است')

    def test_other_village_request_is_not_reachable(self):
        sr = make_request(make_user('citizen', city_village=OTHER), status='requires_documents')
        self.remind(sr)
        self.assertFalse(Notification.objects.filter(related_request=sr).exists())

    def test_request_that_no_longer_waits_is_not_reminded(self):
        sr = make_request(self.citizen, status='approved')
        self.remind(sr)
        self.assertFalse(Notification.objects.filter(related_request=sr).exists())

    def test_get_is_not_allowed(self):
        sr = make_request(self.citizen, status='requires_documents')
        response = client_for(self.clerk).get(reverse('main:clerk_remind', args=[sr.id]))
        self.assertEqual(response.status_code, 405)


class TheCalendar(TestCase):
    def test_parse_month_falls_back_on_junk(self):
        today = desk.jdatetime.date(1405, 6, 10)
        self.assertEqual(desk.parse_month('1404-12', today), (1404, 12))
        for junk in ('', 'abc', '1405-13', '1405-00', '1405', '9999-01', '1405-3-2'):
            self.assertEqual(desk.parse_month(junk, today), (1405, 6), junk)

    def test_shift_month_crosses_the_year(self):
        self.assertEqual(desk.shift_month(1405, 1, -1), (1404, 12))
        self.assertEqual(desk.shift_month(1404, 12, 1), (1405, 1))

    def test_month_lengths(self):
        self.assertEqual(desk.month_days(1405, 1), 31)
        self.assertEqual(desk.month_days(1405, 7), 30)
        self.assertEqual(desk.month_days(1404, 12), 29)       # 1404 is not a leap year
        self.assertEqual(desk.month_days(1403, 12), 30)       # 1403 is

    def test_grid_has_whole_weeks_and_every_day_once(self):
        grid = desk.month_grid(make_user('clerk'), 1405, 1, today=desk.jdatetime.date(1405, 1, 15).togregorian())
        self.assertTrue(all(len(week) == 7 for week in grid['weeks']))
        days = [cell['day'] for week in grid['weeks'] for cell in week if cell]
        self.assertEqual(days, list(range(1, 32)))
        today = [cell for week in grid['weeks'] for cell in week if cell and cell['today']]
        self.assertEqual([c['day'] for c in today], [15])
        self.assertEqual((grid['prev'], grid['next']), ('1404-12', '1405-02'))

    def test_first_day_sits_under_its_weekday(self):
        first = desk.jdatetime.date(1405, 1, 1)
        grid = desk.month_grid(make_user('clerk'), 1405, 1)
        row = grid['weeks'][0]
        self.assertEqual(row.index(next(c for c in row if c and c['day'] == 1)), first.weekday())

    def test_visit_days_are_marked(self):
        clerk, client = make_user('clerk'), make_user('citizen')
        day = desk.jdatetime.date(1405, 1, 10).togregorian()
        start = timezone.make_aware(datetime.combine(day, time.min)) + timedelta(hours=10)
        Appointment.objects.create(provider=clerk, client=client, start=start, end=start + timedelta(minutes=30), subject='x')
        grid = desk.month_grid(clerk, 1405, 1)
        marked = {c['day']: c['count'] for week in grid['weeks'] for c in week if c and c['count']}
        self.assertEqual(marked, {10: 1})
        self.assertEqual(grid['total'], 1)


class LettersReachTheClerk(Village):
    def test_clerk_can_write_to_and_receive_from_colleagues(self):
        sent = letters.compose(self.clerk, to=[self.dehyari.id], subject='ارسال از میز اداری', body='سلام')
        self.assertEqual(sent.status, 'sent')
        self.assertIn(self.clerk, [u for u in letters.allowed_recipients(self.dehyari)])


class Tabs(Village):
    def open(self, **params):
        return client_for(self.clerk).get(reverse('main:clerk_dashboard'), params)

    def test_every_tab_renders_and_unknown_tab_falls_back_to_today(self):
        for tab in ('today', 'messages', 'visits', 'follow'):
            self.assertContains(self.open(tab=tab), f'cd-tabs', msg_prefix=tab)
        self.assertEqual(self.open(tab='nonsense').context['tab'], 'today')

    def test_messages_tab_holds_the_messenger_inline(self):
        page = self.open(tab='messages')
        self.assertContains(page, 'id="mg"')
        self.assertContains(page, 'messenger.js')

    def test_opening_a_thread_from_the_today_tab_links_into_the_messenger_tab(self):
        letters.compose(self.dehyari, to=[self.clerk.id], subject='نامه‌ی امروز', body='متن')
        page = self.open()
        self.assertContains(page, '?tab=messages&open=l')


class VisitsInTheDesk(Village):
    def setUp(self):
        super().setUp()
        self.start = timezone.now() + timedelta(days=1)
        self.visit = Appointment.objects.create(provider=self.clerk, client=self.citizen, start=self.start,
                                                end=self.start + timedelta(minutes=30), subject='گواهی')

    def post(self, name, *args, **data):
        return client_for(self.clerk).post(reverse(f'main:{name}', args=args), data, follow=True)

    def test_clerk_confirms_and_the_citizen_is_told(self):
        response = self.post('clerk_visit_action', self.visit.id, action='confirm')
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.status, 'confirmed')
        self.assertContains(response, 'وقت ملاقات شما تایید شد')
        self.assertTrue(Notification.objects.filter(user=self.citizen, title='وقت ملاقات').exists())

    def test_clerk_cannot_decide_someone_elses_visit(self):
        other = make_user('engineer', city_village=VILLAGE)
        elsewhere = Appointment.objects.create(provider=other, client=self.citizen, start=self.start + timedelta(days=1),
                                               end=self.start + timedelta(days=1, minutes=30), subject='x')
        self.post('clerk_visit_action', elsewhere.id, action='confirm')
        elsewhere.refresh_from_db()
        self.assertEqual(elsewhere.status, 'pending')

    def test_weekly_hours_are_saved_from_the_desk(self):
        from main.models import AvailabilityRule
        self.post('clerk_hours', d0_on='on', d0_from='08:00', d0_to='12:00', d0_len='30')
        rule = AvailabilityRule.objects.get(provider=self.clerk)
        self.assertEqual((rule.weekday, rule.slot_minutes), (0, 30))
        response = self.post('clerk_hours', d0_on='on', d0_from='12:00', d0_to='08:00', d0_len='30')
        self.assertContains(response, 'ساعت پایان باید بعد از شروع باشد')

    def test_booking_a_colleague_from_the_desk(self):
        from datetime import time
        from main.models import AvailabilityRule
        from main.tests.test_appointments import jalali_weekday
        engineer = User.objects.get(pk=make_user('engineer', city_village=VILLAGE).pk)
        day = (timezone.now() + timedelta(days=3)).date()
        AvailabilityRule.objects.create(provider=engineer, weekday=jalali_weekday(day), start_time=time(9), end_time=time(12))
        page = client_for(self.clerk).get(reverse('main:clerk_dashboard'), {'tab': 'visits', 'provider': engineer.id, 'date': day.isoformat()})
        self.assertContains(page, 'name="start"')
        self.post('clerk_book', provider=engineer.id, start=f'{day.isoformat()}T09:00', subject='مشورت')
        self.assertTrue(Appointment.objects.filter(provider=engineer, client=self.clerk, subject='مشورت').exists())

    def test_visit_actions_are_closed_to_other_roles(self):
        r = client_for(self.citizen).post(reverse('main:clerk_visit_action', args=[self.visit.id]), {'action': 'confirm'})
        self.assertEqual(r.status_code, 302)
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.status, 'pending')
