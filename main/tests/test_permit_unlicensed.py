"""Construction without a permit, step 1 (ایجاد پرونده اولیه): filing, who may confirm it, and that the later
building-permit steps stay closed to a file of this track."""
from django.urls import reverse

from main.models import MapParcel, Notification, PermitFile, VillageMap
from main.tests.helpers import client_for
from main.tests.test_permit_files import Village, application

CODE = '0-0-8-182-2'


def unlicensed(ownership='agreement', **override):
    data = application(ownership, built_area='70.28', floors='1', built_year='1402', **override)
    data.pop('permit_kind', None)
    return data


class UnlicensedBase(Village):
    url = 'main:without_permit_form'

    def file_it(self, who=None, **override):
        return client_for(who or self.citizen).post(reverse(self.url), unlicensed(**override))

    def filed(self, **override):          # pylint: disable=arguments-differ
        response = self.file_it(**override)
        self.assertEqual(response.status_code, 302, getattr(response, 'context', None) and response.context['errors'])
        return PermitFile.objects.latest('pk')


class UnlicensedFiling(UnlicensedBase):
    def test_the_form_opens_for_a_citizen_and_is_closed_to_the_rest(self):
        page = client_for(self.citizen).get(reverse(self.url))
        self.assertEqual(page.status_code, 200)
        body = page.content.decode()
        self.assertIn('مشخصات بنای ساخته‌شده', body)
        self.assertNotIn('قرارداد واگذاری بنیاد مسکن', body)      # the Bonyad lease belongs to the permit track
        self.assertNotIn('name="permit_kind"', body)
        for who in (self.clerk, self.engineer, self.dehyari):
            self.assertEqual(client_for(who).get(reverse(self.url)).status_code, 302)
        self.assertEqual(self.client.get(reverse(self.url)).status_code, 302)

    def test_a_valid_application_makes_a_no_permit_request_and_a_file_of_its_own_track(self):
        permit = self.filed()
        sr = permit.request
        self.assertEqual((permit.track, permit.stage_no, permit.state, permit.ownership_type), ('unlicensed', 1, 'submitted', 'agreement'))
        self.assertEqual((sr.request_type, sr.user), ('no_permit', self.citizen))
        self.assertEqual(permit.details['built_area'], '70.28')
        self.assertEqual((permit.details['floors'], permit.details['built_year']), ('1', '1402'))
        self.assertEqual(permit.people.count(), 1)
        for kind in ('national_card', 'birth_cert', 'agreement', 'shamim'):
            self.assertTrue(permit.documents.filter(kind=kind).exists(), kind)
        self.assertEqual(permit.stage_title, 'ایجاد پرونده اولیه')
        self.assertTrue(Notification.objects.filter(user=self.clerk, title__contains='ساخت‌وساز بدون پروانه').exists())
        self.assertTrue(Notification.objects.filter(user=self.engineer, title__contains='ساخت‌وساز بدون پروانه').exists())

    def test_a_deed_works_too_but_the_bonyad_contract_does_not(self):
        self.assertEqual(self.filed(ownership_type='deed', deed=application('deed')['deed']).ownership_type, 'deed')
        response = self.file_it(ownership_type='bonyad')
        self.assertEqual(response.status_code, 400)
        self.assertIn('ownership_type', response.context['errors'])

    def test_the_built_building_must_be_described(self):
        for field in ('built_area', 'floors'):
            response = client_for(self.citizen).post(reverse(self.url), {**unlicensed(), field: ''})
            self.assertEqual(response.status_code, 400, field)
            self.assertIn(field, response.context['errors'])
        for field, value in (('built_area', '-3'), ('floors', '99'), ('built_year', '2010')):
            response = client_for(self.citizen).post(reverse(self.url), {**unlicensed(), field: value})
            self.assertEqual(response.status_code, 400, (field, value))
            self.assertIn(field, response.context['errors'])
        self.assertFalse(PermitFile.objects.exists())

    def test_the_permit_form_still_asks_for_its_own_kind_and_makes_a_permit_file(self):
        response = client_for(self.citizen).post(reverse('main:building_permit_form'), {**application(), 'permit_kind': ''})
        self.assertEqual(response.status_code, 400)
        permit = Village.filed(self)
        self.assertEqual((permit.track, permit.request.request_type), ('permit', 'building_permit'))


