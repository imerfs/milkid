from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings


class AnonymousAccessTests(TestCase):
    def test_payment_export_requires_login(self):
        r = self.client.get('/api/payments/export-excel/')
        self.assertEqual(r.status_code, 401)

    def test_payment_export_denied_for_ordinary_user(self):
        User.objects.create_user('citizen', password='x-pass-1234')
        self.client.login(username='citizen', password='x-pass-1234')
        r = self.client.get('/api/payments/export-excel/')
        self.assertEqual(r.status_code, 403)

    def test_private_views_redirect_anonymous_instead_of_crashing(self):
        for path in ('/payments/', '/api/notifications/', '/dashboard/'):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 302, path)
            self.assertIn('/login/', r['Location'])

    def test_debug_pages_are_gone(self):
        self.assertEqual(self.client.get('/test-geographic/').status_code, 404)
        self.assertEqual(self.client.get('/test/jalali-dates/').status_code, 404)


class MediaAuthTests(TestCase):
    def test_anonymous_is_rejected(self):
        self.assertEqual(self.client.get('/_media-auth/').status_code, 401)

    def test_signed_in_user_is_accepted(self):
        User.objects.create_user('u', password='x-pass-1234')
        self.client.login(username='u', password='x-pass-1234')
        self.assertEqual(self.client.get('/_media-auth/').status_code, 204)


class LoginThrottleTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_login_brute_force_is_throttled(self):
        codes = [self.client.post('/login/', {'username': 'a', 'password': 'b'},
                                  HTTP_X_REAL_IP='203.0.113.9').status_code for _ in range(12)]
        self.assertEqual(codes[-1], 429)
        self.assertNotIn(429, codes[:10])

    def test_spoofed_forwarded_for_does_not_bypass_limit(self):
        last = None
        for i in range(12):
            last = self.client.post('/login/', {'username': 'a', 'password': 'b'},
                                    HTTP_X_REAL_IP='203.0.113.10',
                                    HTTP_X_FORWARDED_FOR=f'198.51.100.{i}').status_code
        self.assertEqual(last, 429)


class StaffRegistrationTests(TestCase):
    _n = 0

    def _register(self, path, role):
        StaffRegistrationTests._n += 1
        nid = f'00123456{StaffRegistrationTests._n:02d}'
        mobile = f'0912123456{StaffRegistrationTests._n}'
        return self.client.post(path, {
            'username': f'{role}1', 'password1': 'Str0ng-pass-993', 'password2': 'Str0ng-pass-993',
            'email': f'{role}@example.com', 'first_name': 'a', 'last_name': 'b',
            'national_id': nid, 'mobile_number': mobile, 'role': role,
        })

    def test_staff_roles_start_inactive_until_approved(self):
        for i, role in enumerate(('accountant', 'inspector', 'dehyari', 'engineer', 'council')):
            self._register(f'/register/{role}/', role)
        self.assertEqual(User.objects.count(), 5)   # guards against a vacuous pass
        for u in User.objects.all():
            self.assertFalse(u.is_active, u.username)
            self.assertEqual(u.profile.approval_status, 'pending', u.username)

    def test_admin_role_cannot_be_self_selected(self):
        from main.forms import CustomUserCreationForm
        choices = dict(CustomUserCreationForm().fields['role'].choices)
        self.assertNotIn('admin', choices)
        self._register('/register/dehyari/', 'admin')
        self.assertFalse(User.objects.filter(username='admin1').exists())


class UploadGuardTests(TestCase):
    def test_html_upload_is_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        User.objects.create_user('u2', password='x-pass-1234')
        self.client.login(username='u2', password='x-pass-1234')
        evil = SimpleUploadedFile('evil.html', b'<script>alert(1)</script>', content_type='text/html')
        r = self.client.post('/dashboard/upload-document/', {'request_id': 1, 'document': evil},
                             HTTP_ACCEPT='application/json')
        self.assertEqual(r.status_code, 400)
