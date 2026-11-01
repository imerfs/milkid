"""Building permit, step 4: engineers, plans, forms 04-07, review and the dehyari's signature."""
from django.contrib.auth.models import User
from django.urls import reverse

from main.models import Notification, PermitDocument, PermitFile
from main.office import permit_step4, permits
from main.tests.helpers import client_for, make_user, requires_gis_data
from main.tests.test_permit_files import PDF, upload
from main.tests.test_permit_step3 import AtStepThree

PEOPLE = {
    'architect_name': 'محمد رضایی', 'architect_father': 'علی', 'architect_grade': '3', 'architect_field': 'معماری', 'architect_license': '12345',
    'structure_name': 'حسین کریمی', 'structure_father': 'رضا', 'structure_grade': '2', 'structure_field': 'عمران', 'structure_license': '67890',
    'supervisor_name': 'سعید احمدی', 'supervisor_father': 'حسن', 'supervisor_grade': '2', 'supervisor_field': 'عمران', 'supervisor_license': '11111',
}


class AtStepFour(AtStepThree):
    def setUp(self):
        super().setUp()
        self.send()
        self.decide()
        self.reload()
        self.assertEqual(self.permit.stage_no, 4)
        self.expert = User.objects.get(pk=make_user('engineer', city_village=self.village).pk)

    def url(self, name, *args):
        return reverse(f'main:permit_{name}', args=[self.permit.pk, *args])

    def people(self, who=None, **change):
        return client_for(who or self.citizen).post(self.url('design_people'), {**PEOPLE, **change})

    def plans(self, kind='plan_arch', n=2, who=None, name='sheet'):
        return client_for(who or self.citizen).post(self.url('design_upload'), {'kind': kind, 'plans': [upload(f'{name}{i}.png') for i in range(n)]})

    def ready(self):
        self.people()
        self.plans('plan_arch')
        self.plans('plan_struct', name='s')

    def submit(self, who=None):
        return client_for(who or self.citizen).post(self.url('design_submit'))

    def review(self, who=None, **ticks):
        data = {'signed_f05': 'on', 'signed_f06': 'on', 'signed_f07': 'on', **ticks}
        return client_for(who or self.clerk).post(self.url('design_review'), {k: v for k, v in data.items() if v is not None})

    def sign(self, who=None, **ticks):
        data = {'signed_f05': 'on', 'signed_f06': 'on', 'signed_f07': 'on', **ticks}
        return client_for(who or self.dehyari).post(self.url('design_sign'), {k: v for k, v in data.items() if v is not None})


@requires_gis_data
class Engineers(AtStepFour):
    def test_the_defaults_come_from_the_file_and_the_bonyads_answer(self):
        data = permit_step4.payload(self.permit)
        self.assertEqual(data['common']['owner'], 'علی رضایی')
        self.assertEqual((data['common']['floors'], data['common']['area']), (1, 135.0))
        self.assertEqual(data['order']['floor_area'], 135.0)               # one floor: the whole allowed area
        self.assertEqual(data['order']['kind'], 'construct')
        self.assertEqual(data['order']['sides']['north']['length'], 10.0)    # the limits form 1 holds
        self.assertEqual(data['order']['sides']['north']['passage'], 12)     # a street
        self.assertEqual(data['forms']['f04']['number'], '18/1837')           # the village's pattern goes on after form 2's number
        self.assertEqual(data['forms']['f05']['number'], '18/1838')

    def test_the_owner_saves_them_and_the_staff_can_correct_them(self):
        self.people()
        self.assertEqual(self.reload().design['people']['structure']['license'], '67890')
        self.people(self.clerk, structure_license='99999')
        self.assertEqual(self.reload().design['people']['structure']['license'], '99999')

    def test_nobody_else_saves_them(self):
        for who in (self.neighbour, self.stranger):
            self.people(who)
        self.assertNotIn('people', self.reload().design or {})

    def test_the_page_opens_for_the_owner_and_the_staff_only(self):
        for who in (self.citizen, self.clerk, self.dehyari):
            self.assertEqual(client_for(who).get(self.url('design')).status_code, 200, who.profile.role)
        for who in (self.neighbour, self.stranger):
            self.assertEqual(client_for(who).get(self.url('design')).status_code, 404)

    def test_the_page_hands_the_forms_their_data(self):
        payload = client_for(self.citizen).get(self.url('design')).context['payload']
        self.assertEqual(payload['owner'], 'علی رضایی')
        self.assertIn('forms/permit/form04_blank.jpg', payload['blank']['f04'])