class UnlicensedStaff(UnlicensedBase):
    def setUp(self):
        super().setUp()
        self.permit = self.filed()
        self.map = VillageMap.objects.get(slug='dastgerd')
        self.parcel = MapParcel.objects.filter(village_map=self.map, renewal_code=CODE).first()
        self.assertIsNotNone(self.parcel)

    def confirm(self, who):
        return client_for(who).post(reverse('main:permit_open', args=[self.permit.pk]),
                                    {'renewal_code': CODE, 'notes': 'مدارک کامل بود'}, follow=True)

    def test_the_file_page_shows_the_six_steps_and_the_staffs_form(self):
        page = client_for(self.clerk).get(reverse('main:permit_file', args=[self.permit.pk])).content.decode()
        self.assertIn('درخواست کمیسیون ماده ۹۹ و بازدید', page)
        self.assertNotIn('استعلام بنیاد مسکن', page)
        self.assertIn('تایید مرحله‌ی ۱ و دادن کد نوسازی', page)
        self.assertIn('زیربنای ساخته‌شده', page)
        mine = client_for(self.citizen).get(reverse('main:permit_file', args=[self.permit.pk])).content.decode()
        self.assertNotIn('تایید مرحله‌ی ۱ و دادن کد نوسازی', mine)

    def test_the_clerk_the_expert_and_the_dehyari_each_can_confirm_step_one(self):
        for who in (self.clerk, self.engineer, self.dehyari):
            permit = self.filed()
            self.permit = permit
            self.confirm(who)
            permit.refresh_from_db()
            permit.request.refresh_from_db()
            self.assertEqual((permit.state, permit.stage_no, permit.renewal_code, permit.opened_by),
                             ('done', 2, CODE, who), who.profile.role)
            self.assertEqual(permit.request.status, 'in_review')

    def test_the_owner_the_accountant_and_other_villages_cannot(self):
        for who in (self.citizen, self.accountant, self.stranger_clerk):
            self.confirm(who)
            self.permit.refresh_from_db()
            self.assertEqual((self.permit.state, self.permit.stage_no), ('submitted', 1), who.profile.role)
        for who in (self.neighbour, self.stranger_clerk, self.accountant):
            self.assertEqual(client_for(who).get(reverse('main:permit_file', args=[self.permit.pk])).status_code, 404)

    def test_staff_can_send_it_back_or_refuse_it_like_any_file(self):
        response = client_for(self.engineer).post(reverse('main:permit_send_back', args=[self.permit.pk]), {'notes': 'قولنامه ناخوانا است'})
        self.assertEqual(response.status_code, 302)
        self.permit.refresh_from_db()
        self.assertEqual(self.permit.state, 'needs_docs')
        client_for(self.dehyari).post(reverse('main:permit_refuse', args=[self.permit.pk]), {'notes': 'خارج از محدوده'})
        self.permit.refresh_from_db()
        self.assertEqual(self.permit.state, 'rejected')

    def test_after_confirming_the_later_building_permit_steps_stay_closed(self):
        self.confirm(self.clerk)
        for name in ('permit_forms', 'permit_design', 'permit_fees', 'permit_licence', 'permit_services', 'permit_endwork',
                     'permit_supervision', 'permit_extension'):
            for who in (self.citizen, self.clerk, self.dehyari):
                self.assertEqual(client_for(who).get(reverse(f'main:{name}', args=[self.permit.pk])).status_code, 404, (name, who.profile.role))
        page = client_for(self.citizen).get(reverse('main:permit_file', args=[self.permit.pk])).content.decode()
        self.assertIn('فرم درخواست و تعهدنامه', page)
        self.assertNotIn(reverse('main:permit_forms', args=[self.permit.pk]), page)
        self.permit.refresh_from_db()
        self.assertEqual(self.permit.status_text, 'منتظر فرم درخواست و تعهدنامه‌ی امضاشده (از متقاضی)')
        self.assertFalse(self.permit.needs_staff)           # waiting for the owner's forms, not for the staff

    def test_it_is_listed_in_the_staff_panel_with_its_own_label(self):
        from main.office import permits
        rows = permits.panel_rows(self.clerk)['rows']
        self.assertIn(self.permit, rows)
        page = client_for(self.clerk).get('/dashboard/clerk/?tab=files').content.decode()
        self.assertIn('ساخت‌وساز بدون پروانه', page)
