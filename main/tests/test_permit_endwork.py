"""Building permit, the last step: the end-of-work request and the certificate."""
from main.models import Notification
from main.office import permit_endwork, permit_services, permits
from main.tests.helpers import client_for
from main.tests.test_permit_supervision import Supervised
from main.office import permit_supervision


class AtTheEnd(Supervised):
    """Forms 8-13 confirmed: the file is at stage 9."""

    def setUp(self):
        super().setUp()
        for n in permit_supervision.NUMBERS:
            self.run_form(n)
        self.reload()
        self.assertEqual(self.permit.stage_no, 9)

    def ask_end(self, who=None):
        return client_for(who or self.citizen).post(self.url('endwork_request'))

    def data(self, **change):
        data = {f'f_{k}': v for k, v in permit_endwork.payload(self.reload()).items()}
        data.update({'f_number': '19/3436', 'f_date': '1405/08/25', **{f'f_{k}': v for k, v in change.items()}})
        return data

    def answer(self, who=None, **change):
        return client_for(who or self.clerk).post(self.url('endwork_approve'), self.data(**change))

    def state(self):
        return self.reload().endwork_state


class Requesting(AtTheEnd):
    def test_the_owner_asks_and_the_staff_are_told(self):
        self.assertEqual(self.permit.status_text, 'نظارت کامل شد؛ درخواست گواهی پایان کار از متقاضی')
        self.ask_end()
        self.assertEqual(self.state(), 'requested')
        self.assertTrue(self.permit.endwork['req_no'])
        self.assertTrue(Notification.objects.filter(user=self.clerk, title='درخواست گواهی پایان کار').exists())
        self.assertTrue(self.permit.needs_staff)
        self.assertEqual(self.permit.status_text, 'درخواست پایان کار منتظر دهیاری')

    def test_strangers_cannot_ask_and_not_before_the_supervision_ends(self):
        for who in (self.neighbour, self.stranger):
            self.ask_end(who)
        self.assertEqual(self.state(), '')
        self.permit.stage_no = 7
        self.permit.save()
        self.ask_end()
        self.assertEqual(self.state(), '')

    def test_one_request_at_a_time(self):
        self.ask_end()
        before = self.reload().endwork['req_no']
        self.ask_end()
        self.assertEqual(self.reload().endwork['req_no'], before)


class Answering(AtTheEnd):
    def setUp(self):
        super().setUp()
        self.ask_end()

    def test_each_of_the_three_staff_may_approve(self):
        for who in (self.citizen, self.neighbour, self.stranger, self.officer, self.inspector):
            self.answer(who)
        self.assertEqual(self.state(), 'requested')
        self.answer(self.expert)
        permit = self.reload()
        self.assertEqual((permit.endwork_state, permit.endwork['f']['number'], permit.endwork['f']['date']), ('approved', '19/3436', '1405/08/25'))
        self.assertTrue(Notification.objects.filter(user=self.citizen, title='گواهی پایان کار آماده است').exists())

    def test_a_number_and_date_are_needed(self):
        self.answer(number='')
        self.answer(date='bad')
        self.assertEqual(self.state(), 'requested')

    def test_the_certificate_is_filled_from_the_file(self):
        data = permit_endwork.payload(self.reload())
        self.assertEqual((data['owner'], data['permit_no']), ('علی رضایی', '18/1286'))
        self.assertEqual((data['sup_name'], data['use']), ('سعید احمدی', 'مسکونی'))
        self.assertEqual(data['form_no'], permit_supervision.forms(self.permit)[13]['f']['number'])
        self.assertEqual((data['fl_ground_count'], data['fl_ground_area'], data['total_area']), ('1', '135', 135))
        self.assertEqual(data['sd_north_after'], '10')

    def test_rejecting_needs_a_reason_and_allows_a_new_request(self):
        client_for(self.expert).post(self.url('endwork_reject'), {'reason': ''})
        self.assertEqual(self.state(), 'requested')
        client_for(self.dehyari).post(self.url('endwork_reject'), {'reason': 'مغایرت در متراژ'})
        self.assertEqual(self.state(), 'rejected')
        self.assertTrue(Notification.objects.filter(user=self.citizen, title='درخواست پایان کار رد شد').exists())
        self.ask_end()
        self.assertEqual(self.state(), 'requested')

    def test_the_handover_needs_the_tick_and_ends_the_file(self):
        client_for(self.clerk).post(self.url('endwork_issue'), {'signed': 'on'})
        self.assertEqual(self.state(), 'requested')
        self.answer()
        client_for(self.clerk).post(self.url('endwork_issue'), {})
        client_for(self.citizen).post(self.url('endwork_issue'), {'signed': 'on'})
        self.assertEqual(self.state(), 'approved')
        client_for(self.dehyari).post(self.url('endwork_issue'), {'signed': 'on'})
        permit = self.reload()
        self.assertEqual(permit.endwork_state, 'issued')
        self.assertEqual(permit.status_text, 'گواهی پایان کار صادر شد')
        self.assertTrue(Notification.objects.filter(user=self.citizen, title='گواهی پایان ساخت صادر شد').exists())
        self.assertFalse(permit.needs_staff)
        self.assertEqual([s['state'] for s in permits.tracker(permit) if s['no'] == 9], ['done'])

    def test_the_end_of_work_number_reaches_the_electricity_letter(self):
        self.answer()
        client_for(self.clerk).post(self.url('endwork_issue'), {'signed': 'on'})
        data = permit_services.defaults(self.reload(), 'elec_endwork')
        self.assertEqual((data['endwork_no'], data['endwork_date']), ('19/3436', '1405/08/25'))

    def test_the_pages(self):
        staff = client_for(self.clerk).get(self.url('endwork')).content.decode()
        self.assertIn('name="f_number"', staff)
        self.assertIn('تایید درخواست', staff)
        owner = client_for(self.citizen).get(self.url('endwork')).content.decode()
        self.assertIn('امضا و تحویل دستی', owner)
        self.assertNotIn('تایید درخواست (شماره‌دار', owner)
        self.assertEqual(client_for(self.neighbour).get(self.url('endwork')).status_code, 404)
        self.permit.stage_no = 7
        self.permit.save()
        self.assertEqual(client_for(self.citizen).get(self.url('endwork')).status_code, 302)
