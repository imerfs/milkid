"""Construction without a permit, steps 10 and 11: form 16 signed by the governor is added to the file, then the file summary is sent to the commission; any of
the three staff confirms each step."""
from main.models import Notification, PermitDocument
from main.office import permit_form16
from main.tests.helpers import client_for
from main.tests.test_permit_files import PNG, upload
from main.tests.test_permit_pack import Step9


class Step10(Step9):
    def setUp(self):
        super().setUp()
        self.permit.pack_state = 'verified'
        self.permit.save()
        self.act(self.dehyari, 'permit_step9_finish', confirm='on')
        self.assertEqual(self.reload().stage_no, 10)

    def post16(self, **over):
        post = {'owner': 'محمدجواد فگار', 'father': 'موسی', 'use': 'residential', 'built': 'built', 'requests': ['max_fine'], 'served': ['owner'],
                'date': '1405/07/18', 'number': '19/3491', 's_number': '19/3492', 's_area': '136.28', 's_expert': 'حسین مالکی', 's_strength': 'has'}
        post.update(over)
        return post

    def file(self, who=None, **over):
        return client_for(who or self.dehyari).post(self.url('permit_form16_file'), self.post16(**over), follow=True)

    def post_summary(self, who=None, **over):
        return client_for(who or self.dehyari).post(self.url('permit_summary_send'), self.post16(**over), follow=True)


class Step11(Step10):
    def setUp(self):
        super().setUp()
        self.file(scan=upload('f16.png', PNG))
        self.act(self.dehyari, 'permit_step10_finish', confirm='on')
        self.assertEqual(self.reload().stage_no, 11)


class Defaults(Step10):
    def test_the_status_and_stage_name(self):
        self.assertEqual(self.permit.status_text, 'منتظر فرم ۱۶ و امضای بخشدار (دهیاری)')
        self.assertEqual(self.permit.stage_title, 'فرم ۱۶ و امضای بخشدار')
        self.assertTrue(self.permit.needs_staff)

    def test_the_forms_are_filled_from_the_file(self):
        self.permit.commit = {**self.permit.commit, 'reply': {'expert': 'حسین مالکی', 'letter_no': '19/3463', 'letter_date': '1405/07/05', 'strength': 'lacks'}}
        self.permit.save()
        v = permit_form16.data(self.permit, self.dehyari)
        self.assertEqual(v['owner'], 'علی رضایی')
        self.assertEqual(v['use'], 'residential')
        self.assertEqual(v['built'], 'built')
        self.assertEqual(v['notice_no'], '2/4493')
        self.assertEqual(v['served'], ['owner'])
        self.assertEqual(v['summary']['expert_no'], '19/3463')
        self.assertEqual(v['summary']['strength'], 'lacks')
        self.assertTrue(float(v['summary']['area']) > 0)

    def test_the_page_opens_for_the_three_staff_only(self):
        for who in (self.clerk, self.engineer, self.dehyari):
            self.assertEqual(client_for(who).get(self.url('permit_form16')).status_code, 200, who.profile.role)
        for who in (self.citizen, self.neighbour, self.stranger_clerk, self.accountant):
            self.assertEqual(client_for(who).get(self.url('permit_form16')).status_code, 404, who.profile.role)


