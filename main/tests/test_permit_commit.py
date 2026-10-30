"""Construction without a permit, step 5: the judiciary experts the dehyari lists, the introduction, the neighbours' consent and the
notarial undertaking, each confirmed by any of the clerk / technical expert / dehyari, and the confirmation that ends the step."""
from django.urls import reverse

from main.models import JudicialExpert, MapParcel, Notification, ParcelArchive, PermitDocument, VillageMap
from main.office import permit_commit, plotmap
from main.tests.helpers import client_for
from main.tests.test_permit_files import PNG, upload
from main.tests.test_permit_notice import soon
from main.tests.test_permit_report import Step4
from main.tests.test_permit_step2 import SLUG, plot

GEOM = {'type': 'Polygon', 'coordinates': []}


class Step5(Step4):
    def setUp(self):
        super().setUp()
        self.fill()
        self.act(self.dehyari, 'permit_step4_finish', confirm='on')
        self.assertEqual(self.reload().stage_no, 5)
        self.expert = JudicialExpert.objects.create(city_village=permit_commit.permit_step2._village(self.permit), name='مهندس حسین مالکی', field='راه و ساختمان')

    def deliver(self, **over):
        post = {'scan': upload('d.png', PNG), 'deed_no': '4481', 'deed_date': '1405/06/22', 'office': 'دفترخانه ۶۴ بیرجند', 'delivered': 'on'}
        post.update(over)
        return client_for(self.citizen).post(self.url('permit_deed_upload'), post, follow=True)

    def consent(self, **over):
        post = {'scan': upload('c.png', PNG), 'signed': 'on'}
        post.update(over)
        return client_for(self.citizen).post(self.url('permit_consent_upload'), post, follow=True)

    def introduce(self, who=None, **over):
        post = {'expert': self.expert.pk, 'letter_no': '12', 'letter_date': ''}
        post.update(over)
        return client_for(who or self.clerk).post(self.url('permit_commit_introduce'), post, follow=True)


class Experts(Step5):
    def test_only_the_dehyari_manages_the_list_and_the_three_staff_read_it(self):
        add = lambda who: client_for(who).post(reverse('main:permit_expert_add'), {'name': 'مهندس رضا احمدی', 'field': 'عمران', 'phone': '09151234567'})
        for who in (self.clerk, self.engineer, self.citizen, self.accountant):
            add(who)
        self.assertFalse(JudicialExpert.objects.filter(name='مهندس رضا احمدی').exists())
        add(self.dehyari)
        self.assertTrue(JudicialExpert.objects.filter(name='مهندس رضا احمدی').exists())
        for who in (self.clerk, self.engineer, self.dehyari):
            self.assertEqual(client_for(who).get(reverse('main:permit_experts')).status_code, 200)
        self.assertEqual(client_for(self.citizen).get(reverse('main:permit_experts')).status_code, 404)

    def test_the_list_is_the_villages_own_and_an_expert_can_be_set_aside(self):
        other = JudicialExpert.objects.create(city_village='روستای دیگر', name='مهندس دیگر')
        client_for(self.dehyari).post(reverse('main:permit_expert_toggle', args=[other.pk]), {'active': '0'})
        other.refresh_from_db()
        self.assertTrue(other.active)
        client_for(self.dehyari).post(reverse('main:permit_expert_toggle', args=[self.expert.pk]), {'active': '0'})
        self.expert.refresh_from_db()
        self.assertFalse(self.expert.active)
        self.introduce()
        self.assertEqual(self.reload().expert_state, '')                           # a set-aside expert cannot be chosen

    def test_the_names_show_in_the_staff_panels_form(self):
        for who in (self.clerk, self.engineer, self.dehyari):
            page = client_for(who).get(self.url('permit_commit')).content.decode()
            self.assertIn('مهندس حسین مالکی', page, who.profile.role)


class Introduction(Step5):
    def test_each_of_the_three_staff_introduces_the_owner(self):
        for who in (self.clerk, self.engineer, self.dehyari):
            self.permit.expert_state = ''
            self.permit.save()
            self.introduce(who)
            self.assertEqual(self.reload().expert_state, 'introduced', who.profile.role)
        self.assertEqual(self.permit.commit['expert']['name'], 'مهندس حسین مالکی')
        self.assertTrue(Notification.objects.filter(user=self.citizen, title='معرفی به کارشناس دادگستری').exists())

    def test_the_owner_and_outsiders_cannot_introduce(self):
        for who in (self.citizen, self.accountant, self.stranger_clerk, self.neighbour):
            self.introduce(who)
            self.assertEqual(self.reload().expert_state, '', who.profile.role)

    def test_the_letter_is_filled_from_the_file(self):
        self.introduce()
        payload = permit_commit.letter_payload(self.reload(), self.dehyari)
        self.assertEqual(payload['owner'], 'علی رضایی')
        self.assertEqual(payload['expert'], 'مهندس حسین مالکی')
        self.assertEqual(payload['address'], self.permit.address)
        self.assertTrue(payload['signer'])
        self.assertEqual(permit_commit.letter_payload(self.permit, self.clerk)['signer'], '')   # only the dehyari signs