@requires_gis_data
class Plans(AtStepFour):
    def test_the_owner_uploads_and_deletes_plans(self):
        self.plans('plan_arch', n=3)
        self.assertEqual(self.permit.documents.filter(kind='plan_arch').count(), 3)
        self.assertEqual(len(self.reload().design['hashes']), 3)
        doc = self.permit.documents.filter(kind='plan_arch').first()
        client_for(self.citizen).post(self.url('design_delete', doc.pk))
        self.assertEqual(self.permit.documents.filter(kind='plan_arch').count(), 2)
        self.assertEqual(len(self.reload().design['hashes']), 2)

    def test_only_the_owner_uploads_or_deletes(self):
        for who in (self.neighbour, self.stranger, self.clerk):
            self.plans(who=who)
        self.assertFalse(PermitDocument.objects.filter(kind='plan_arch').exists())
        self.plans()
        doc = PermitDocument.objects.filter(kind='plan_arch').first()
        for who in (self.neighbour, self.clerk):
            client_for(who).post(self.url('design_delete', doc.pk))
        self.assertEqual(PermitDocument.objects.filter(kind='plan_arch').count(), 2)

    def test_wrong_kinds_and_files_are_refused(self):
        client_for(self.citizen).post(self.url('design_upload'), {'kind': 'national_card', 'plans': [upload('a.png')]})
        client_for(self.citizen).post(self.url('design_upload'), {'kind': 'plan_arch', 'plans': [upload('a.txt', b'hello')]})
        client_for(self.citizen).post(self.url('design_upload'), {'kind': 'plan_arch'})
        self.assertFalse(PermitDocument.objects.filter(kind__startswith='plan').exists())

    def test_a_pdf_and_a_dxf_are_fine(self):
        client_for(self.citizen).post(self.url('design_upload'), {'kind': 'plan_struct', 'plans': [upload('s.pdf', PDF), upload('s.dxf', b'0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n')]})
        self.assertEqual(self.permit.documents.filter(kind='plan_struct').count(), 2)

    def test_plans_are_as_private_as_the_other_papers(self):
        self.plans()
        doc = self.permit.documents.filter(kind='plan_arch').first()
        for who in (self.citizen, self.clerk, self.dehyari):
            self.assertEqual(client_for(who).get(reverse('main:permit_document', args=[doc.pk])).status_code, 200)
        for who in (self.neighbour, self.stranger):
            self.assertEqual(client_for(who).get(reverse('main:permit_document', args=[doc.pk])).status_code, 404)


@requires_gis_data
class Submitting(AtStepFour):
    def test_it_needs_the_engineers_and_both_kinds_of_plan(self):
        self.submit()
        self.assertEqual(self.reload().design_state, '')
        self.people()
        self.plans('plan_arch')
        self.submit()
        self.assertEqual(self.reload().design_state, '')                    # no structure plans yet
        self.plans('plan_struct', name='s')
        self.submit()
        self.assertEqual(self.reload().design_state, 'submitted')
        self.assertTrue(Notification.objects.filter(user=self.clerk, title='نقشه‌های پرونده رسید').exists())
        self.assertEqual(self.permit.status_text, 'نقشه‌ها منتظر بررسی')

    def test_nothing_changes_after_sending(self):
        self.ready()
        self.submit()
        self.plans('plan_arch', name='late')
        self.people(structure_name='دیگری')
        self.assertEqual(self.permit.documents.filter(kind='plan_arch').count(), 2)
        self.assertEqual(self.reload().design['people']['structure']['name'], 'حسین کریمی')

    def test_only_the_owner_sends(self):
        self.ready()
        for who in (self.neighbour, self.clerk):
            self.submit(who)
        self.assertEqual(self.reload().design_state, '')

    def test_the_lists_count_it(self):
        self.ready()
        self.submit()
        self.assertEqual(permits.panel_rows(self.clerk)['waiting'], 1)


@requires_gis_data
class Reviewing(AtStepFour):
    def setUp(self):
        super().setUp()
        self.ready()
        self.submit()

    def test_any_of_the_staff_review_with_the_signed_forms_ticked(self):
        self.review(self.clerk)
        permit = self.reload()
        self.assertEqual((permit.design_state, permit.design_reviewed_by), ('reviewed', self.clerk))
        self.assertEqual(permit.status_text, 'منتظر امضای دهیار')
        self.assertTrue(permit.design['review']['forms']['f05'])
        self.assertTrue(Notification.objects.filter(user=self.dehyari, title='نقشه‌ها منتظر امضای شماست').exists())

    def test_the_expert_may_review_too(self):
        self.review(self.expert)
        self.assertEqual(self.reload().design_state, 'reviewed')

    def test_every_form_must_be_ticked(self):
        for missing in ('signed_f05', 'signed_f06', 'signed_f07'):
            self.review(**{missing: None})
        self.assertEqual(self.reload().design_state, 'submitted')

    def test_nobody_else_reviews(self):
        for who in (self.citizen, self.neighbour, self.stranger):
            self.review(who)
        self.assertEqual(self.reload().design_state, 'submitted')

    def test_sending_back_gives_the_owner_the_reason_and_a_second_try(self):
        client = client_for(self.clerk)
        client.post(self.url('design_return'), {'notes': ' '})
        self.assertEqual(self.reload().design_state, 'submitted')
        client.post(self.url('design_return'), {'notes': 'برگه‌ی مقاطع سازه ناقص است'})
        permit = self.reload()
        self.assertEqual((permit.design_state, permit.request.status), ('returned', 'requires_documents'))
        page = client_for(self.citizen).get(self.url('design')).content.decode()
        self.assertIn('برگه‌ی مقاطع سازه ناقص است', page)
        self.plans('plan_struct', n=1, name='fix')
        self.submit()
        permit = self.reload()
        self.assertEqual((permit.design_state, permit.request.status), ('submitted', 'pending'))


