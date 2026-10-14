"""Email login codes, SMS gateway settings, the support form and the admin mailbox."""
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from main import logincode, mailbox, sms
from main.models import LoginCode, MailMessage, SmsConfig, TwoFactorDevice
from main.tests.helpers import client_for, make_user


def user_with_email(role='citizen', email='ali@example.com'):
    user = make_user(role)
    user.email = email
    user.save()
    return user


def sent_code():
    return mail.outbox[-1].body.split('کد ورود شما: ')[1][:6]


class EmailLoginCode(TestCase):
    def setUp(self):
        cache.clear()
        self.user = user_with_email()
        self.client = Client()

    def request_code(self, email='ali@example.com'):
        return self.client.post(reverse('main:login_code_request'), {'email': email})

    def verify(self, code):
        return self.client.post(reverse('main:login_code_verify'), {'code': code})

    def test_correct_code_logs_in_once(self):
        self.request_code()
        code = sent_code()
        self.assertRedirects(self.verify(code), reverse('main:dashboard'), fetch_redirect_response=False)
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.id)
        other = Client()
        other.session['login_code_email'] = 'ali@example.com'
        other.post(reverse('main:login_code_request'), {'email': 'ali@example.com'})   # no new mail inside the cooldown
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn('_auth_user_id', other.post(reverse('main:login_code_verify'), {'code': code}).wsgi_request.session)

    def test_unknown_email_looks_the_same_and_sends_nothing(self):
        response = self.request_code('nobody@example.com')
        self.assertRedirects(response, reverse('main:login_code_verify'), fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 0)

    def test_inactive_and_shared_emails_get_no_code(self):
        self.user.is_active = False
        self.user.save()
        self.request_code()
        self.user.is_active = True
        self.user.save()
        user_with_email(email='ALI@example.com')       # two accounts share the address
        self.request_code()
        self.assertEqual(len(mail.outbox), 0)

    def test_wrong_code_and_attempt_limit(self):
        self.request_code()
        code = sent_code()
        for _ in range(logincode.MAX_ATTEMPTS):
            self.verify('000000' if code != '000000' else '111111')
        self.verify(code)                                   # right code, but the entry is burnt
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_expired_code_is_refused(self):
        self.request_code()
        LoginCode.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.verify(sent_code())
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_new_code_replaces_the_old_one(self):
        self.request_code()
        first = sent_code()
        LoginCode.objects.update(created_at=timezone.now() - timedelta(minutes=2))
        self.request_code()
        second = sent_code()
        self.verify(first if first != second else '999999')
        self.assertNotIn('_auth_user_id', self.client.session)
        self.verify(second)
        self.assertIn('_auth_user_id', self.client.session)

    def test_code_is_stored_hashed(self):
        self.request_code()
        self.assertNotIn(sent_code(), LoginCode.objects.get().code_hash)

    def test_admin_with_two_factor_still_needs_the_second_step(self):
        admin = user_with_email('admin', 'boss@example.com')
        TwoFactorDevice.objects.create(user=admin, secret='JBSWY3DPEHPK3PXP', confirmed=True)
        self.request_code('boss@example.com')
        self.verify(sent_code())
        response = self.client.get(reverse('main:admin_dashboard'))
        self.assertRedirects(response, reverse('main:two_factor_verify'), fetch_redirect_response=False)

    def test_verify_page_needs_a_requested_email(self):
        self.assertRedirects(self.client.get(reverse('main:login_code_verify')), reverse('main:login_code_request'),
                             fetch_redirect_response=False)

    def test_pages_render(self):
        self.assertContains(self.client.get(reverse('main:login_code_request')), 'ارسال کد')
        self.assertContains(self.client.get(reverse('main:login')), reverse('main:login_code_request'))


