"""Construction without a permit, step 6: the judiciary expert's two replies uploaded by the owner, confirmed by any of the three staff."""
from django.urls import reverse

from main.models import Notification, PermitDocument
from main.office import permit_reply
from main.tests.helpers import client_for
from main.tests.test_permit_commit import Step5
from main.tests.test_permit_files import PNG, upload


class Step6(Step5):
    def setUp(self):
        super().setUp()
        self.introduce()
        self.reload()
        self.permit.consent_state, self.permit.deed_state = 'verified', 'verified'
        self.permit.save()
        self.act(self.dehyari, 'permit_step5_finish', confirm='on')
        self.assertEqual(self.reload().stage_no, 6)

    def reply(self, who=None, **over):
        post = {'letter': upload('l.png', PNG), 'table': upload('t.png', PNG), 'expert': 'حسین مالکی', 'letter_no': '19/3463', 'letter_date': '1405/07/05',
                'strength': 'lacks', 'delivered': 'on'}
        post.update(over)
        return client_for(who or self.citizen).post(self.url('permit_reply_upload'), post, follow=True)


class Upload(Step6):
    def test_the_page_shows_the_expert_chosen_in_step_5(self):
        page = client_for(self.citizen).get(self.url('permit_reply')).content.decode()
        self.assertIn('مهندس حسین مالکی', page)
        self.assertEqual(self.permit.status_text, 'منتظر دو جوابیه‌ی کارشناس دادگستری (از متقاضی)')

    def test_both_scans_the_number_date_verdict_and_the_delivery_tick_are_needed(self):
        for bad in ({'letter': ''}, {'table': ''}, {'letter_no': ''}, {'letter_date': '1499/01/01'}, {'letter_date': 'x'}, {'strength': ''}, {'delivered': ''}):
            self.reply(**bad)
            self.assertEqual(self.reload().reply_state, '', bad)
        self.reply()
        self.assertEqual(self.reload().reply_state, 'uploaded')
        self.assertEqual(self.permit.commit['reply']['strength'], 'lacks')
        self.assertEqual(PermitDocument.objects.filter(file=self.permit, kind__in=('expert_letter', 'expert_table')).count(), 2)
        self.assertTrue(Notification.objects.filter(user=self.clerk, title='جوابیه‌های کارشناس دادگستری').exists())
        self.assertTrue(self.permit.needs_staff)

    def test_only_the_owner_uploads(self):
        for who in (self.clerk, self.dehyari, self.accountant, self.neighbour):
            self.reply(who)
            self.assertEqual(self.reload().reply_state, '', who.profile.role)


class Decide(Step6):
    def test_each_of_the_three_staff_confirms_with_the_tick_and_then_ends_the_step(self):
        for who in (self.clerk, self.engineer, self.dehyari):
            self.permit.reply_state, self.permit.stage_no = 'uploaded', 6
            self.permit.save()
            self.act(who, 'permit_reply_verify')
            self.assertEqual(self.reload().reply_state, 'uploaded')
            self.act(who, 'permit_reply_verify', confirm='on')
            self.assertEqual(self.reload().reply_state, 'verified', who.profile.role)
            self.act(who, 'permit_step6_finish', confirm='on')
            self.assertEqual(self.reload().stage_no, 7, who.profile.role)
        self.assertIn('مرحله‌ی ۶ تایید شد', self.permit.status_text)

    def test_the_step_does_not_end_before_the_replies_are_confirmed(self):
        self.reply()
        self.act(self.dehyari, 'permit_step6_finish', confirm='on')
        self.assertEqual(self.reload().stage_no, 6)

    def test_a_reason_is_needed_to_send_back_and_the_owner_can_send_again(self):
        self.reply()
        self.act(self.clerk, 'permit_reply_return', notes='')
        self.assertEqual(self.reload().reply_state, 'uploaded')
        self.act(self.clerk, 'permit_reply_return', notes='جدول ناخوانا است')
        self.assertEqual(self.reload().reply_state, 'returned')
        self.reply()
        self.assertEqual(self.reload().reply_state, 'uploaded')

    def test_outsiders_cannot_decide_or_open(self):
        self.reply()
        for who in (self.citizen, self.accountant, self.stranger_clerk, self.neighbour):
            self.act(who, 'permit_reply_verify', confirm='on')
            self.assertEqual(self.reload().reply_state, 'uploaded', who.profile.role)
        for who in (self.neighbour, self.stranger_clerk, self.accountant):
            self.assertEqual(client_for(who).get(self.url('permit_reply')).status_code, 404, who.profile.role)
        for who in (self.citizen, self.clerk, self.engineer, self.dehyari):
            self.assertEqual(client_for(who).get(self.url('permit_reply')).status_code, 200, who.profile.role)

    def test_the_verdict_is_kept_for_the_next_steps(self):
        self.reply(strength='has')
        self.assertEqual(permit_reply.defaults(self.reload())['strength'], 'has')
        self.assertEqual(reverse('main:permit_reply', args=[self.permit.pk]), self.url('permit_reply'))
