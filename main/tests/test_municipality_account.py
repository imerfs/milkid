"""A municipality registration carries its dehyari's account: inactive until an admin approves."""
import json

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from main import municipality_approval
from main.models import CityVillage, County, District, Municipality, Province
from main.tests.helpers import client_for, make_user

PASSWORD = 'Dehyari-pass-4821'


def place():
    p = Province.objects.create(name='خراسان جنوبی')
    c = County.objects.create(province=p, name='بیرجند')
    d = District.objects.create(county=c, name='مرکزی')
    return p, c, d


def registration_data(p, c, d, **over):
    data = {
        'name': 'دهیاری حاجی‌آباد', 'municipality_type': 'dehyari',
        'province': p.id, 'county': c.id, 'district': d.id,
        'city_village': 'حاجی‌آباد', 'settlement_type': 'village',
        'official_phone': '05632200000', 'official_email': 'office@example.ir',
        'postal_code': '9710000000', 'address': 'خیابان اصلی',
        'establishment_date': '2020-01-01', 'population': 500, 'area_hectares': '12.5',
        'manager_name': 'علی رضایی', 'manager_national_id': '0012345679',
        'manager_phone': '09121234567', 'manager_email': 'ali@example.ir',
        'manager_username': 'ali_dehyar', 'manager_password': PASSWORD, 'manager_password2': PASSWORD,
        'governor_decree': SimpleUploadedFile('decree.pdf', b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\n', 'application/pdf'),
    }
    data.update(over)
    return data


def existing_place():
    return Province.objects.first(), County.objects.first(), District.objects.first()


class Registration(TestCase):
    def setUp(self):
        cache.clear()  # registration is throttled per IP; tests share the cache

    def register(self, **over):
        p, c, d = existing_place() if Province.objects.exists() else place()
        return self.client.post(reverse('main:register_municipality'), registration_data(p, c, d, **over))

    def test_creates_an_inactive_account_linked_to_the_municipality(self):
        response = self.register()
        errors = response.context['form'].errors if response.status_code == 200 else None
        self.assertEqual(response.status_code, 302, errors)
        town = Municipality.objects.get()
        user = User.objects.get(username='ali_dehyar')
        self.assertEqual(town.status, 'pending')
        self.assertEqual((town.admin_user, town.manager_user), (user, user))
        self.assertFalse(user.is_active)
        self.assertEqual(user.profile.role, 'citizen')          # not a dehyari until approved
        self.assertEqual(user.profile.approval_status, 'pending')
        self.assertEqual(user.profile.national_id, '0012345679')
        self.assertTrue(user.check_password(PASSWORD))

    def test_cannot_log_in_before_approval(self):
        self.register()
        self.assertFalse(self.client.login(username='ali_dehyar', password=PASSWORD))

    def test_registering_does_not_touch_places_or_the_current_dehyari(self):
        p, c, d = place()
        CityVillage.objects.create(district=d, name='حاجی‌آباد', settlement_type='village')
        old = make_user('dehyari', province='خراسان جنوبی', county='بیرجند', city_village='حاجی‌آباد')
        self.client.post(reverse('main:register_municipality'), registration_data(p, c, d))
        old.profile.refresh_from_db()
        self.assertEqual(old.profile.role, 'dehyari')
        self.assertFalse(CityVillage.objects.get(name='حاجی‌آباد').has_municipality)

    def test_duplicate_national_id_and_weak_password_are_rejected(self):
        make_user('citizen', national_id='0012345679')
        response = self.register()
        self.assertEqual(response.status_code, 200)
        self.assertIn('manager_national_id', response.context['form'].errors)
        self.assertEqual(Municipality.objects.count(), 0)
        response = self.register(manager_national_id='0987654321', manager_password='12345678')
        self.assertIn('manager_password', response.context['form'].errors)
        self.assertFalse(User.objects.filter(username='ali_dehyar').exists())


    def test_password_repeat_must_match(self):
        response = self.register(manager_password2='Different-pass-9999')
        self.assertEqual(response.status_code, 200)
        self.assertIn('manager_password2', response.context['form'].errors)
        self.assertEqual(Municipality.objects.count(), 0)
        response = self.register(manager_password2='')
        self.assertIn('manager_password2', response.context['form'].errors)


class Approval(TestCase):
    def setUp(self):
        cache.clear()
        self.p, self.c, self.d = place()
        self.admin = make_user('admin')

    def register_and_get(self, **over):
        self.client.post(reverse('main:register_municipality'), registration_data(self.p, self.c, self.d, **over))
        return Municipality.objects.get(name=over.get('name', 'دهیاری حاجی‌آباد'))

    def approve_via_api(self, town):
        response = client_for(self.admin).post(
            reverse('main:api_admin_municipality_action', args=[town.id]),
            data=json.dumps({'action': 'approve'}), content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)

    def test_approval_activates_the_account_and_it_can_log_in(self):
        town = self.register_and_get()
        self.approve_via_api(town)
        user = User.objects.get(username='ali_dehyar')
        user.profile.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertEqual((user.profile.role, user.profile.approval_status), ('dehyari', 'approved'))
        self.assertTrue(self.client.login(username='ali_dehyar', password=PASSWORD))

    def test_a_new_place_is_added_on_approval(self):
        town = self.register_and_get()
        self.assertFalse(CityVillage.objects.filter(name='حاجی‌آباد').exists())
        self.approve_via_api(town)
        place_row = CityVillage.objects.get(name='حاجی‌آباد')
        self.assertEqual((place_row.district, place_row.settlement_type), (self.d, 'village'))
        self.assertTrue(place_row.has_municipality)
        self.assertEqual(place_row.municipality, town)

    def test_an_existing_place_is_reused_not_duplicated(self):
        CityVillage.objects.create(district=self.d, name='حاجی‌آباد', settlement_type='village')
        self.approve_via_api(self.register_and_get())
        self.assertEqual(CityVillage.objects.filter(name='حاجی‌آباد').count(), 1)

    def test_the_previous_dehyari_of_that_place_becomes_a_citizen(self):
        CityVillage.objects.create(district=self.d, name='حاجی‌آباد', settlement_type='village')
        old = make_user('dehyari', province='خراسان جنوبی', county='بیرجند', district='مرکزی', city_village='حاجی‌آباد')
        elsewhere = make_user('dehyari', province='خراسان جنوبی', county='بیرجند', city_village='جای دیگر')
        self.approve_via_api(self.register_and_get())
        old.profile.refresh_from_db()
        elsewhere.profile.refresh_from_db()
        self.assertEqual(old.profile.role, 'citizen')
        self.assertEqual(elsewhere.profile.role, 'dehyari')     # other places are untouched
        self.assertEqual(User.objects.get(username='ali_dehyar').profile.role, 'dehyari')

    def test_without_a_previous_dehyari_the_new_one_simply_becomes_dehyari(self):
        town = self.register_and_get()
        replaced = municipality_approval.approve(town, self.admin)
        self.assertEqual(replaced, [])
        self.assertEqual(town.admin_user.profile.role, 'dehyari')

    def test_rejection_leaves_the_account_inactive(self):
        town = self.register_and_get()
        client_for(self.admin).post(reverse('main:api_admin_municipality_action', args=[town.id]),
                                    data=json.dumps({'action': 'reject'}), content_type='application/json')
        self.assertFalse(User.objects.get(username='ali_dehyar').is_active)
