"""Construction without a permit, step 8: the owner asks for the Bonyad's visit list, the technical expert confirms the visit (the owner sees the package and
gets an SMS), the owner uploads the Bonyad's letter, any of the three staff confirms it and ends the step."""
from unittest import mock

from django.urls import reverse

from main.models import Notification, PermitDocument
from main.tests.helpers import client_for
from main.tests.test_permit_dues import Step7
from main.tests.test_permit_files import PNG, upload


class Step8(Step7):
    def setUp(self):
        super().setUp()
        self.issue()
        self.pay(self.accountant, amount=str(self.reload().dues_total), slip='1')
        self.act(self.dehyari, 'permit_step7_finish', confirm='on')
        self.assertEqual(self.reload().stage_no, 8)

    def ask(self, who=None, **over):
        post = {'confirm': 'on', 'note': ''}
        post.update(over)
        return client_for(who or self.citizen).post(self.url('permit_bonyad_request'), post, follow=True)

    def release(self, who=None, **over):
        post = {'date': '1405/01/01', 'confirm': 'on'}
        post.update(over)
        return client_for(who or self.engineer).post(self.url('permit_bonyad_release'), post, follow=True)

    def letter(self, **over):
        post = {'letter': upload('b.png', PNG), 'letter_no': '55/9', 'letter_date': '1405/01/05'}
        post.update(over)
        return client_for(self.citizen).post(self.url('permit_bonyad_upload'), post, follow=True)


class Request(Step8):
    def test_the_status_waits_for_the_owner_and_the_stage_is_named(self):
        self.assertEqual(self.permit.status_text, 'منتظر درخواست قرار گرفتن در لیست بازدید بنیاد (از متقاضی)')
        self.assertEqual(self.permit.stage_title, 'لیست بازدید بنیاد و نامه‌ی بنیاد')

    def test_only_the_owner_asks_and_the_tick_is_needed(self):
        self.ask(confirm='')
        self.assertEqual(self.reload().bonyad_list_state, '')
        for who in (self.clerk, self.engineer, self.dehyari, self.neighbour):
            self.ask(who)
            self.assertEqual(self.reload().bonyad_list_state, '', who.profile.role)
        self.ask()
        self.assertEqual(self.reload().bonyad_list_state, 'requested')
        self.assertTrue(self.permit.needs_staff)
        self.assertTrue(Notification.objects.filter(user=self.engineer, title='لیست بازدید بنیاد').exists())

    def test_the_package_and_the_letter_are_hidden_from_the_owner_until_the_visit(self):
        self.ask()
        page = client_for(self.citizen).get(self.url('permit_bonyad')).content.decode()
        self.assertNotIn('id="bd-pack"', page)
        self.assertEqual(client_for(self.citizen).get(self.url('permit_bonyad_letter')).status_code, 404)
        self.assertEqual(client_for(self.engineer).get(self.url('permit_bonyad_letter')).status_code, 200)


class Release(Step8):
    def setUp(self):
        super().setUp()
        self.ask()

    def test_the_technical_expert_or_the_dehyari_confirm_and_the_owner_gets_an_sms(self):
        for who in (self.clerk, self.accountant, self.citizen, self.neighbour):
            self.release(who)
            self.assertEqual(self.reload().bonyad_list_state, 'requested', who.profile.role)
        for bad in ({'date': ''}, {'date': '1499/01/01'}, {'confirm': ''}):
            self.release(**bad)
            self.assertEqual(self.reload().bonyad_list_state, 'requested', bad)
        with mock.patch('main.sms.send_sms', return_value=(True, 'ok')) as sent:
            self.release()
        self.assertEqual(self.reload().bonyad_list_state, 'released')
        sent.assert_called_once()
        self.assertEqual(sent.call_args[0][0], self.permit.people.first().phone)
        self.assertTrue(self.permit.bonyad_list['visit']['sms'])
        self.assertTrue(Notification.objects.filter(user=self.citizen, title='بازدید بنیاد انجام شد').exists())

    def test_a_failing_gateway_does_not_stop_the_flow(self):
        with mock.patch('main.sms.send_sms', return_value=(False, 'x')):
            self.release(self.dehyari)
        self.assertEqual(self.reload().bonyad_list_state, 'released')
        self.assertFalse(self.permit.bonyad_list['visit']['sms'])

    def test_the_package_shows_the_sketch_the_reply_the_report_the_payments_and_the_letter(self):
        PermitDocument.objects.create(file=self.permit, kind='shamim', document=upload('s.dxf', b'0\nEOF\n'), original_name='s.dxf', size=5, uploaded_by=self.engineer)
        PermitDocument.objects.create(file=self.permit, kind='expert_table', document=upload('t.png', PNG), original_name='t.png', size=5, uploaded_by=self.citizen)
        with mock.patch('main.sms.send_sms', return_value=(True, 'ok')):
            self.release()
        page = client_for(self.citizen).get(self.url('permit_bonyad')).content.decode()
        for part in ('id="bd-pack"', 's.dxf', 'جدول ۲', 'گزارش کارشناس فنی', 'فیش', 'نامه‌ی دهیاری به بنیاد'):
            self.assertIn(part, page, part)
        for name in ('permit_bonyad_letter', 'permit_dues_sheet', 'permit_report'):
            self.assertEqual(client_for(self.citizen).get(self.url(name)).status_code, 200, name)