class SmsSettings(TestCase):
    def setUp(self):
        self.admin = client_for(make_user('admin'))

    def save(self, **extra):
        data = {'base_url': 'https://93.184.216.34/send', 'api_key': 'SECRET-KEY-123', 'sender': '3000123',
                'auth_header': 'Authorization', 'auth_prefix': 'Bearer ', 'to_field': 'to', 'text_field': 'message',
                'sender_field': 'from', 'enabled': '1', **extra}
        return self.admin.post(reverse('main:admin_sms_save'), data)

    def test_key_is_encrypted_and_never_shown(self):
        self.save()
        config = SmsConfig.objects.get()
        self.assertNotIn('SECRET-KEY-123', config.api_key_enc)
        self.assertEqual(sms.api_key(config), 'SECRET-KEY-123')
        self.assertNotContains(self.admin.get(reverse('main:admin_server'), {'tab': 'sms'}), 'SECRET-KEY-123')

    def test_blank_key_keeps_the_stored_one(self):
        self.save()
        self.save(api_key='')
        self.assertEqual(sms.api_key(SmsConfig.objects.get()), 'SECRET-KEY-123')

    def test_rejects_plain_http_and_internal_addresses(self):
        for url in ('http://93.184.216.34/send', 'https://127.0.0.1/send', 'https://10.0.0.5/x', 'https://169.254.169.254/'):
            self.save(base_url=url)
        self.assertFalse(SmsConfig.objects.exists())

    def test_rejects_header_injection_in_field_names(self):
        self.save(auth_header='X-Key\r\nEvil: 1')
        self.assertFalse(SmsConfig.objects.exists())

    def test_only_admins_reach_the_settings(self):
        for role in ('citizen', 'dehyari', 'accountant'):
            client = client_for(make_user(role))
            for name in ('admin_sms_save', 'admin_sms_test'):
                self.assertIn(client.post(reverse(f'main:{name}'), {'base_url': 'https://93.184.216.34/'}).status_code, (302, 403))
        self.assertFalse(SmsConfig.objects.exists())


class SmsSending(TestCase):
    def setUp(self):
        self.admin = client_for(make_user('admin'))
        self.admin.post(reverse('main:admin_sms_save'), {
            'base_url': 'https://93.184.216.34/send', 'api_key': 'KEY', 'sender': '3000', 'auth_header': 'X-Api-Key',
            'auth_prefix': '', 'to_field': 'mobile', 'text_field': 'text', 'sender_field': 'line', 'enabled': '1'})

    def test_posts_with_configured_fields_and_normalised_number(self):
        with mock.patch('main.sms._post', return_value=200) as post:
            ok, _ = sms.send_sms('۰۹۱۲۳۴۵۶۷۸۹', 'سلام')
        self.assertTrue(ok)
        url, headers, payload = post.call_args.args
        self.assertEqual(url, 'https://93.184.216.34/send')
        self.assertEqual(headers['X-Api-Key'], 'KEY')
        self.assertEqual(payload, {'mobile': '09123456789', 'text': 'سلام', 'line': '3000'})

    def test_bad_number_empty_text_and_gateway_errors_are_reported_not_raised(self):
        with mock.patch('main.sms._post', side_effect=OSError('down')):
            self.assertFalse(sms.send_sms('09123456789', 'x')[0])
        with mock.patch('main.sms._post', return_value=500):
            self.assertFalse(sms.send_sms('09123456789', 'x')[0])
        with mock.patch('main.sms._post') as post:
            self.assertFalse(sms.send_sms('12345', 'x')[0])
            self.assertFalse(sms.send_sms('09123456789', '  ')[0])
            self.assertFalse(sms.send_sms('09123456789', 'a' * 601)[0])
            post.assert_not_called()

    def test_disabled_gateway_sends_nothing(self):
        SmsConfig.objects.update(enabled=False)
        with mock.patch('main.sms._post') as post:
            self.assertFalse(sms.send_sms('09123456789', 'x')[0])
            post.assert_not_called()

    def test_test_button(self):
        with mock.patch('main.sms._post', return_value=200) as post:
            self.admin.post(reverse('main:admin_sms_test'), {'phone': '09123456789'})
        post.assert_called_once()


