"""The messenger: one inbox for chats and letters, who may write to whom, and who is shown as the sender."""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from main.models import Message, MessageRecipient, Municipality, UserProfile
from main.office import directory, letters, messenger
from main.tests.helpers import client_for, make_municipality, make_user

A, B = 'روستای الف', 'بخش ب'


def fresh(user):
    return User.objects.get(pk=user.pk)


def person(role, first='', last='', **profile):
    user = make_user(role, **profile)
    User.objects.filter(pk=user.pk).update(first_name=first, last_name=last)
    return user


class World(TestCase):
    def setUp(self):
        self.mayor = person('dehyari', 'رضا', 'احمدی', city_village=A)
        self.org_a = make_municipality(self.mayor, A)
        self.bakhshdar = person('dehyari', 'سعید', 'کریمی', city_village=B)
        self.org_b = make_municipality(self.bakhshdar, B)
        Municipality.objects.filter(pk=self.org_b.pk).update(municipality_type='bakhshdari', name='بخشداری مرکزی')
        Municipality.objects.filter(pk__in=[self.org_a.pk, self.org_b.pk]).update(status='active')
        self.clerk = person('clerk', 'سارا', 'رضایی', city_village=A)
        self.citizen = person('citizen', 'علی', 'محمدی', city_village=A)
        self.other_citizen = make_user('citizen', city_village=A)
        self.mayor, self.bakhshdar, self.clerk, self.citizen, self.other_citizen = (
            fresh(u) for u in (self.mayor, self.bakhshdar, self.clerk, self.citizen, self.other_citizen))

    def chat(self, sender, to, body='سلام'):
        return client_for(sender).post(reverse('main:messenger_new'), {'kind': 'chat', 'to': [to.id], 'body': body})

    def letter(self, sender, to, subject='موضوع', body='متن نامه'):
        return client_for(sender).post(reverse('main:messenger_new'), {
            'kind': 'letter', 'to': [u.id for u in to], 'subject': subject, 'body': body, 'priority': 'normal'})


class Identity(World):
    def test_manager_of_an_organization_is_shown_with_its_title(self):
        who = directory.identity(self.bakhshdar)
        self.assertEqual((who.title, who.org), ('بخشدار', 'بخشداری مرکزی'))
        self.assertEqual(directory.identity(self.mayor).title, 'دهیار')

    def test_staff_and_citizens_carry_their_role_and_village_organization(self):
        self.assertEqual(directory.identity(self.clerk).line, f'کارشناس اداری · {self.org_a.name}')
        self.assertEqual(directory.identity(self.citizen).title, 'شهروند')


class WhoMayWriteToWhom(World):
    def test_staff_write_across_organizations_both_ways(self):
        self.assertEqual(self.chat(self.mayor, self.bakhshdar).status_code, 200)
        self.assertEqual(self.chat(self.bakhshdar, self.mayor).status_code, 200)
        self.assertEqual(self.letter(self.bakhshdar, [self.mayor, self.clerk]).status_code, 200)

    def test_staff_write_to_their_own_citizens_only(self):
        self.assertEqual(self.chat(self.clerk, self.citizen).status_code, 200)
        far = fresh(make_user('citizen', city_village=B))
        self.assertEqual(self.chat(self.clerk, far).status_code, 403)

    def test_citizen_writes_to_staff_of_home_and_chosen_organization_only(self):
        self.assertEqual(self.chat(self.citizen, self.clerk).status_code, 200)
        self.assertEqual(self.chat(self.citizen, self.other_citizen).status_code, 403)
        self.assertEqual(self.chat(self.citizen, self.bakhshdar).status_code, 403)
        UserProfile.objects.filter(user=self.citizen).update(active_municipality=self.org_b)
        self.assertEqual(self.chat(fresh(self.citizen), self.bakhshdar).status_code, 200)

    def test_chat_needs_exactly_one_recipient(self):
        response = client_for(self.mayor).post(reverse('main:messenger_new'), {
            'kind': 'chat', 'to': [self.clerk.id, self.bakhshdar.id], 'body': 'x'})
        self.assertEqual(response.status_code, 400)