class Neighbours(Step5):
    def test_the_form_starts_with_the_east_and_west_sides_and_no_more_than_three(self):
        rows = permit_commit.neighbours_default(self.permit)
        self.assertEqual(len(rows), 3)
        self.assertEqual([r['side'] for r in rows][:2], ['east', 'west'])

    def test_plots_touching_the_owner_on_the_map_fill_name_id_and_phone(self):
        village = permit_commit.permit_step2._village(self.permit)
        vm = VillageMap.objects.create(name=village)
        mine = MapParcel.objects.create(village_map=vm, uid='a', number='1', area_m2=100, geometry=GEOM)
        east = MapParcel.objects.create(village_map=vm, uid='b', number='2', area_m2=100, geometry=GEOM)
        ParcelArchive.objects.create(parcel=east, owner_name='اسماعیل صبری', owner_national_id='0652723986', owner_phone='09151234567')
        self.permit.parcel = mine
        self.permit.save()
        from unittest import mock
        with mock.patch.object(plotmap, 'neighbours', return_value={'east': [east.pk], 'west': [], 'north': [], 'south': []}):
            rows = permit_commit.neighbours_default(self.permit)
        self.assertEqual((rows[0]['side'], rows[0]['name'], rows[0]['national_id'], rows[0]['phone']), ('east', 'اسماعیل صبری', '0652723986', '09151234567'))
        self.assertIn('قطعه 2', rows[0]['address'])

    def test_the_owner_edits_and_saves_the_neighbours(self):
        post = {'n0_side': 'east', 'n0_name': 'اسماعیل صبری', 'n0_father': 'حاجی', 'n0_national_id': '۰۶۵۲۷۲۳۹۸۶', 'n0_phone': '۰۹۱۵۱۲۳۴۵۶۷', 'n1_side': 'bogus'}
        client_for(self.citizen).post(self.url('permit_consent_save'), post)
        rows = permit_commit.consent_data(self.reload())['neighbours']
        self.assertEqual((rows[0]['name'], rows[0]['national_id'], rows[0]['phone']), ('اسماعیل صبری', '0652723986', '09151234567'))
        self.assertEqual(rows[1]['side'], '')
        client_for(self.neighbour).post(self.url('permit_consent_save'), {'n0_name': 'x'})
        self.assertEqual(permit_commit.consent_data(self.reload())['neighbours'][0]['name'], 'اسماعیل صبری')

    def test_the_signed_form_needs_the_scan_and_the_tick(self):
        self.consent(signed='')
        self.assertEqual(self.reload().consent_state, '')
        self.consent(scan='')
        self.assertEqual(self.reload().consent_state, '')
        self.consent()
        self.assertEqual(self.reload().consent_state, 'uploaded')
        self.assertTrue(PermitDocument.objects.filter(file=self.permit, kind='consent_form').exists())

    def test_each_of_the_three_staff_confirms_or_sends_it_back(self):
        for who in (self.clerk, self.engineer, self.dehyari):
            self.permit.consent_state = 'uploaded'
            self.permit.save()
            client_for(who).post(reverse('main:permit_commit_verify', args=[self.permit.pk, 'consent']), {'confirm': 'on'})
            self.assertEqual(self.reload().consent_state, 'verified', who.profile.role)
        self.permit.consent_state = 'uploaded'
        self.permit.save()
        client_for(self.clerk).post(reverse('main:permit_commit_return', args=[self.permit.pk, 'consent']), {'notes': ''})
        self.assertEqual(self.reload().consent_state, 'uploaded')
        client_for(self.clerk).post(reverse('main:permit_commit_return', args=[self.permit.pk, 'consent']), {'notes': 'امضای ضلع غرب نیست'})
        self.assertEqual(self.reload().consent_state, 'returned')
        self.consent()
        self.assertEqual(self.reload().consent_state, 'uploaded')

    def test_outsiders_cannot_confirm(self):
        self.permit.consent_state = 'uploaded'
        self.permit.save()
        for who in (self.citizen, self.accountant, self.stranger_clerk):
            client_for(who).post(reverse('main:permit_commit_verify', args=[self.permit.pk, 'consent']), {'confirm': 'on'})
            self.assertEqual(self.reload().consent_state, 'uploaded', who.profile.role)


