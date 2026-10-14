"""Council panel: voting box, meeting calendar, messages and settings inside one page."""
from datetime import timedelta

import jdatetime
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from main.models import ServiceRequest, Conversation, CouncilMeeting, CouncilPoll, CouncilPollVote, Message
from main.tests.helpers import client_for, make_user

V = 'روستای الف'


def member(role='council', village=V):
    return make_user(role, city_village=village)


def make_poll(author, title='طرح-پل-روستا', status='open'):
    return CouncilPoll.objects.create(title=title, village=V, created_by=author, status=status)


class PollAccess(TestCase):
    def setUp(self):
        self.a, self.b = member(), member()
        self.poll = make_poll(self.a)

    def vote(self, user, choice='approve', poll=None):
        return client_for(user).post(reverse('main:council_poll_vote', args=[(poll or self.poll).id]), {'choice': choice})

    def test_member_votes_once_and_second_vote_is_refused(self):
        self.vote(self.a, 'approve')
        self.vote(self.a, 'reject')
        self.assertEqual(CouncilPollVote.objects.filter(poll=self.poll, member=self.a).count(), 1)
        self.assertEqual(CouncilPollVote.objects.get(member=self.a).choice, 'approve')

    def test_invalid_choice_is_refused(self):
        self.vote(self.a, 'maybe')
        self.assertFalse(CouncilPollVote.objects.exists())

    def test_closed_poll_takes_no_votes(self):
        self.poll.status = 'closed'
        self.poll.save()
        self.vote(self.b)
        self.assertFalse(CouncilPollVote.objects.exists())

    def test_other_village_council_cannot_vote_or_see(self):
        outsider = member(village='روستای ب')
        self.vote(outsider)
        self.assertFalse(CouncilPollVote.objects.exists())
        page = client_for(outsider).get(reverse('main:council_dashboard'))
        self.assertNotContains(page, 'طرح-پل-روستا')

    def test_non_council_roles_cannot_vote_create_or_close(self):
        for role in ('citizen', 'owner', 'dehyari', 'accountant'):
            u = member(role)
            self.vote(u)
            client_for(u).post(reverse('main:council_poll_create'), {'title': 'x'})
            client_for(u).post(reverse('main:council_poll_close', args=[self.poll.id]))
        self.assertFalse(CouncilPollVote.objects.exists())
        self.assertEqual(CouncilPoll.objects.count(), 1)
        self.poll.refresh_from_db()
        self.assertEqual(self.poll.status, 'open')

    def test_anonymous_is_sent_to_login(self):
        r = client_for().post(reverse('main:council_poll_vote', args=[self.poll.id]), {'choice': 'approve'})
        self.assertEqual(r.status_code, 302)
        self.assertIn('login', r.url)

    def test_create_validates_title_and_scopes_village(self):
        c = client_for(self.a)
        c.post(reverse('main:council_poll_create'), {'title': '   '})
        c.post(reverse('main:council_poll_create'), {'title': 'ا' * 201})
        self.assertEqual(CouncilPoll.objects.count(), 1)
        c.post(reverse('main:council_poll_create'), {'title': 'آسفالت', 'description': 'توضیح'})
        p = CouncilPoll.objects.get(title='آسفالت')
        self.assertEqual((p.village, p.status, p.created_by), (V, 'open', self.a))

    def test_close_sets_status_and_results_show_counts(self):
        self.vote(self.a, 'approve')
        self.vote(self.b, 'reject')
        client_for(self.a).post(reverse('main:council_poll_close', args=[self.poll.id]))
        self.poll.refresh_from_db()
        self.assertEqual(self.poll.status, 'closed')
        self.assertEqual(self.poll.tally(), {'approve': 1, 'reject': 1, 'abstain': 0, 'total': 2})

    def test_other_village_cannot_close(self):
        client_for(member(village='روستای ب')).post(reverse('main:council_poll_close', args=[self.poll.id]))
        self.poll.refresh_from_db()
        self.assertEqual(self.poll.status, 'open')

    def test_dehyari_sees_polls_read_only(self):
        d = member('dehyari')
        page = client_for(d).get(reverse('main:council_dashboard'))
        self.assertContains(page, 'طرح-پل-روستا')
        self.assertNotContains(page, reverse('main:council_poll_vote', args=[self.poll.id]))