class SupportForm(TestCase):
    def setUp(self):
        cache.clear()

    def test_signed_in_user_message_lands_in_the_admin_inbox(self):
        user = user_with_email()
        client_for(user).post(reverse('main:support'), {'subject': 'مشکل پرداخت', 'body': 'متن پیام'})
        row = MailMessage.objects.get()
        self.assertEqual((row.folder, row.source, row.user, row.sender, row.is_read), ('inbox', 'support', user, 'ali@example.com', False))

    def test_anonymous_is_sent_to_login(self):
        response = Client().post(reverse('main:support'), {'subject': 's', 'body': 'b'})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(MailMessage.objects.exists())

    def test_validation(self):
        client = client_for(make_user())
        for data in ({'subject': '', 'body': 'x'}, {'subject': 'x', 'body': ''}, {'subject': 'x' * 201, 'body': 'b'},
                     {'subject': 's', 'body': 'b' * 20001}):
            client.post(reverse('main:support'), data)
        self.assertFalse(MailMessage.objects.exists())

    def test_flood_is_throttled(self):
        client = client_for(make_user())
        codes = [client.post(reverse('main:support'), {'subject': 's', 'body': 'b'}).status_code for _ in range(7)]
        self.assertEqual(codes[-1], 429)
        self.assertEqual(MailMessage.objects.count(), 5)

    def test_page_renders(self):
        self.assertContains(client_for(make_user()).get(reverse('main:support')), 'ارسال به پشتیبانی')