class Form16(Step10):
    def test_a_draft_keeps_the_edited_values_and_unknown_choices_are_dropped(self):
        client_for(self.clerk).post(self.url('permit_form16_save'), self.post16(use='nonsense', requests=['demolish', 'bogus'], s_widening='on'))
        v = permit_form16.data(self.reload())
        self.assertEqual((v['use'], v['requests'], v['number']), ('residential', ['demolish'], '19/3491'))
        self.assertTrue(v['summary']['widening'])
        self.assertEqual(self.permit.form16_state, '')

    def test_an_empty_owner_is_refused(self):
        self.file(owner='', scan=upload('f16.png', PNG))
        self.assertEqual(self.reload().form16_state, '')

    def test_the_governors_signed_scan_is_required(self):
        self.file()
        self.assertEqual(self.reload().form16_state, '')

    def test_each_of_the_three_staff_adds_the_signed_form_and_the_scan_is_kept(self):
        for who in (self.citizen, self.neighbour, self.accountant):
            self.file(who, scan=upload('f16.png', PNG))
            self.assertEqual(self.reload().form16_state, '', who.profile.role)
        for who in (self.clerk, self.engineer, self.dehyari):
            self.permit.form16_state = ''
            self.permit.save()
            self.file(who, scan=upload('f16.png', PNG))
            self.assertEqual(self.reload().form16_state, 'filed', who.profile.role)
        self.assertEqual(PermitDocument.objects.filter(file=self.permit, kind='form16_scan').count(), 1)
        self.assertIn('تایید نهایی', self.permit.status_text)

    def test_the_summary_cannot_be_sent_at_this_step(self):
        self.post_summary()
        self.assertEqual(self.reload().summary_state, '')

    def test_nothing_ends_before_the_signed_form_is_filed_and_the_tick_is_needed(self):
        self.act(self.dehyari, 'permit_step10_finish', confirm='on')
        self.assertEqual(self.reload().stage_no, 10)
        self.file(scan=upload('f16.png', PNG))
        self.act(self.dehyari, 'permit_step10_finish')
        self.assertEqual(self.reload().stage_no, 10)
        for who in (self.citizen, self.neighbour, self.stranger_clerk):
            self.act(who, 'permit_step10_finish', confirm='on')
            self.assertEqual(self.reload().stage_no, 10, who.profile.role)
        for who in (self.clerk, self.engineer, self.dehyari):
            self.permit.stage_no = 10
            self.permit.save()
            self.act(who, 'permit_step10_finish', confirm='on')
            self.assertEqual(self.reload().stage_no, 11, who.profile.role)
        self.assertTrue(Notification.objects.filter(user=self.citizen, title='فرم ۱۶ امضا شد').exists())


class Summary(Step11):
    def test_the_status_and_stage_name(self):
        self.assertEqual(self.permit.status_text, 'منتظر ارسال خلاصه‌ی پرونده به کمیسیون (دهیاری)')
        self.assertEqual(self.permit.stage_title, 'خلاصه‌ی پرونده و ارسال به کمیسیون')

    def test_the_letter_number_is_required_and_the_scan_is_optional(self):
        self.post_summary(s_number='')
        self.assertEqual(self.reload().summary_state, '')
        for who in (self.citizen, self.neighbour, self.accountant):
            self.post_summary(who)
            self.assertEqual(self.reload().summary_state, '', who.profile.role)
        for who in (self.clerk, self.engineer, self.dehyari):
            self.permit.summary_state = ''
            self.permit.save()
            self.post_summary(who)
            self.assertEqual(self.reload().summary_state, 'sent', who.profile.role)
        self.assertEqual(self.permit.form16['sent']['number'], '19/3492')
        self.assertIn('تایید نهایی', self.permit.status_text)

    def test_the_signed_summary_scan_is_kept(self):
        self.post_summary(scan=upload('summary.png', PNG))
        self.assertEqual(PermitDocument.objects.filter(file=self.permit, kind='summary_scan').count(), 1)

    def test_nothing_ends_before_the_summary_is_sent_and_the_tick_is_needed(self):
        self.act(self.dehyari, 'permit_step11_finish', confirm='on')
        self.assertEqual(self.reload().stage_no, 11)
        self.post_summary()
        self.act(self.dehyari, 'permit_step11_finish')
        self.assertEqual(self.reload().stage_no, 11)
        for who in (self.citizen, self.neighbour, self.stranger_clerk):
            self.act(who, 'permit_step11_finish', confirm='on')
            self.assertEqual(self.reload().stage_no, 11, who.profile.role)
        for who in (self.clerk, self.engineer, self.dehyari):
            self.permit.stage_no = 11
            self.permit.save()
            self.act(who, 'permit_step11_finish', confirm='on')
            self.assertEqual(self.reload().stage_no, 12, who.profile.role)
        self.assertTrue(Notification.objects.filter(user=self.citizen, title='پرونده‌ی شما برای کمیسیون فرستاده شد').exists())
        self.assertIn('مرحله‌ی ', self.reload().status_text)
