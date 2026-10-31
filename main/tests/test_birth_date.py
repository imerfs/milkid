"""The date of birth is asked in the registrations and the profile: Jalali (Persian or Latin digits), stored as YYYY/MM/DD, never in the future."""
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from main.forms import CitizenRegistrationForm, ProfileUpdateForm
from main.widgets import BirthDateField
from main.tests.helpers import client_for, make_user


class Field(SimpleTestCase):
    def clean(self, value, **kw):
        return BirthDateField(**kw).clean(value)

    def test_persian_and_latin_digits_normalise_to_one_format(self):
        self.assertEqual(self.clean('۱۳۷۶/۴/۱۲'), '1376/04/12')
        self.assertEqual(self.clean('1376-4-12'), '1376/04/12')
        self.assertEqual(self.clean('1376.04.12'), '1376/04/12')

    def test_bad_dates_are_refused(self):
        for bad in ('1376/13/01', '1376/07/31', '1404/12/30', 'x', '1376/04', '1200/01/01', '1500/01/01'):
            with self.subTest(bad=bad):
                with self.assertRaises(Exception):
                    self.clean(bad)

    def test_a_leap_year_has_its_thirtieth_of_esfand(self):
        self.assertEqual(self.clean('1375/12/30'), '1375/12/30')      # 1375 is a leap year

    def test_required_or_optional(self):
        with self.assertRaises(Exception):
            self.clean('', required=True)
        self.assertEqual(self.clean('', required=False), '')


class Registration(TestCase):
    def post(self, **over):
        data = {'username': 'new.user', 'first_name': 'علی', 'last_name': 'رضایی', 'email': 'a@b.ir', 'national_id': '0012345678',
                'mobile_number': '09121234567', 'birth_date': '1376/04/12', 'role': 'citizen', 'password1': 'S3cret-pass-99', 'password2': 'S3cret-pass-99'}
        data.update(over)
        return data

    def test_the_form_asks_for_it_and_keeps_it(self):
        form = CitizenRegistrationForm(self.post())
        form.is_valid()
        self.assertNotIn('birth_date', form.errors)
        self.assertEqual(form.cleaned_data['birth_date'], '1376/04/12')
        missing = CitizenRegistrationForm(self.post(birth_date=''))
        self.assertFalse(missing.is_valid())
        self.assertIn('birth_date', missing.errors)

    def test_the_registration_page_has_the_field_and_the_date_picker(self):
        page = self.client.get(reverse('main:register_citizen'))
        self.assertContains(page, 'name="birth_date"')
        self.assertContains(page, 'jalali-datepicker')

    def test_the_profile_form_saves_it(self):
        user = make_user('citizen')
        form = ProfileUpdateForm({'first_name': 'علی', 'last_name': 'رضایی', 'mobile_number': '09121234567', 'birth_date': '۱۳۷۰/۰۱/۰۱'}, instance=user.profile)
        form.is_valid()
        self.assertNotIn('birth_date', form.errors)
        self.assertEqual(form.cleaned_data['birth_date'], '1370/01/01')

    def test_the_mayor_panel_profile_saves_it_and_refuses_a_bad_one(self):
        from main.tests.helpers import make_municipality
        dehyari = make_user('dehyari')
        make_municipality(dehyari, 'روستای الف')
        c = client_for(dehyari)
        url = reverse('main:mayor_panel', args=['profile'])
        base = {'first_name': 'علی', 'last_name': 'رضایی', 'mobile_number': '09121234567'}
        self.assertEqual(c.post(url, {**base, 'birth_date': '1370/13/01'}).status_code, 400)
        self.assertEqual(c.post(url, {**base, 'birth_date': '۱۳۷۰/۰۱/۰۱'}).status_code, 200)
        from django.contrib.auth.models import User
        self.assertEqual(User.objects.get(pk=dehyari.pk).profile.birth_date, '1370/01/01')
