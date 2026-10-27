"""The public pages tell the truth: no invented address, figures or people, a contact form that really delivers, links that go somewhere."""
import re

from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from main.models import MailMessage

NOT_THERE = ('تهران، میدان آزادی', 'تهران، خیابان ولیعصر', 'سمندآباد', 'municipality.ir', 'behrangaar', 'کد پستی: 1234567890', 'رضا کریمی', 'مریم احمدی')


class NothingInvented(TestCase):
    def test_no_made_up_address_email_or_person_on_the_public_pages(self):
        for name in ('main:home', 'main:contact', 'main:about'):
            html = self.client.get(reverse(name)).content.decode()
            for text in NOT_THERE:
                self.assertNotIn(text, html, (name, text))

    def test_the_home_page_has_no_invented_percentages_or_dead_links(self):
        html = self.client.get(reverse('main:home')).content.decode()
        for text in ('85%', '99%', 'تضمین اصالت اسناد', 'پایش امنیتی مستمر', 'نظرات کاربران'):
            self.assertNotIn(text, html)
        self.assertNotIn('href="#"', html)
        self.assertNotIn('نسخه نمایشی', html)

    def test_the_footer_has_no_dead_social_links_or_fake_hours(self):
        html = self.client.get(reverse('main:contact')).content.decode()
        self.assertNotIn('href="#"', html)
        self.assertNotIn('۸:۰۰ تا ۱۶:۰۰', html)

    def test_the_about_page_makes_no_support_promise_it_cannot_keep(self):
        html = self.client.get(reverse('main:about')).content.decode()
        self.assertNotIn('۲۴ ساعته</p>', html.replace('دسترسی ۲۴ ساعته', ''))
        self.assertNotIn('نسخه سیستم', html)

    def test_every_internal_link_and_anchor_of_the_home_page_works(self):
        html = self.client.get(reverse('main:home')).content.decode()
        for link in set(re.findall(r'href="(/[^"#]*)"', html)):
            if link.startswith(('/static/', '/media/')):
                continue
            self.assertIn(self.client.get(link).status_code, (200, 302), link)
        for anchor in set(re.findall(r'href="#([\w-]+)"', html)):
            self.assertIn(f'id="{anchor}"', html, anchor)


class ContactForm(TestCase):
    def setUp(self):
        cache.clear()                       # the contact page is throttled per IP and tests share the cache

    def post(self, **change):
        data = {'name': 'علی رضایی', 'email': 'ali@example.test', 'phone': '', 'subject': 'services', 'message': 'چطور پروانه بگیرم؟', 'website': ''}
        data.update(change)
        return self.client.post(reverse('main:contact'), data)

    def test_the_message_reaches_the_admin_mailbox(self):
        response = self.post()
        self.assertRedirects(response, reverse('main:contact'))
        item = MailMessage.objects.get()
        self.assertEqual((item.folder, item.source), ('inbox', 'support'))
        self.assertIn('علی رضایی', item.body)
        self.assertIn('چطور پروانه بگیرم؟', item.body)
        self.assertIn('ali@example.test', item.sender)

    @override_settings(SITE_EMAIL='office@example.test')
    def test_and_to_the_site_address_when_one_is_set(self):
        self.post()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['office@example.test'])

    def test_a_mobile_number_is_enough(self):
        self.post(email='', phone='۰۹۱۲۳۴۵۶۷۸۹')
        self.assertIn('09123456789', MailMessage.objects.get().body)

    def test_a_way_to_answer_is_required(self):
        self.post(email='', phone='')
        self.assertFalse(MailMessage.objects.exists())
        self.post(email='', phone='12345')
        self.assertFalse(MailMessage.objects.exists())

    def test_short_or_missing_things_are_refused(self):
        for change in (dict(name=''), dict(message='سلام'), dict(subject='nonsense'), dict(email='not-an-email')):
            self.post(**change)
        self.assertFalse(MailMessage.objects.exists())

    def test_bots_filling_the_hidden_field_deliver_nothing(self):
        self.post(website='http://spam.example')
        self.assertFalse(MailMessage.objects.exists())

    def test_the_page_shows_the_phone_and_the_email_of_the_settings_only(self):
        with override_settings(SUPPORT_PHONE='', SUPPORT_EMAIL=''):
            html = self.client.get(reverse('main:contact')).content.decode()
        self.assertNotIn('tel:', html)
        self.assertNotIn('mailto:', html)
        with override_settings(SUPPORT_PHONE='09120000000', SUPPORT_EMAIL='help@example.test'):
            html = self.client.get(reverse('main:contact')).content.decode()
        self.assertIn('tel:09120000000', html)
        self.assertIn('mailto:help@example.test', html)