@requires_gis_data
class Signing(AtStepFour):
    def setUp(self):
        super().setUp()
        self.ready()
        self.submit()
        self.review()

    def test_only_the_dehyari_signs(self):
        for who in (self.clerk, self.expert, self.citizen, self.neighbour, self.stranger):
            self.sign(who)
        self.assertEqual(self.reload().design_state, 'reviewed')
        self.sign()
        permit = self.reload()
        self.assertEqual((permit.design_state, permit.stage_no, permit.design_signed_by), ('signed', 5, self.dehyari))
        self.assertEqual(permit.design['signed']['files'], 4)
        self.assertEqual(len(permit.design['signed']['sha256']), 64)
        self.assertTrue(Notification.objects.filter(user=self.citizen, title='نقشه‌های شما امضا شد').exists())
        self.assertEqual(permit.status_text, 'منتظر تعیین عوارض (مسئول مالی)')

    def test_the_dehyari_may_review_and_sign_in_one_go_but_must_tick_the_forms(self):
        PermitFile.objects.filter(pk=self.permit.pk).update(design_state='submitted')
        self.sign(signed_f06=None)
        self.assertEqual(self.reload().design_state, 'submitted')
        self.sign()
        self.assertEqual(self.reload().stage_no, 5)

    def test_signing_twice_changes_nothing(self):
        self.sign()
        before = self.reload().design['signed']
        self.sign()
        self.assertEqual(self.reload().design['signed'], before)

    def test_what_was_signed_is_remembered(self):
        self.sign()
        self.assertFalse(permit_step4.tampered(self.reload()))
        PermitDocument.objects.create(file=self.permit, kind='plan_arch', document=self.permit.documents.first().document,
                                      original_name='extra.png', size=1)
        self.assertTrue(permit_step4.tampered(self.reload()))
        self.assertIn('تغییر کرده', client_for(self.dehyari).get(self.url('design')).content.decode())

    def test_nothing_is_edited_after_the_signature(self):
        self.sign()
        self.people(self.clerk, structure_name='x')
        client_for(self.clerk).post(self.url('design_forms'), {'f04_number': '1/1', 'f04_date': '1405/01/01'})
        permit = self.reload()
        self.assertEqual(permit.design['people']['structure']['name'], 'حسین کریمی')
        self.assertNotIn('forms', permit.design)


@requires_gis_data
class FormNumbers(AtStepFour):
    def test_the_staff_set_the_numbers_and_form_04(self):
        client_for(self.clerk).post(self.url('design_forms'), {
            'f04_number': '18/1840', 'f04_date': '1405/08/10', 'f05_number': '18/1841', 'f05_date': '1405/08/10',
            'c_owner': 'علی رضایی', 'c_floors': '2', 'c_area': '270', 'o_kind': 'repair', 'o_basis': 'urf', 'o_floors': '2', 'o_floor_area': '135',
            's_north_length': '10', 's_north_after': '9.5', 's_north_passage': '12', 's_north_approved': '12'})
        data = permit_step4.payload(self.reload())
        self.assertEqual((data['forms']['f04']['number'], data['forms']['f05']['number']), ('18/1840', '18/1841'))
        self.assertEqual((data['order']['kind'], data['order']['basis'], data['order']['sides']['north']['after']), ('repair', 'urf', '9.5'))
        self.assertEqual(data['common']['floors'], '2')

    def test_the_owner_and_others_cannot(self):
        for who in (self.citizen, self.neighbour, self.stranger):
            client_for(who).post(self.url('design_forms'), {'f04_number': '9/9', 'f04_date': '1405/01/01'})
        self.assertNotIn('forms', self.reload().design or {})

    def test_the_file_page_leads_to_step_four(self):
        page = client_for(self.citizen).get(reverse('main:permit_file', args=[self.permit.pk])).content.decode()
        self.assertIn(self.url('design'), page)

    def test_before_step_four_the_page_is_closed(self):
        PermitFile.objects.filter(pk=self.permit.pk).update(stage_no=3)
        self.assertEqual(client_for(self.citizen).get(self.url('design')).status_code, 302)
