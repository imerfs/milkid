"""The application form: the geographic block has the registration form's layout, and the four limits are written «به طول x متر منتهی به … متری» and stay editable."""
from django.urls import reverse

from main.models import PermitFile
from main.tests.helpers import client_for
from main.tests.test_permit_files import Village, application


class Layout(Village):
    def test_the_geographic_block_looks_like_the_registration_form(self):
        page = client_for(self.citizen).get(reverse('main:building_permit_form'))
        for needle in ('fa-map-signs', 'fa-map-marker-alt', 'ابتدا استان را انتخاب کنید، سپس به ترتیب شهرستان', 'پس از انتخاب استان فعال می‌شود',
                       'id="id_province_bp"', 'id="id_county_bp"', 'id="id_district_bp"', 'id="id_city_village_bp"', 'id="id_dehestan_bp"'):
            self.assertContains(page, needle)

    def test_each_limit_has_its_parts_and_the_editable_sentence(self):
        page = client_for(self.citizen).get(reverse('main:building_permit_form'))
        for side in ('north', 'south', 'east', 'west'):
            self.assertContains(page, f'data-limit="{side}"')
            self.assertContains(page, f'name="limit_{side}"')
        self.assertContains(page, 'به طول')

    def test_the_sentences_are_kept_as_the_owner_edited_them(self):
        post = application('deed', limit_north='به طول ۲۰ متر منتهی به معبر ۸ متری', limit_south='به طول ۱۵ متر منتهی به قطعه ۲۳۷ (ویرایش‌شده)',
                           limit_east='', limit_west='به طول ۱۰ متر منتهی به ملک آقای احمدی')
        self.assertEqual(client_for(self.citizen).post(reverse('main:building_permit_form'), post).status_code, 302)
        details = PermitFile.objects.latest('pk').details
        self.assertEqual(details['limit_north'], 'به طول ۲۰ متر منتهی به معبر ۸ متری')
        self.assertEqual(details['limit_south'], 'به طول ۱۵ متر منتهی به قطعه ۲۳۷ (ویرایش‌شده)')
        self.assertNotIn('limit_east', details)
        self.assertEqual(details['limit_west'], 'به طول ۱۰ متر منتهی به ملک آقای احمدی')

    def test_the_file_page_shows_them(self):
        client_for(self.citizen).post(reverse('main:building_permit_form'), application('deed', limit_north='به طول ۲۰ متر منتهی به معبر ۸ متری'))
        permit = PermitFile.objects.latest('pk')
        self.assertContains(client_for(self.citizen).get(reverse('main:permit_file', args=[permit.pk])), 'به طول ۲۰ متر منتهی به معبر ۸ متری')


class ServiceForms(Village):
    """The other service request forms ask for the place the same way: the cascading selects, no free text."""
    PAGES = ('main:land_use_change_form', 'main:hadi_plan_form', 'main:property_deed_step1_alt', 'main:residence_confirmation_step2')

    def test_each_form_has_the_cascade_selects_and_no_free_text_place(self):
        for name in self.PAGES:
            with self.subTest(page=name):
                page = client_for(self.citizen).get(reverse(name))
                self.assertEqual(page.status_code, 200)
                for needle in ('id="id_province_sr"', 'id="id_county_sr"', 'id="id_district_sr"', 'id="id_city_village_sr"', 'GeographicCascade', 'geographic_cascade.js'):
                    self.assertContains(page, needle)
                self.assertNotContains(page, 'placeholder="مثال: تهران"')
