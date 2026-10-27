"""Building permit services: the letters for electricity, gas and water the dehyari signs."""
from main.models import Notification
from main.office import permit_services, permit_supervision
from main.tests.test_permit_supervision import Supervised
from main.tests.helpers import client_for
from main.tests.test_permit_extension import Issued


class Letters(Issued):
    def ask_letter(self, kind='elec_permit', who=None, **extra):
        data = {'kind': kind, **{f'f_{k}': v for k, v in extra.items()}}
        return client_for(who or self.citizen).post(self.url('service_request'), data)

    def letter_item(self, n=0):
        return permit_services.services(self.reload())[n]

    def approve_letter(self, sid=1, who=None, **change):
        item = self.letter_item(sid - 1)
        data = {f'f_{k}': v for k, v in permit_services.payload(self.permit, item).items()}
        data.update({'f_number': '19/2001', 'f_date': '1405/08/20', **{f'f_{k}': v for k, v in change.items()}})
        return client_for(who or self.clerk).post(self.url('service_approve', sid), data)


class Asking(Letters):
    def test_the_owner_asks_and_the_staff_are_told(self):
        self.ask_letter()
        item = self.letter_item()
        self.assertEqual((item['kind'], item['state']), ('elec_permit', 'requested'))
        self.assertTrue(Notification.objects.filter(user=self.clerk, title='درخواست نامه‌ی خدمات').exists())
        self.assertTrue(self.permit.needs_staff)

    def test_only_one_open_request_per_letter_and_only_known_kinds(self):
        self.ask_letter()
        self.ask_letter()
        self.ask_letter('nonsense')
        self.assertEqual(len(permit_services.services(self.reload())), 1)

    def test_some_letters_need_extra_figures(self):
        self.ask_letter('gas_dig')
        self.ask_letter('elec_endwork')
        self.assertFalse(permit_services.services(self.reload()))
        self.ask_letter('gas_dig', ref_no='43/210/35180', slip_no='899180', slip_date='1405/08/01')
        self.ask_letter('elec_endwork', endwork_no='325/7', endwork_date='1405/08/02')
        self.assertEqual(len(permit_services.services(self.reload())), 2)

    def test_strangers_cannot_ask_and_nothing_before_the_permit(self):
        for who in (self.neighbour, self.stranger):
            self.ask_letter(who=who)
        self.assertFalse(permit_services.services(self.reload()))
        self.permit.licence_state = ''
        self.permit.save()
        self.ask_letter()
        self.assertFalse(permit_services.services(self.reload()))

    def test_the_letter_is_filled_from_the_file(self):
        data = permit_services.defaults(self.permit, 'elec_permit')
        self.assertEqual((data['name'], data['permit_no']), ('علی رضایی', '18/1286'))
        self.assertIn('18/1286', permit_services.defaults(self.permit, 'gas_status')['basis'])
        self.assertEqual(data['village'], self.village)
        self.assertTrue(data['date'])