class Meetings(TestCase):
    def setUp(self):
        self.a = member()
        self.when = jdatetime.date.fromgregorian(date=(timezone.now() + timedelta(days=3)).date()).strftime('%Y/%m/%d')

    def save(self, user, **data):
        body = {'title': 'جلسه عادی', 'date': self.when, 'time': '10:30', 'location': 'سالن', 'agenda': 'دستور'}
        body.update(data)
        return client_for(user).post(reverse('main:council_meeting_save'), body)

    def test_create_with_jalali_date(self):
        self.save(self.a)
        m = CouncilMeeting.objects.get()
        self.assertEqual((m.village, m.status, m.created_by), (V, 'scheduled', self.a))
        local = timezone.localtime(m.starts_at)
        self.assertEqual(jdatetime.date.fromgregorian(date=local.date()).strftime('%Y/%m/%d'), self.when)
        self.assertEqual(local.strftime('%H:%M'), '10:30')

    def test_persian_digits_accepted(self):
        self.save(self.a, date=self.when.translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')), time='۱۰:۳۰')
        self.assertEqual(CouncilMeeting.objects.count(), 1)

    def test_bad_input_refused(self):
        for bad in ({'date': '1403/13/40'}, {'date': 'abc'}, {'time': '25:99'}, {'title': ''}, {'title': 'ا' * 201}):
            self.save(self.a, **bad)
        self.assertFalse(CouncilMeeting.objects.exists())

    def test_edit_and_cancel(self):
        self.save(self.a)
        m = CouncilMeeting.objects.get()
        client_for(self.a).post(reverse('main:council_meeting_save'),
                                {'meeting_id': m.id, 'title': 'عوض شد', 'date': self.when, 'time': '09:00'})
        m.refresh_from_db()
        self.assertEqual(m.title, 'عوض شد')
        client_for(self.a).post(reverse('main:council_meeting_cancel', args=[m.id]))
        m.refresh_from_db()
        self.assertEqual(m.status, 'cancelled')

    def test_other_village_and_other_roles_cannot_touch(self):
        self.save(self.a)
        m = CouncilMeeting.objects.get()
        for u in (member(village='روستای ب'), member('citizen'), member('dehyari')):
            client_for(u).post(reverse('main:council_meeting_cancel', args=[m.id]))
            client_for(u).post(reverse('main:council_meeting_save'),
                               {'meeting_id': m.id, 'title': 'هک', 'date': self.when, 'time': '09:00'})
            self.save(u, title='جدید')
        m.refresh_from_db()
        self.assertEqual((m.status, m.title), ('scheduled', 'جلسه عادی'))
        self.assertEqual(CouncilMeeting.objects.filter(village=V).count(), 1)

    def test_calendar_month_param_renders_and_garbage_falls_back(self):
        self.save(self.a)
        c = client_for(self.a)
        self.assertContains(c.get(reverse('main:council_dashboard')), 'جلسه عادی')
        self.assertEqual(c.get(reverse('main:council_dashboard') + '?ym=garbage').status_code, 200)
        self.assertEqual(c.get(reverse('main:council_dashboard') + '?ym=1403-13').status_code, 200)

    def test_other_village_meetings_hidden(self):
        self.save(self.a)
        page = client_for(member(village='روستای ب')).get(reverse('main:council_dashboard'))
        self.assertNotContains(page, 'جلسه عادی')


class MessagesAndSettings(TestCase):
    def setUp(self):
        self.a, self.b = member(), member('dehyari')

    def test_new_message_to_village_colleague(self):
        r = client_for(self.a).post(reverse('main:council_message_new'),
                                    {'recipient_id': self.b.id, 'subject': 'سلام', 'message_body': 'متن'})
        self.assertEqual(r.status_code, 302)
        conv = Conversation.objects.get()
        self.assertEqual(set(conv.participants.all()), {self.a, self.b})
        self.assertEqual(Message.objects.get().body, 'متن')

    def test_cannot_message_other_village_or_empty(self):
        outsider = member(village='روستای ب')
        client_for(self.a).post(reverse('main:council_message_new'),
                                {'recipient_id': outsider.id, 'subject': 's', 'message_body': 'b'})
        client_for(self.a).post(reverse('main:council_message_new'),
                                {'recipient_id': self.b.id, 'subject': '', 'message_body': ''})
        self.assertFalse(Conversation.objects.exists())

    def test_reply_only_for_participants(self):
        client_for(self.a).post(reverse('main:council_message_new'),
                                {'recipient_id': self.b.id, 'subject': 's', 'message_body': 'one'})
        conv = Conversation.objects.get()
        url = reverse('main:council_message_reply', args=[conv.id])
        client_for(self.b).post(url, {'message_body': 'two'})
        client_for(member()).post(url, {'message_body': 'intruder'})
        self.assertEqual(list(Message.objects.values_list('body', flat=True)), ['one', 'two'])

    def test_thread_hidden_from_non_participants(self):
        client_for(self.a).post(reverse('main:council_message_new'),
                                {'recipient_id': self.b.id, 'subject': 'محرمانه', 'message_body': 'راز'})
        conv = Conversation.objects.get()
        page = client_for(member()).get(reverse('main:council_dashboard') + f'?conv={conv.id}')
        self.assertNotContains(page, 'راز')

    def test_settings_update_profile(self):
        client_for(self.a).post(reverse('main:council_settings_save'),
                                {'first_name': 'علی', 'last_name': 'رسولی', 'email': 'a@b.ir', 'mobile_number': '09121234567'})
        self.a.refresh_from_db()
        self.assertEqual((self.a.first_name, self.a.email, self.a.profile.mobile_number), ('علی', 'a@b.ir', '09121234567'))

    def test_settings_bad_mobile_or_email_refused(self):
        client_for(self.a).post(reverse('main:council_settings_save'),
                                {'first_name': 'x', 'last_name': 'y', 'email': 'nope', 'mobile_number': '123'})
        self.a.refresh_from_db()
        self.assertEqual(self.a.first_name, '')

    def test_settings_password_change(self):
        c = client_for(self.a)
        c.post(reverse('main:council_settings_save'),
               {'first_name': 'علی', 'last_name': 'ر', 'new_password1': 'Str0ng-pass-99', 'new_password2': 'Str0ng-pass-99'})
        self.a.refresh_from_db()
        self.assertTrue(self.a.check_password('Str0ng-pass-99'))
        c.post(reverse('main:council_settings_save'),
               {'first_name': 'علی', 'last_name': 'ر', 'new_password1': 'Another-pass-1', 'new_password2': 'different'})
        self.a.refresh_from_db()
        self.assertTrue(self.a.check_password('Str0ng-pass-99'))

    def test_old_urls_land_on_tab(self):
        r = client_for(self.a).get(reverse('main:council_voting_list'))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.url.endswith('?tab=voting') or '?tab=voting' in r.url)

    def test_dashboard_has_no_fake_data(self):
        page = client_for(self.a).get(reverse('main:council_dashboard'))
        for fake in ('احمد رضایی', 'rasooli@example.com', 'C-045', 'جناب آقای رسولی'):
            self.assertNotContains(page, fake)