class Undertaking(Step5):
    def test_the_draft_is_typed_from_the_file(self):
        text = permit_commit.deed_default(self.permit)
        self.assertIn('علی رضایی', text)
        self.assertIn('شمالاً بطول', text)
        self.assertIn('مقاوم‌سازی', text)

    def test_an_edited_text_is_kept_and_a_stub_is_refused(self):
        body = ' '.join(['متن تعهد'] * 40)
        client_for(self.citizen).post(self.url('permit_deed_save'), {'text': body})
        self.assertEqual(permit_commit.deed_data(self.reload())['text'], body)
        client_for(self.citizen).post(self.url('permit_deed_save'), {'text': 'کوتاه'})
        self.assertEqual(permit_commit.deed_data(self.reload())['text'], body)

    def test_the_scan_number_date_office_and_the_delivery_tick_are_all_needed(self):
        for bad in ({'deed_no': ''}, {'office': ''}, {'deed_date': soon()}, {'deed_date': 'x'}, {'delivered': ''}, {'scan': ''}):
            self.deliver(**bad)
            self.assertEqual(self.reload().deed_state, '', bad)
        self.deliver()
        self.assertEqual(self.reload().deed_state, 'uploaded')
        self.assertEqual(self.permit.commit['deed']['number'], '4481')
        self.assertTrue(Notification.objects.filter(user=self.clerk, title='تعهد محضری').exists())

    def test_each_of_the_three_staff_confirms_the_deed_after_the_original_reached_the_dehyari(self):
        for who in (self.clerk, self.engineer, self.dehyari):
            self.permit.deed_state = 'uploaded'
            self.permit.save()
            client_for(who).post(reverse('main:permit_commit_verify', args=[self.permit.pk, 'deed']), {})
            self.assertEqual(self.reload().deed_state, 'uploaded')
            client_for(who).post(reverse('main:permit_commit_verify', args=[self.permit.pk, 'deed']), {'confirm': 'on'})
            self.assertEqual(self.reload().deed_state, 'verified', who.profile.role)


class Ending(Step5):
    def ready(self):
        self.introduce()
        self.consent()
        self.deliver()
        for part in ('consent', 'deed'):
            client_for(self.engineer).post(reverse('main:permit_commit_verify', args=[self.permit.pk, part]), {'confirm': 'on'})

    def test_nothing_ends_until_all_three_parts_are_done(self):
        self.act(self.dehyari, 'permit_step5_finish', confirm='on')
        self.assertEqual(self.reload().stage_no, 5)
        self.introduce()
        self.consent()
        self.act(self.dehyari, 'permit_step5_finish', confirm='on')
        self.assertEqual(self.reload().stage_no, 5)
        self.assertEqual(len(permit_commit.blocking(self.permit)), 2)

    def test_each_of_the_three_staff_ends_the_step_and_the_tick_is_needed(self):
        self.ready()
        self.act(self.clerk, 'permit_step5_finish')
        self.assertEqual(self.reload().stage_no, 5)
        for who in (self.clerk, self.engineer, self.dehyari):
            self.permit.stage_no = 5
            self.permit.save()
            self.act(who, 'permit_step5_finish', confirm='on')
            self.assertEqual(self.reload().stage_no, 6, who.profile.role)
        self.assertTrue(Notification.objects.filter(user=self.citizen, title='مرحله‌ی ۵ تایید شد').exists())
        self.assertEqual(self.permit.status_text, 'منتظر دو جوابیه‌ی کارشناس دادگستری (از متقاضی)')

    def test_outsiders_cannot_end_it(self):
        self.ready()
        for who in (self.citizen, self.accountant, self.stranger_clerk, self.neighbour):
            self.act(who, 'permit_step5_finish', confirm='on')
            self.assertEqual(self.reload().stage_no, 5, who.profile.role)

    def test_status_follows_the_step(self):
        self.assertIn('منتظر معرفی به کارشناس دادگستری', self.permit.status_text)
        self.introduce()
        self.assertTrue(self.reload().status_text.startswith('منتظر تعهدنامه‌ی رضایت همسایگان'))
        self.consent()
        self.deliver()
        self.assertEqual(self.reload().status_text, 'مدارک متقاضی منتظر تایید')
        self.assertTrue(self.permit.needs_staff)
        for part in ('consent', 'deed'):
            client_for(self.engineer).post(reverse('main:permit_commit_verify', args=[self.permit.pk, part]), {'confirm': 'on'})
        self.assertIn('منتظر تایید نهایی', self.reload().status_text)

    def test_the_page_opens_for_the_owner_and_the_three_staff_only(self):
        for who in (self.citizen, self.clerk, self.engineer, self.dehyari):
            self.assertEqual(client_for(who).get(self.url('permit_commit')).status_code, 200, who.profile.role)
        for who in (self.neighbour, self.stranger_clerk, self.accountant):
            self.assertEqual(client_for(who).get(self.url('permit_commit')).status_code, 404, who.profile.role)


class MapNeighbours(Step5):
    def test_the_real_map_names_the_plots_touching_each_side_and_never_the_plot_itself(self):
        parcel = plot()
        found = plotmap.neighbours(VillageMap.objects.get(slug=SLUG), parcel.pk)
        self.assertEqual(set(found), {'north', 'east', 'south', 'west'})
        ids = [i for ids in found.values() for i in ids]
        self.assertTrue(ids)
        self.assertNotIn(parcel.pk, ids)
        self.assertEqual(plotmap.neighbours(VillageMap.objects.get(slug=SLUG), 0), {})