class Chats(World):
    def test_same_pair_shares_one_chat_and_sender_sees_who_wrote(self):
        self.chat(self.clerk, self.citizen, 'اولی')
        self.chat(self.clerk, self.citizen, 'دومی')
        threads = messenger.threads(self.citizen)
        self.assertEqual(len(threads), 1)
        self.assertEqual((threads[0].unread, threads[0].who.name), (2, 'سارا رضایی'))
        self.assertEqual(threads[0].who.title, 'کارشناس اداری')

    def test_opening_marks_read_and_only_participants_can_open(self):
        self.chat(self.clerk, self.citizen)
        key = messenger.threads(self.citizen)[0].key
        page = client_for(self.citizen).get(reverse('main:messenger_thread', args=[key]))
        self.assertContains(page, 'سارا رضایی')
        self.assertContains(page, 'کارشناس اداری')
        self.assertEqual(messenger.threads(self.citizen)[0].unread, 0)
        self.assertEqual(client_for(self.other_citizen).get(reverse('main:messenger_thread', args=[key])).status_code, 404)

    def test_replying_in_the_thread_reaches_the_other_side(self):
        self.chat(self.clerk, self.citizen)
        key = messenger.threads(self.citizen)[0].key
        client_for(self.citizen).post(reverse('main:messenger_send', args=[key]), {'body': 'ممنون'})
        self.assertEqual(Message.objects.count(), 2)
        self.assertEqual(MessageRecipient.objects.filter(recipient=self.clerk, is_read=False).count(), 1)
        self.assertEqual(messenger.threads(self.clerk)[0].unread, 1)

    def test_empty_and_oversized_messages_are_refused(self):
        self.chat(self.clerk, self.citizen)
        key = messenger.threads(self.citizen)[0].key
        for body in ('   ', 'x' * (messenger.MAX_BODY + 1)):
            r = client_for(self.citizen).post(reverse('main:messenger_send', args=[key]), {'body': body})
            self.assertEqual(r.status_code, 400)

    def test_chat_is_rate_limited(self):
        self.chat(self.clerk, self.citizen)
        chat_id = int(messenger.threads(self.clerk)[0].key[1:])
        for _ in range(messenger.CHAT_HOURLY_CAP):
            Message.objects.create(conversation_id=chat_id, sender=self.clerk, body='x')
        self.assertEqual(client_for(self.clerk).post(
            reverse('main:messenger_send', args=[f'c{chat_id}']), {'body': 'بیشتر'}).status_code, 429)


class Letters(World):
    def test_letter_appears_for_the_recipient_with_the_senders_organization(self):
        self.letter(self.bakhshdar, [self.mayor], subject='ابلاغ بخشنامه')
        row = messenger.threads(self.mayor)[0]
        self.assertEqual((row.kind, row.unread, row.subject), ('letter', 1, 'ابلاغ بخشنامه'))
        page = client_for(self.mayor).get(reverse('main:messenger_thread', args=[row.key]))
        self.assertContains(page, 'بخشداری مرکزی')
        self.assertContains(page, 'بخشدار')
        self.assertEqual(messenger.threads(self.mayor)[0].unread, 0)

    def test_reply_joins_the_same_thread(self):
        self.letter(self.bakhshdar, [self.mayor])
        key = messenger.threads(self.mayor)[0].key
        client_for(self.mayor).post(reverse('main:messenger_send', args=[key]), {'body': 'دریافت شد'})
        self.assertEqual(len(messenger.threads(self.mayor)), 1)
        self.assertEqual(len(messenger.threads(self.bakhshdar)), 1)
        self.assertEqual(messenger.threads(self.bakhshdar)[0].unread, 1)
        page = client_for(self.bakhshdar).get(reverse('main:messenger_thread', args=[key]))
        self.assertContains(page, 'دریافت شد')

    def test_a_stranger_cannot_open_a_letter_thread(self):
        self.letter(self.bakhshdar, [self.mayor])
        key = messenger.threads(self.mayor)[0].key
        self.assertEqual(client_for(self.clerk).get(reverse('main:messenger_thread', args=[key])).status_code, 404)

    def test_letter_needs_a_subject_and_a_body(self):
        self.assertEqual(self.letter(self.mayor, [self.clerk], subject='').status_code, 400)


class TheInbox(World):
    def test_filters_by_kind_search_and_unread(self):
        self.chat(self.clerk, self.citizen, 'پیام کوتاه')
        self.letter(self.mayor, [self.citizen], subject='گواهی سکونت')
        self.assertEqual({t.kind for t in messenger.threads(self.citizen)}, {'chat', 'letter'})
        self.assertEqual([t.kind for t in messenger.threads(self.citizen, 'letter')], ['letter'])
        self.assertEqual([t.kind for t in messenger.threads(self.citizen, q='گواهی')], ['letter'])
        self.assertEqual(len(messenger.threads(self.citizen, unread=True)), 2)

    def test_signature_changes_when_something_arrives(self):
        before = messenger.signature(self.citizen)
        self.chat(self.clerk, self.citizen)
        self.assertNotEqual(messenger.signature(self.citizen), before)
        data = client_for(self.citizen).get(reverse('main:messenger_poll')).json()
        self.assertEqual(data['unread'], 1)

    def test_pages_need_a_login(self):
        for name in ('messenger', 'messenger_list', 'messenger_poll', 'messenger_directory'):
            response = client_for().get(reverse(f'main:{name}'))
            self.assertEqual(response.status_code, 302, name)

    def test_page_renders_embedded_and_standalone(self):
        self.chat(self.clerk, self.citizen)
        for params in ({}, {'embed': '1'}, {'new': 'letter'}):
            self.assertContains(client_for(self.citizen).get(reverse('main:messenger'), params), 'id="mg"')