class VillageScope(TestCase):
    """Council sees and acts only on requests/payments of citizens in its own village."""

    def setUp(self):
        from main.tests.helpers import make_request, make_payment
        self.a = member()
        mine = make_user('citizen', city_village=V)
        other = make_user('citizen', city_village='روستای ب')
        self.mine = make_request(mine, status='pending')
        ServiceRequest.objects.filter(id=self.mine.id).update(title='درخواست-خودی')
        self.theirs = make_request(other, status='pending')
        ServiceRequest.objects.filter(id=self.theirs.id).update(title='درخواست-غریبه')
        self.pay_mine = make_payment(mine)
        self.pay_theirs = make_payment(other)

    def test_cannot_vote_on_other_village_request(self):
        client_for(self.a).post(reverse('main:council_submit_vote', args=[self.theirs.id]), {'vote': 'approve'})
        self.assertFalse(self.theirs.votes.exists())
        client_for(self.a).post(reverse('main:council_submit_vote', args=[self.mine.id]), {'vote': 'approve'})
        self.assertTrue(self.mine.votes.exists())

    def test_cannot_view_or_comment_other_village_request(self):
        c = client_for(self.a)
        self.assertEqual(c.get(reverse('main:council_request_detail', args=[self.theirs.id])).status_code, 404)
        c.post(reverse('main:council_add_comment', args=[self.theirs.id]), {'comment': 'x'})
        self.assertFalse(self.theirs.council_comments.exists())
        self.assertEqual(c.get(reverse('main:council_request_detail', args=[self.mine.id])).status_code, 200)

    def test_user_without_village_sees_nothing(self):
        nowhere = make_user('council')
        page = client_for(nowhere).get(reverse('main:council_dashboard'))
        self.assertNotContains(page, 'درخواست-خودی')
        self.assertNotContains(page, 'درخواست-غریبه')

    def test_dashboard_lists_only_own_village(self):
        page = client_for(self.a).get(reverse('main:council_dashboard'))
        self.assertContains(page, 'درخواست-خودی')
        self.assertNotContains(page, 'درخواست-غریبه')


class RealTabs(TestCase):
    def test_financial_deeds_and_history_show_database_rows_only(self):
        from main.tests.helpers import make_request, make_payment
        a = member()
        citizen = make_user('citizen', city_village=V)
        deed = make_request(citizen, status='pending')
        ServiceRequest.objects.filter(id=deed.id).update(title='گواهی-نمونه-۱', request_type='property_deed')
        pay = make_payment(citizen)
        poll = make_poll(a, title='مصوبه-بسته')
        client_for(a).post(reverse('main:council_poll_vote', args=[poll.id]), {'choice': 'approve'})
        client_for(a).post(reverse('main:council_poll_close', args=[poll.id]))
        page = client_for(a).get(reverse('main:council_dashboard'))
        for text in ('گواهی-نمونه-۱', 'مصوبه-بسته', 'تصویب شد'):
            self.assertContains(page, text)
        for fake in ('سارا حسینی', '۱۴۰۳-۰۲', 'روستای فشم', '۲۴۵ میلیون', 'آیین‌نامه شهرسازی جدید'):
            self.assertNotContains(page, fake)

    def test_old_financial_and_review_urls_redirect_to_tabs(self):
        c = client_for(member())
        self.assertIn('tab=financial', c.get(reverse('main:council_financial_reports')).url)
        self.assertIn('tab=voting', c.get(reverse('main:council_review_requests')).url)
