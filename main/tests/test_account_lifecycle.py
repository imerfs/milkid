"""Deleting accounts keeps their records; dehyari replacement; admin oversight of letters and chats."""
import json
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from main.forms import ENABLED_MUNICIPALITY_TYPES, MunicipalityRegistrationForm
from main.models import (CityVillage, County, District, Conversation, Message, Municipality, Payment, Province,
                         UserProfile)
from main.models_office import Letter, LetterRecipient
from main.tests.helpers import client_for, make_municipality, make_payment, make_user


class SoftDelete(TestCase):
    def setUp(self):
        self.admin = make_user('admin')
        self.citizen = make_user('citizen')
        self.payment = make_payment(self.citizen)

    def delete_via_api(self, user):
        return client_for(self.admin).post(reverse('main:api_admin_delete_user', args=[user.id]))

    def test_deleting_a_citizen_keeps_their_records(self):
        self.assertEqual(self.delete_via_api(self.citizen).status_code, 200)
        self.assertTrue(User.objects.filter(id=self.citizen.id).exists())
        self.assertTrue(Payment.objects.filter(id=self.payment.id).exists())

    def test_deleted_account_cannot_log_in_and_is_hidden(self):
        self.delete_via_api(self.citizen)
        user = User.objects.get(id=self.citizen.id)
        self.assertFalse(user.is_active)
        self.assertFalse(user.has_usable_password())
        self.assertIsNotNone(user.profile.deleted_at)
        html = client_for(self.admin).get(reverse('main:manage_users')).content.decode()
        self.assertNotIn(self.citizen.username, html.split('deleted-users-table')[0])

    def test_the_users_page_delete_button_also_keeps_records(self):
        client_for(self.admin).post(reverse('main:manage_users'),
                                    {'user_id': self.citizen.profile.id, 'action': 'delete'})
        self.assertTrue(User.objects.filter(id=self.citizen.id).exists())
        self.assertTrue(Payment.objects.filter(id=self.payment.id).exists())

    def test_deleted_values_are_released_and_listed_in_the_deleted_tab(self):
        old = self.citizen
        old.profile.national_id = '0012345678'
        old.profile.save()
        username = old.username
        self.delete_via_api(old)
        again = User.objects.create_user(username=username, password='x-pass-12345')
        profile = UserProfile.objects.get(user=again)
        profile.national_id = '0012345678'
        profile.save()
        html = client_for(self.admin).get(reverse('main:manage_users')).content.decode()
        self.assertIn('deleted-users-table', html)
        self.assertIn('0012345678', html.split('deleted-users-table')[1])
        self.assertFalse(self.client.login(username=f'deleted-{old.id}', password='x-pass-12345'))

    def test_admin_cannot_delete_themselves(self):
        self.assertEqual(self.delete_via_api(self.admin).status_code, 400)


