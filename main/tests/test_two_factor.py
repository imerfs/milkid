"""Two-step login: TOTP maths, the session gate, setup/disable, and admin-only setup."""
import time

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from main import twofactor
from main.models import TwoFactorDevice
from main.tests.helpers import client_for, make_user


def current_code(secret):
    return twofactor.code_at(secret, int(time.time() // twofactor.STEP))


class Totp(SimpleTestCase):
    def test_rfc6238_vector(self):
        # RFC 6238 appendix B, SHA1, T=59s -> 94287082 (last 6 digits: 287082)
        secret = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'   # base32 of "12345678901234567890"
        self.assertEqual(twofactor.code_at(secret, 59 // 30), '287082')

    def test_drift_window_replay_and_garbage(self):
        secret = twofactor.new_secret()
        now = 1_800_000_000
        step = now // 30
        self.assertEqual(twofactor.matching_step(secret, twofactor.code_at(secret, step - 1), now=now), step - 1)
        self.assertIsNone(twofactor.matching_step(secret, twofactor.code_at(secret, step - 3), now=now))
        self.assertIsNone(twofactor.matching_step(secret, twofactor.code_at(secret, step), now=now, last_step=step))
        for junk in ('', 'abcdef', '12345', None):
            self.assertIsNone(twofactor.matching_step(secret, junk, now=now))


class SessionGate(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = make_user('admin')
        self.device = TwoFactorDevice.objects.create(user=self.admin, secret=twofactor.new_secret(), confirmed=True)

    def test_logged_in_user_with_2fa_is_held_on_verify_until_a_valid_code(self):
        client = client_for(self.admin)
        response = client.get(reverse('main:admin_server'))
        self.assertRedirects(response, reverse('main:two_factor_verify'), fetch_redirect_response=False)
        client.post(reverse('main:two_factor_verify'), {'code': '000000' if current_code(self.device.secret) != '000000' else '111111'})
        self.assertEqual(client.get(reverse('main:admin_server')).status_code, 302)
        client.post(reverse('main:two_factor_verify'), {'code': current_code(self.device.secret)})
        self.assertEqual(client.get(reverse('main:admin_server')).status_code, 200)

    def test_same_code_cannot_open_a_second_session(self):
        code = current_code(self.device.secret)
        client_for(self.admin).post(reverse('main:two_factor_verify'), {'code': code})
        other = client_for(self.admin)
        other.post(reverse('main:two_factor_verify'), {'code': code})
        self.assertEqual(other.get(reverse('main:admin_server')).status_code, 302)

    def test_users_without_2fa_are_not_affected(self):
        self.assertEqual(client_for(make_user('admin')).get(reverse('main:admin_server')).status_code, 200)

    def test_verify_does_not_redirect_offsite(self):
        response = client_for(self.admin).post(reverse('main:two_factor_verify'),
                                               {'code': current_code(self.device.secret), 'next': 'https://evil.example/'})
        self.assertEqual(response['Location'], reverse('main:dashboard'))


class Setup(TestCase):
    def test_enable_then_disable_with_codes(self):
        admin = make_user('admin')
        client = client_for(admin)
        client.post(reverse('main:admin_two_factor_start'))
        device = TwoFactorDevice.objects.get(user=admin)
        self.assertFalse(device.confirmed)
        self.assertContains(client.get(reverse('main:admin_server'), {'tab': 'security'}), 'otpauth://totp/')
        client.post(reverse('main:admin_two_factor_confirm'), {'code': current_code(device.secret)})
        device.refresh_from_db()
        self.assertTrue(device.confirmed)
        self.assertEqual(client.get(reverse('main:admin_server')).status_code, 200)   # this session already passed
        device.last_step = None   # allow reusing the current step in the test
        device.save()
        client.post(reverse('main:admin_two_factor_disable'), {'code': current_code(device.secret)})
        self.assertFalse(TwoFactorDevice.objects.filter(user=admin).exists())

    def test_wrong_code_does_not_enable(self):
        admin = make_user('admin')
        client = client_for(admin)
        client.post(reverse('main:admin_two_factor_start'))
        client.post(reverse('main:admin_two_factor_confirm'), {'code': 'xxxxxx'})
        self.assertFalse(TwoFactorDevice.objects.get(user=admin).confirmed)

    def test_setup_is_admin_only(self):
        for role in ('citizen', 'dehyari', 'accountant'):
            client = client_for(make_user(role))
            for name in ('admin_two_factor_start', 'admin_two_factor_confirm', 'admin_two_factor_disable'):
                with self.subTest(role=role, endpoint=name):
                    self.assertIn(client.post(reverse(f'main:{name}')).status_code, (302, 403))
        self.assertFalse(TwoFactorDevice.objects.exists())