class Directory(World):
    def test_staff_see_organizations_then_the_people_they_may_write_to(self):
        page = client_for(self.mayor).get(reverse('main:messenger_directory'))
        self.assertContains(page, 'بخشداری مرکزی')
        people = client_for(self.mayor).get(reverse('main:messenger_directory'), {'org': self.org_b.pk})
        self.assertContains(people, 'سعید کریمی')

    def test_citizen_sees_no_people_in_an_organization_they_have_not_chosen(self):
        people = client_for(self.citizen).get(reverse('main:messenger_directory'), {'org': self.org_b.pk})
        self.assertNotContains(people, 'سعید کریمی')


class SwitchingOrganization(World):
    def test_citizen_switches_and_goes_back(self):
        c = client_for(self.citizen)
        c.post(reverse('main:switch_municipality'), {'org': self.org_b.pk})
        self.assertEqual(UserProfile.objects.get(user=self.citizen).active_municipality, self.org_b)
        self.assertEqual(directory.effective_org(fresh(self.citizen)), self.org_b)
        c.post(reverse('main:switch_municipality'), {'org': ''})
        self.assertIsNone(UserProfile.objects.get(user=self.citizen).active_municipality)

    def test_unknown_or_inactive_organization_is_refused(self):
        Municipality.objects.filter(pk=self.org_b.pk).update(status='pending')
        client_for(self.citizen).post(reverse('main:switch_municipality'), {'org': self.org_b.pk})
        self.assertIsNone(UserProfile.objects.get(user=self.citizen).active_municipality)

    def test_staff_do_not_use_the_switcher(self):
        response = client_for(self.clerk).post(reverse('main:switch_municipality'), {'org': self.org_b.pk})
        self.assertRedirects(response, reverse('main:dashboard'), fetch_redirect_response=False)
        self.assertIsNone(UserProfile.objects.get(user=self.clerk).active_municipality)

    def test_open_redirect_target_is_ignored(self):
        response = client_for(self.citizen).post(reverse('main:switch_municipality'), {'org': self.org_b.pk, 'next': '//evil.test'})
        self.assertEqual(response.url, reverse('main:my_municipality'))


class RequestsFollowTheChosenOrganization(World):
    def file(self, user, title):
        from main import lifecycle
        from main.models import ServiceRequest
        return lifecycle.submit(user, action='ثبت', instance=ServiceRequest(request_type='other', title=title, description='d'))

    def test_request_goes_to_the_organization_the_citizen_switched_to(self):
        from main.models import ServiceRequest
        home = self.file(self.citizen, 'در دهیاری خودم')
        UserProfile.objects.filter(user=self.citizen).update(active_municipality=self.org_b)
        away = self.file(fresh(self.citizen), 'در بخشداری')
        self.assertIsNone(home.target_municipality)
        self.assertEqual(away.target_municipality, self.org_b)
        in_a = set(ServiceRequest.objects.filter(directory.requests_for(A)).values_list('title', flat=True))
        in_b = set(ServiceRequest.objects.filter(directory.requests_for(B)).values_list('title', flat=True))
        self.assertEqual((in_a, in_b), ({'در دهیاری خودم'}, {'در بخشداری'}))

    def test_clerk_of_the_target_sees_it_in_the_follow_up_list(self):
        from main.models import ServiceRequest
        UserProfile.objects.filter(user=self.citizen).update(active_municipality=self.org_b)
        away = self.file(fresh(self.citizen), 'نیاز به مدارک')
        ServiceRequest.objects.filter(pk=away.pk).update(status='requires_documents')
        clerk_b = fresh(person('clerk', 'م', 'ک', city_village=B))
        from main.office import desk
        self.assertEqual([sr.pk for sr in desk.follow_ups(clerk_b)], [away.pk])
        self.assertEqual(list(desk.follow_ups(self.clerk)), [])

    def test_create_request_page_names_the_target(self):
        UserProfile.objects.filter(user=self.citizen).update(active_municipality=self.org_b)
        page = client_for(self.citizen).get(reverse('main:create_request'), {'embed': '1'})
        self.assertContains(page, 'بخشداری مرکزی')