class Letter(Step8):
    def setUp(self):
        super().setUp()
        self.ask()
        with mock.patch('main.sms.send_sms', return_value=(True, 'ok')):
            self.release()

    def test_the_letter_needs_the_scan_number_and_a_past_date_and_only_the_owner_sends_it(self):
        for bad in ({'letter': ''}, {'letter_no': ''}, {'letter_date': '1499/01/01'}, {'letter_date': 'x'}):
            self.letter(**bad)
            self.assertEqual(self.reload().bonyad_list_state, 'released', bad)
        client_for(self.clerk).post(self.url('permit_bonyad_upload'), {'letter': upload('b.png', PNG), 'letter_no': '1', 'letter_date': '1405/01/05'})
        self.assertEqual(self.reload().bonyad_list_state, 'released')
        self.letter()
        self.assertEqual(self.reload().bonyad_list_state, 'uploaded')
        self.assertTrue(PermitDocument.objects.filter(file=self.permit, kind='bonyad_letter').exists())
        self.assertTrue(self.permit.needs_staff)

    def test_each_of_the_three_staff_confirms_or_sends_back_and_then_ends_the_step(self):
        self.letter()
        self.act(self.clerk, 'permit_bonyad_return', notes='')
        self.assertEqual(self.reload().bonyad_list_state, 'uploaded')
        self.act(self.clerk, 'permit_bonyad_return', notes='ناخوانا')
        self.assertEqual(self.reload().bonyad_list_state, 'returned')
        self.letter()
        for who in (self.accountant, self.citizen, self.neighbour):
            self.act(who, 'permit_bonyad_verify', confirm='on')
            self.assertEqual(self.reload().bonyad_list_state, 'uploaded', who.profile.role)
        for who in (self.clerk, self.engineer, self.dehyari):
            self.permit.bonyad_list_state, self.permit.stage_no = 'uploaded', 8
            self.permit.save()
            self.act(who, 'permit_bonyad_verify')
            self.assertEqual(self.reload().bonyad_list_state, 'uploaded')
            self.act(who, 'permit_bonyad_verify', confirm='on')
            self.assertEqual(self.reload().bonyad_list_state, 'verified', who.profile.role)
            self.act(who, 'permit_step8_finish', confirm='on')
            self.assertEqual(self.reload().stage_no, 9, who.profile.role)

    def test_nothing_ends_before_the_letter_is_confirmed(self):
        self.act(self.dehyari, 'permit_step8_finish', confirm='on')
        self.letter()
        self.act(self.dehyari, 'permit_step8_finish', confirm='on')
        self.assertEqual(self.reload().stage_no, 8)

    def test_the_page_opens_for_the_owner_and_the_village_staff_only(self):
        for who in (self.citizen, self.clerk, self.engineer, self.dehyari):
            self.assertEqual(client_for(who).get(self.url('permit_bonyad')).status_code, 200, who.profile.role)
        for who in (self.neighbour, self.stranger_clerk):
            self.assertEqual(client_for(who).get(self.url('permit_bonyad')).status_code, 404, who.profile.role)
        self.assertEqual(reverse('main:permit_bonyad', args=[self.permit.pk]), self.url('permit_bonyad'))
