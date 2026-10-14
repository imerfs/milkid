from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from main.models import RoleGrant
from main.tests.helpers import client_for, make_municipality, make_user

VALID = {'username': 'ali.fani', 'first_name': 'علی', 'last_name': 'فنی',
         'national_id': '0012345678', 'mobile_number': '09121234567', 'role': 'engineer'}


class StaffAccountCreation(TestCase):
    def setUp(self):
        self.dehyari = make_user('dehyari')
        make_municipality(self.dehyari, 'روستای الف')
        self.url = reverse('main:role_create_account')

    def create(self, who=None, **over):
        return client_for(who or self.dehyari).post(self.url, {**VALID, **over})

    def test_dehyari_creates_each_staff_role_in_own_village(self):
        for i, role in enumerate(('accountant', 'engineer', 'inspector', 'council')):
            r = self.create(role=role, username=f'user{i}', national_id=f'00123456{i:02d}', mobile_number=f'0912123456{i}')
            self.assertEqual(r.status_code, 302, r.content.decode()[:300])
            user = User.objects.get(username=f'user{i}')
            self.assertEqual(user.profile.role, role)
            self.assertEqual(user.profile.city_village, 'روستای الف')
            self.assertTrue(user.is_active and user.profile.is_verified)
            self.assertTrue(RoleGrant.objects.filter(user=user, role=role, granted_by=self.dehyari).exists())

    def test_initial_password_is_national_id_and_must_be_changed(self):
        self.create()
        user = User.objects.get(username='ali.fani')
        self.assertTrue(user.profile.must_change_password)
        c = Client()
        self.assertTrue(c.login(username='ali.fani', password=VALID['national_id']))
        change = reverse('main:password_change')
        for url in ('/', reverse('main:letters_inbox')):
            self.assertRedirects(c.get(url), change, fetch_redirect_response=False)
        self.assertEqual(c.get(change).status_code, 200)
        self.assertEqual(c.get(reverse('main:logout')).status_code, 302)   # logout stays reachable

    def test_password_change_rules_and_unlock(self):
        self.create()
        c = Client()
        c.login(username='ali.fani', password=VALID['national_id'])
        url = reverse('main:password_change')
        def post(old, new, new2=None):
            return c.post(url, {'old_password': old, 'new_password': new, 'new_password2': new2 or new})
        nid = VALID['national_id']
        self.assertEqual(post('wrong', 'Zx-93kd-Qw71').status_code, 400)       # wrong current password
        self.assertEqual(post(nid, nid).status_code, 400)                      # same as national id / old
        self.assertEqual(post(nid, 'Zx-93kd-Qw71', 'other').status_code, 400)  # mismatch
        self.assertEqual(post(nid, '12345').status_code, 400)                  # weak
        self.assertTrue(User.objects.get(username='ali.fani').profile.must_change_password)
        self.assertEqual(post(nid, 'Zx-93kd-Qw71').status_code, 302)
        user = User.objects.get(username='ali.fani')
        self.assertFalse(user.profile.must_change_password)
        self.assertTrue(user.check_password('Zx-93kd-Qw71'))
        self.assertEqual(c.get(reverse('main:letters_inbox')).status_code, 200)  # no longer redirected

    def test_existing_accounts_are_not_forced(self):
        user = make_user('citizen')
        self.assertFalse(user.profile.must_change_password)
        self.assertNotEqual(client_for(user).get(reverse('main:letters_inbox'), HTTP_SEC_FETCH_DEST='iframe').status_code, 302)

    def test_dehyari_and_admin_roles_cannot_be_created(self):
        for role in ('dehyari', 'admin', 'citizen', 'resident', ''):
            r = self.create(role=role)
            self.assertEqual(r.status_code, 400, role)
        self.assertFalse(User.objects.filter(username='ali.fani').exists())

    def test_invalid_input_creates_nothing(self):
        for bad in ({'national_id': '123'}, {'national_id': '00123456ab'}, {'mobile_number': '12345'},
                    {'username': ''}, {'username': 'a b'}, {'first_name': ''}, {'last_name': 'x' * 200}):
            self.assertEqual(self.create(**bad).status_code, 400, bad)
        self.assertFalse(User.objects.filter(username='ali.fani').exists())

    def test_duplicate_username_or_national_id_is_refused(self):
        self.assertEqual(self.create().status_code, 302)
        self.assertEqual(self.create(national_id='0099999999', mobile_number='09120000000').status_code, 400)  # same username
        self.assertEqual(self.create(username='other').status_code, 400)                                      # same national id
        self.assertEqual(User.objects.filter(profile__national_id='0012345678').count(), 1)

    def test_only_a_dehyari_can_create(self):
        for role in ('citizen', 'accountant', 'engineer', 'council', 'admin'):
            r = self.create(who=make_user(role))
            self.assertIn(r.status_code, (302, 400, 403), role)
            self.assertFalse(User.objects.filter(username='ali.fani').exists(), role)
        self.assertEqual(client_for().post(self.url, VALID).status_code, 302)  # anonymous: sent to login
        self.assertFalse(User.objects.filter(username='ali.fani').exists())

    def test_get_is_not_allowed(self):
        self.assertEqual(client_for(self.dehyari).get(self.url).status_code, 405)

    def test_form_is_on_the_roles_page(self):
        html = client_for(self.dehyari).get(reverse('main:mayor_panel', args=['employees'])).content.decode()
        self.assertIn(self.url, html)