class AdminMailbox(TestCase):
    def setUp(self):
        self.admin = client_for(make_user('admin'))
        self.inbox = MailMessage.objects.create(folder='inbox', source='support', sender='ali@example.com',
                                                subject='سلام', body='<script>alert(1)</script> متن')

    def test_only_admins_see_or_change_the_mailbox(self):
        for role in ('citizen', 'dehyari', 'accountant', 'council'):
            client = client_for(make_user(role))
            self.assertIn(client.get(reverse('main:admin_mail')).status_code, (302, 403))
            for name in ('admin_mail_send', 'admin_mail_action', 'admin_mail_fetch'):
                self.assertIn(client.post(reverse(f'main:{name}'), {'to': 'a@b.ir', 'subject': 's', 'body': 'b',
                                                                   'ids': self.inbox.id, 'op': 'delete'}).status_code, (302, 403))
        self.assertEqual(Client().get(reverse('main:admin_mail')).status_code, 302)
        self.assertEqual(MailMessage.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 0)

    def test_inbox_lists_and_opening_marks_read_with_escaped_body(self):
        self.assertContains(self.admin.get(reverse('main:admin_mail')), 'سلام')
        response = self.admin.get(reverse('main:admin_mail'), {'id': self.inbox.id})
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.inbox.refresh_from_db()
        self.assertTrue(self.inbox.is_read)

    def test_compose_sends_real_mail_and_files_it_under_sent(self):
        response = self.admin.post(reverse('main:admin_mail_send'), {'to': 'a@b.ir, c@d.ir', 'subject': 'موضوع', 'body': 'متن'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(mail.outbox[0].to, ['a@b.ir', 'c@d.ir'])
        row = MailMessage.objects.get(folder='sent')
        self.assertEqual((row.failed, row.subject), (False, 'موضوع'))
        self.assertContains(self.admin.get(reverse('main:admin_mail'), {'folder': 'sent'}), 'موضوع')

    def test_send_validation_sends_nothing(self):
        for data in ({'to': 'not-an-email', 'subject': 's', 'body': 'b'}, {'to': '', 'subject': 's', 'body': 'b'},
                     {'to': 'a@b.ir', 'subject': '', 'body': 'b'}, {'to': 'a@b.ir', 'subject': 's', 'body': ''},
                     {'to': ','.join(f'u{i}@b.ir' for i in range(11)), 'subject': 's', 'body': 'b'},
                     {'to': 'a@b.ir\nbcc:evil@x.ir', 'subject': 's', 'body': 'b'}):
            self.admin.post(reverse('main:admin_mail_send'), data)
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(MailMessage.objects.filter(folder='sent').exists())

    def test_smtp_failure_is_kept_and_flagged(self):
        with mock.patch('main.mailbox.EmailMessage.send', side_effect=OSError('smtp down')):
            self.admin.post(reverse('main:admin_mail_send'), {'to': 'a@b.ir', 'subject': 's', 'body': 'b'})
        row = MailMessage.objects.get(folder='sent')
        self.assertTrue(row.failed)
        self.assertIn('smtp down', row.error)

    def test_trash_restore_and_delete_forever(self):
        act = lambda op: self.admin.post(reverse('main:admin_mail_action'), {'ids': [self.inbox.id], 'op': op, 'folder': 'inbox'})
        act('delete')                                            # not in the trash yet: refused
        self.assertTrue(MailMessage.objects.filter(id=self.inbox.id).exists())
        act('trash')
        self.inbox.refresh_from_db()
        self.assertEqual(self.inbox.folder, 'trash')
        act('restore')
        self.inbox.refresh_from_db()
        self.assertEqual(self.inbox.folder, 'inbox')
        act('trash')
        act('delete')
        self.assertFalse(MailMessage.objects.exists())

    def test_reply_prefills_the_account_email_of_a_support_sender(self):
        user = user_with_email(email='real@example.com')
        self.inbox.user = user
        self.inbox.save()
        response = self.admin.get(reverse('main:admin_mail'), {'compose': 1, 'reply': self.inbox.id})
        self.assertContains(response, 'value="real@example.com"')
        self.assertContains(response, 'Re: سلام')

    def test_search(self):
        MailMessage.objects.create(folder='inbox', sender='x@y.ir', subject='گزارش مالی', body='b')
        response = self.admin.get(reverse('main:admin_mail'), {'q': 'مالی'})
        self.assertContains(response, 'گزارش مالی')
        self.assertNotContains(response, 'ali@example.com')

    def test_bulk_ids_ignore_garbage(self):
        response = self.admin.post(reverse('main:admin_mail_action'), {'ids': ['abc', '', str(self.inbox.id)], 'op': 'read', 'folder': 'bogus'})
        self.assertEqual(response.status_code, 302)
        self.inbox.refresh_from_db()
        self.assertTrue(self.inbox.is_read)


class ImapFetch(TestCase):
    RAW = (b'From: Sara <sara@example.com>\r\nTo: info@amirl.ir\r\nSubject: =?utf-8?b?2LPZhNin2YU=?=\r\n'
           b'Message-ID: <abc@example.com>\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nhello body\r\n')

    def test_store_raw_parses_and_dedupes_by_message_id(self):
        first = mailbox.store_raw(self.RAW)
        self.assertEqual((first.sender, first.subject, first.folder, first.source), ('sara@example.com', 'سلام', 'inbox', 'imap'))
        self.assertIn('hello body', first.body)
        self.assertIsNone(mailbox.store_raw(self.RAW))
        self.assertEqual(MailMessage.objects.count(), 1)

    def test_fetch_button_without_imap_config_explains(self):
        admin = client_for(make_user('admin'))
        response = admin.post(reverse('main:admin_mail_fetch'), follow=True)
        self.assertContains(response, 'IMAP_HOST')

    @override_settings(IMAP_HOST='imap.example.com', IMAP_PORT=993, IMAP_USER='u', IMAP_PASSWORD='p')
    def test_fetch_reads_unseen_mail(self):
        box = mock.MagicMock()
        box.search.return_value = ('OK', [b'1'])
        box.fetch.return_value = ('OK', [(b'1 (BODY[] {10}', self.RAW), b')'])
        with mock.patch('main.mailbox.imaplib.IMAP4_SSL', return_value=box):
            self.assertEqual(mailbox.fetch_imap(), 1)
        self.assertEqual(MailMessage.objects.count(), 1)
        box.logout.assert_called()