class DehyariRules(TestCase):
    def setUp(self):
        self.admin = make_user('admin')
        self.place = dict(province='خراسان جنوبی', county='بیرجند', city_village='روستای نمونه')

    def change_role(self, profile, role):
        return client_for(self.admin).post(reverse('main:api_admin_user_change_role', args=[profile.id]),
                                           data=json.dumps({'role': role}), content_type='application/json')

    def test_approving_a_dehyari_no_longer_deletes_pending_municipalities(self):
        pending = make_municipality(None)
        pending.status = 'pending'
        pending.manager_name = 'نام'
        pending.save()
        applicant = make_user('dehyari', approval_status='pending', **self.place)
        applicant.first_name = 'نام'
        applicant.save()
        response = client_for(self.admin).post(reverse('main:manage_users'),
                                               {'user_id': applicant.profile.id, 'action': 'approve'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Municipality.objects.filter(id=pending.id).exists())

    def test_making_someone_dehyari_replaces_the_places_current_one_and_links_the_municipality(self):
        old = make_user('dehyari', **self.place)
        town = make_municipality(old)
        town.status = 'active'
        town.save()
        new = make_user('citizen', **self.place)
        self.assertEqual(self.change_role(new.profile, 'dehyari').status_code, 200)
        old.profile.refresh_from_db()
        town.refresh_from_db()
        self.assertEqual(old.profile.role, 'citizen')
        self.assertEqual(town.admin_user, new)

    def test_another_place_is_untouched(self):
        elsewhere = make_user('dehyari', province='خراسان جنوبی', county='بیرجند', city_village='جای دیگر')
        self.change_role(make_user('citizen', **self.place).profile, 'dehyari')
        elsewhere.profile.refresh_from_db()
        self.assertEqual(elsewhere.profile.role, 'dehyari')


class RegistrationTypes(TestCase):
    def test_only_dehyari_and_shahrdari_can_be_registered_for_now(self):
        offered = {value for value, _ in MunicipalityRegistrationForm().fields['municipality_type'].choices}
        self.assertEqual(offered, set(ENABLED_MUNICIPALITY_TYPES))
        self.assertEqual(offered, {'dehyari', 'shahrdari'})

    def test_a_disabled_type_is_rejected(self):
        form = MunicipalityRegistrationForm(data={'municipality_type': 'farmandari'})
        form.is_valid()
        self.assertIn('municipality_type', form.errors)


class Monitoring(TestCase):
    def setUp(self):
        self.admin = make_user('admin')
        self.a, self.b = make_user('citizen'), make_user('dehyari')
        self.letter = Letter.objects.create(
            sender=self.a, village='روستای نمونه', subject='موضوع محرمانه', body='متن نامه‌ی آزمایشی',
            confidential=True, status='sent', year=1405, sequence=1, sent_at=timezone.now())
        LetterRecipient.objects.create(letter=self.letter, user=self.b)
        self.chat = Conversation.objects.create(subject='گفتگوی آزمایشی')
        self.chat.participants.add(self.a, self.b)
        Message.objects.create(conversation=self.chat, sender=self.a, body='سلام دهیار')

    def test_admin_sees_letters_including_confidential_ones(self):
        html = client_for(self.admin).get(reverse('main:admin_monitoring')).content.decode()
        self.assertIn('موضوع محرمانه', html)
        self.assertIn(self.a.username, html)
        html = client_for(self.admin).get(reverse('main:admin_monitoring_letter', args=[self.letter.id])).content.decode()
        self.assertIn('متن نامه‌ی آزمایشی', html)

    def test_admin_sees_chats_and_their_messages(self):
        html = client_for(self.admin).get(reverse('main:admin_monitoring') + '?tab=chats').content.decode()
        self.assertIn('گفتگوی آزمایشی', html)
        html = client_for(self.admin).get(reverse('main:admin_monitoring_chat', args=[self.chat.id])).content.decode()
        self.assertIn('سلام دهیار', html)

    def test_search_filters(self):
        html = client_for(self.admin).get(reverse('main:admin_monitoring') + '?q=چیزی-که-نیست').content.decode()
        self.assertNotIn('موضوع محرمانه', html)

    def test_chat_search_keeps_the_real_message_count(self):
        Message.objects.create(conversation=self.chat, sender=self.b, body='جواب')
        html = client_for(self.admin).get(reverse('main:admin_monitoring') + '?tab=chats&q=سلام').content.decode()
        self.assertIn('گفتگوی آزمایشی', html)
        self.assertRegex(html, r'<td>2</td>')

    def test_drafts_are_not_listed(self):
        Letter.objects.create(sender=self.a, village='x', subject='پیش‌نویس مخفی', body='b', status='draft')
        html = client_for(self.admin).get(reverse('main:admin_monitoring')).content.decode()
        self.assertNotIn('پیش‌نویس مخفی', html)

    def test_only_admins_may_look(self):
        for user in (self.a, self.b):
            for url in (reverse('main:admin_monitoring'),
                        reverse('main:admin_monitoring_letter', args=[self.letter.id]),
                        reverse('main:admin_monitoring_chat', args=[self.chat.id])):
                self.assertEqual(client_for(user).get(url).status_code, 302, url)
        self.assertEqual(self.client.get(reverse('main:admin_monitoring')).status_code, 302)