class Deciding(Letters):
    def setUp(self):
        super().setUp()
        self.ask_letter('gas_status')

    def test_the_staff_approve_it_with_a_number_and_the_owner_is_told(self):
        for who in (self.citizen, self.neighbour, self.stranger):
            self.approve_letter(who=who)
        self.assertEqual(self.letter_item()['state'], 'requested')
        self.approve_letter(who=self.expert)
        item = self.letter_item()
        self.assertEqual((item['state'], item['f']['number'], item['f']['date']), ('approved', '19/2001', '1405/08/20'))
        self.assertTrue(Notification.objects.filter(user=self.citizen, title='نامه‌ی شما آماده است').exists())

    def test_a_number_and_a_real_date_are_needed(self):
        self.approve_letter(number='')
        self.approve_letter(date='bad')
        self.assertEqual(self.letter_item()['state'], 'requested')

    def test_the_printing_buttons_appear_only_after_approval(self):
        before = client_for(self.citizen).get(self.url('services')).content.decode()
        self.assertNotIn('id="pfv-print"\n', before.replace('><', '>\n<').replace('hidden', ''))
        self.assertIn('پس از تایید دهیاری', before)
        self.approve_letter()
        after = client_for(self.citizen).get(self.url('services')).content.decode()
        self.assertIn('نامه را چاپ کنید', after)

    def test_rejecting_needs_a_reason(self):
        client_for(self.clerk).post(self.url('service_reject', 1), {'reason': ''})
        self.assertEqual(self.letter_item()['state'], 'requested')
        client_for(self.clerk).post(self.url('service_reject', 1), {'reason': 'مدارک ناقص'})
        self.assertEqual((self.letter_item()['state'], self.letter_item()['reason']), ('rejected', 'مدارک ناقص'))
        self.assertTrue(Notification.objects.filter(user=self.citizen, title='درخواست نامه رد شد').exists())

    def test_the_owner_may_cancel_only_while_waiting(self):
        client_for(self.neighbour).post(self.url('service_cancel', 1))
        client_for(self.clerk).post(self.url('service_cancel', 1))
        self.assertEqual(self.letter_item()['state'], 'requested')
        client_for(self.citizen).post(self.url('service_cancel', 1))
        self.assertEqual(self.letter_item()['state'], 'cancelled')

    def test_the_handover_is_recorded_after_approval_with_the_tick(self):
        client_for(self.clerk).post(self.url('service_issue', 1), {'signed': 'on'})
        self.assertEqual(self.letter_item()['state'], 'requested')
        self.approve_letter()
        client_for(self.clerk).post(self.url('service_issue', 1), {})
        self.assertEqual(self.letter_item()['state'], 'approved')
        client_for(self.citizen).post(self.url('service_issue', 1), {'signed': 'on'})
        self.assertEqual(self.letter_item()['state'], 'approved')
        client_for(self.expert).post(self.url('service_issue', 1), {'signed': 'on'})
        self.assertEqual(self.letter_item()['state'], 'issued')
        self.assertTrue(Notification.objects.filter(user=self.citizen, title='نامه‌ی خدمات تحویل شد').exists())
        self.assertFalse(self.reload().needs_staff)

    def test_the_pages(self):
        staff = client_for(self.clerk).get(self.url('services') + '?s=1').content.decode()
        self.assertIn('name="f_number"', staff)
        self.assertIn('تایید نامه', staff)
        owner = client_for(self.citizen).get(self.url('services')).content.decode()
        self.assertIn('امضا و تحویل دستی', owner)
        self.assertNotIn('تایید نامه (شماره‌دار', owner)
        self.assertEqual(client_for(self.neighbour).get(self.url('services')).status_code, 404)


class Clearances(Supervised):
    """The non-violation certificates of the supervision stages."""

    def ask_nov(self, kind='nov_1', who=None):
        return client_for(who or self.citizen).post(self.url('service_request'), {'kind': kind})

    def test_a_certificate_waits_for_its_supervision_form(self):
        self.ask_nov()
        self.assertFalse(permit_services.services(self.reload()))
        self.run_form(8)
        self.run_form(9)
        self.ask_nov('nov_2')
        self.assertFalse(permit_services.services(self.reload()))
        self.ask_nov('nov_1')
        item = permit_services.services(self.reload())[0]
        self.assertEqual((item['kind'], item['state']), ('nov_1', 'requested'))
        self.assertTrue(item['f']['req_no'])

    def test_it_is_filled_from_the_file_and_approved_like_any_letter(self):
        self.run_form(8)
        self.run_form(9)
        self.ask_nov()
        data = permit_services.payload(self.reload(), permit_services.services(self.permit)[0])
        self.assertEqual((data['permit_no'], data['sup_name'], data['stage_text'][:3]), ('18/1286', 'سعید احمدی', 'اول'))
        self.assertEqual(data['report_date'], permit_supervision.forms(self.permit)[9]['f']['date'])
        self.assertTrue(data['tech_name'] is not None)
        post = {f'f_{k}': v for k, v in data.items()}
        post.update({'f_number': '19/3000', 'f_date': '1405/08/21'})
        client_for(self.clerk).post(self.url('service_approve', 1), post)
        self.assertEqual(permit_services.services(self.reload())[0]['state'], 'approved')
        client_for(self.expert).post(self.url('service_issue', 1), {'signed': 'on'})
        self.assertEqual(permit_services.services(self.reload())[0]['state'], 'issued')
