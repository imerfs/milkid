"""Province -> county -> district -> settlement dropdowns, driven by HTMX swapping whole <select> elements."""
import re

from django.test import TestCase
from django.urls import reverse

from main.forms import CitizenRegistrationForm, CustomUserCreationForm
from main.models import CityVillage, County, District, Province


def tree():
    p = Province.objects.create(name='خراسان جنوبی')
    c = County.objects.create(province=p, name='بیرجند')
    c2 = County.objects.create(province=p, name='قاین')
    d = District.objects.create(county=c, name='مرکزی')
    d2 = District.objects.create(county=c, name='خوسف')
    v = CityVillage.objects.create(district=d, name='حاجی‌آباد', settlement_type='village')
    t = CityVillage.objects.create(district=d, name='بیرجند', settlement_type='city')
    return p, c, c2, d, d2, v, t


def selects(html):
    """{id: [option labels]} for every <select> in the response."""
    out = {}
    for m in re.finditer(r'<select\b([^>]*)>(.*?)</select>', html, re.S):
        ident = re.search(r'\bid="([^"]+)"', m.group(1)).group(1)
        out[ident] = re.findall(r'<option[^>]*>(.*?)</option>', m.group(2), re.S)
    return out


class OptionsEndpoint(TestCase):
    def get(self, form, changed, **values):
        return self.client.get(reverse('main:geo_options'), {'form': form, 'changed': changed, **values})

    def test_choosing_a_province_fills_the_counties_and_empties_the_rest(self):
        p, *_ = tree()
        response = self.get('citizen', 'province', province=p.id)
        found = selects(response.content.decode())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(found['id_county_citizen'][1:], ['بیرجند', 'قاین'])
        self.assertEqual(len(found['id_district_citizen']), 1)             # only the placeholder
        self.assertEqual(len(found['id_city_village_citizen']), 1)

    def test_choosing_a_county_fills_its_districts_only(self):
        p, c, c2, *_ = tree()
        found = selects(self.get('citizen', 'county', province=p.id, county=c.id).content.decode())
        self.assertEqual(found['id_district_citizen'][1:], ['خوسف', 'مرکزی'])
        self.assertNotIn('id_county_citizen', found)                       # the changed select itself is not replaced

    def test_choosing_a_district_lists_cities_and_villages_with_their_type(self):
        p, c, c2, d, *_ = tree()
        found = selects(self.get('citizen', 'district', district=d.id).content.decode())
        self.assertEqual(found['id_city_village_citizen'][1:], ['بیرجند (شهر)', 'حاجی‌آباد (روستا)'])

    def test_every_returned_select_is_an_out_of_band_swap_with_its_own_wiring(self):
        p, *_ = tree()
        html = self.get('role', 'province', province=p.id).content.decode()
        self.assertIn('id="id_county_role"', html)
        self.assertEqual(html.count('hx-swap-oob="true"'), 4)        # county, district, dehestan, city_village
        self.assertIn('hx-get="/geo/options/?form=role&amp;changed=county"', html)

    def test_empty_downstream_selects_are_disabled_and_filled_ones_are_not(self):
        p, *_ = tree()
        html = self.get('citizen', 'province', province=p.id).content.decode()
        county = re.search(r'<select[^>]*id="id_county_citizen"[^>]*>', html).group(0)
        district = re.search(r'<select[^>]*id="id_district_citizen"[^>]*>', html).group(0)
        self.assertNotIn('disabled', county)
        self.assertIn('disabled', district)

    def test_garbage_input_gives_empty_selects_not_an_error(self):
        response = self.get('citizen', 'province', province='x; drop table')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(selects(response.content.decode())['id_county_citizen']), 1)

    def test_unknown_form_or_level_is_a_404_and_posts_are_refused(self):
        self.assertEqual(self.get('nope', 'province').status_code, 404)
        self.assertEqual(self.get('citizen', 'city_village').status_code, 404)
        self.assertEqual(self.client.post(reverse('main:geo_options')).status_code, 405)

    def test_needs_no_login_because_registration_is_anonymous(self):
        p, *_ = tree()
        self.assertEqual(self.get('citizen', 'province', province=p.id).status_code, 200)


class FormsAreWired(TestCase):
    def test_province_county_district_ask_the_endpoint_when_they_change(self):
        for form_class, suffix, key in ((CitizenRegistrationForm, '_citizen', 'citizen'), (CustomUserCreationForm, '_role', 'role')):
            form = form_class()
            for level, child in (('province', 'county'), ('county', 'district'), ('district', 'city_village')):
                attrs = form.fields[level].widget.attrs
                self.assertEqual(attrs['hx-get'], f'/geo/options/?form={key}&changed={level}', (key, level))
                self.assertEqual(attrs['hx-trigger'], 'change')
                self.assertEqual(attrs['hx-swap'], 'none')
                self.assertEqual(attrs['id'], f'id_{level}{suffix}')
            self.assertNotIn('hx-get', form.fields['city_village'].widget.attrs)

    def test_only_the_values_of_the_geography_selects_are_sent_never_the_whole_form(self):
        attrs = CitizenRegistrationForm().fields['county'].widget.attrs
        self.assertEqual(attrs['hx-include'], '#id_province_citizen, #id_county_citizen')
        self.assertNotIn('password', attrs['hx-include'])

    def test_a_posted_county_from_another_province_is_rejected(self):
        p, c, *_ = tree()
        other = County.objects.create(province=Province.objects.create(name='دیگر'), name='جای دیگر')
        form = CitizenRegistrationForm(data={'province': p.id, 'county': other.id})
        form.is_valid()
        self.assertIn('county', form.errors)


class RegistrationPages(TestCase):
    def test_citizen_page_uses_htmx_and_not_the_old_cascade_script(self):
        html = self.client.get(reverse('main:register_citizen')).content.decode()
        self.assertIn('/static/vendor/htmx/htmx.min.js', html)
        self.assertNotIn('geographic_selector.js', html)
        self.assertIn('hx-get="/geo/options/?form=citizen&amp;changed=province"', html)


class MunicipalityRegistration(TestCase):
    def test_choosing_a_province_fills_counties_and_clears_the_district_only(self):
        p, *_ = tree()
        html = self.client.get(reverse('main:geo_options'), {'form': 'municipality', 'changed': 'province', 'province': p.id}).content.decode()
        found = selects(html)
        self.assertEqual(found['id_county'][1:], ['بیرجند', 'قاین'])
        self.assertEqual(len(found['id_district']), 1)
        self.assertNotIn('id_city_village', found)                          # the settlement is typed as text on this form
        self.assertEqual(html.count('hx-swap-oob="true"'), 2)

    def test_page_uses_htmx_and_the_old_scripts_are_gone(self):
        html = self.client.get(reverse('main:register_municipality')).content.decode()
        self.assertIn('/static/vendor/htmx/htmx.min.js', html)
        self.assertNotIn('geographic_selector.js', html)
        self.assertNotIn('/api/get-counties/', html)
        self.assertIn('hx-get="/geo/options/?form=municipality&amp;changed=province"', html)

    def test_a_county_of_another_province_is_rejected(self):
        from main.forms import MunicipalityRegistrationForm
        p, *_ = tree()
        stranger = County.objects.create(province=Province.objects.create(name='دیگر'), name='جای دیگر')
        form = MunicipalityRegistrationForm(data={'province': p.id, 'county': stranger.id})
        form.is_valid()
        self.assertIn('county', form.errors)

    def test_editing_keeps_the_stored_place_selected(self):
        from main.forms import MunicipalityRegistrationForm
        from main.tests.helpers import make_municipality, make_user
        p, c, c2, d, d2, *_ = tree()
        town = make_municipality(make_user('dehyari'))
        town.district = 'مرکزی'
        town.save()
        form = MunicipalityRegistrationForm(instance=town)
        self.assertEqual(form.fields['county'].initial, c)
        self.assertEqual({county.pk for county in form.fields['county'].queryset}, {c.pk, c2.pk})
        self.assertEqual({x.pk for x in form.fields['district'].queryset}, {d.pk, d2.pk})
