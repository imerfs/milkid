"""Construction without a permit, every stage: the file sits in the right panels (clerk, technical expert, dehyari of the village; the financial officer
when money is due), stays hidden from other villages and bystanders, the owner sees the status, and the whole chain finishes at stage 12.

The step modules build on each other (each ``StepN`` class replays steps 1..N-1 through the real URLs), so every class below starts from a file that
really went through the earlier steps.
"""
# pylint: disable=no-member   # the mixin runs inside the TestCase classes it is combined with
from main.models import Notification
from main.office import permits
from main.tests.helpers import client_for
from main.tests.test_permit_bonyad import Step8
from main.tests.test_permit_commit import Step5
from main.tests.test_permit_dues import Step7
from main.tests.test_permit_files import PNG, upload
from main.tests.test_permit_form16 import Step10, Step11
from main.tests.test_permit_notice import Notice
from main.tests.test_permit_pack import Step9
from main.tests.test_permit_reply import Step6
from main.tests.test_permit_report import Step4

STAFF = ('clerk', 'engineer', 'dehyari')


class Routing:
    """Mixed into a class that has reached ``stage``."""
    stage = None
    page = None

    def test_the_file_is_at_the_expected_stage(self):
        self.assertEqual(self.reload().stage_no, self.stage)
        self.assertTrue(self.permit.unlicensed)
        self.assertTrue(self.permit.status_text)

    def test_the_three_staff_were_told_when_the_citizen_filed(self):
        for name in STAFF:
            self.assertTrue(Notification.objects.filter(user=getattr(self, name), title__contains='ساخت‌وساز بدون پروانه').exists(), name)
        self.assertFalse(Notification.objects.filter(user=self.stranger_clerk, title__contains='ساخت‌وساز بدون پروانه').exists())

    def test_it_is_in_the_panels_of_the_three_staff_of_the_village_only(self):
        for name in STAFF:
            rows = permits.panel_rows(getattr(self, name))['rows']
            self.assertIn(self.permit.pk, [f.pk for f in rows], name)
        for name in ('stranger_clerk', 'citizen', 'neighbour'):
            self.assertNotIn(self.permit.pk, [f.pk for f in permits.panel_rows(getattr(self, name))['rows']], name)

    def test_the_financial_officer_has_no_access_to_the_file_pages(self):
        self.assertEqual(client_for(self.accountant).get(self.url('permit_file')).status_code, 404)

    def test_the_owner_sees_the_file_and_its_status_and_a_bystander_does_not(self):
        page = client_for(self.citizen).get(self.url('permit_file'))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, self.reload().status_text)
        self.assertEqual(client_for(self.neighbour).get(self.url('permit_file')).status_code, 404)
        self.assertEqual(client_for(self.stranger_clerk).get(self.url('permit_file')).status_code, 404)

    def test_the_stage_page_opens_for_the_three_staff_and_not_for_outsiders(self):
        if not self.page:
            return
        for name in STAFF:
            self.assertEqual(client_for(getattr(self, name)).get(self.url(self.page)).status_code, 200, name)
        for name in ('stranger_clerk', 'neighbour'):
            self.assertNotEqual(client_for(getattr(self, name)).get(self.url(self.page)).status_code, 200, name)


class Stage3(Routing, Notice):
    stage = 3
    page = 'permit_notice'


class Stage4(Routing, Step4):
    stage, page = 4, 'permit_report'


class Stage5(Routing, Step5):
    stage, page = 5, 'permit_commit'


class Stage6(Routing, Step6):
    stage, page = 6, 'permit_reply'


class Stage7(Routing, Step7):
    stage, page = 7, 'permit_dues'

    def test_the_financial_officer_gets_the_file_for_the_money(self):
        self.permit.dues_state = 'issued'
        self.permit.save()
        self.assertIn(self.permit.pk, [f.pk for f in permits.fee_rows_for(self.accountant)['rows']])
        self.assertNotIn(self.permit.pk, [f.pk for f in permits.fee_rows_for(self.stranger_clerk)['rows']])


class Stage8(Routing, Step8):
    stage, page = 8, 'permit_bonyad'


class Stage9(Routing, Step9):
    stage, page = 9, 'permit_pack'


class Stage10(Routing, Step10):
    stage, page = 10, 'permit_form16'


class Stage11(Routing, Step11):
    stage, page = 11, 'permit_form16'

    def test_the_last_built_step_ends_at_stage_12_and_tells_the_owner(self):
        self.permit.summary_state = 'sent'
        self.permit.save()
        before = Notification.objects.filter(user=self.citizen).count()
        for who in (self.dehyari,):
            self.act(who, 'permit_step11_finish', confirm='on')
        self.assertEqual(self.reload().stage_no, 12)
        self.assertGreater(Notification.objects.filter(user=self.citizen).count(), before)
        self.assertIn('12', str(self.permit.stage_no))
        self.assertEqual(self.permit.stage_title, 'رأی کمیسیون، جریمه و پایان کار')
        self.assertIn(self.permit.pk, [f.pk for f in permits.panel_rows(self.clerk)['rows']])


class InterchangeableStaff(Step10):
    """Any of the clerk, the technical expert and the dehyari can take the file over at a step: whoever confirms moves it on, and the others see it move."""

    def test_each_of_them_can_confirm_the_same_step(self):
        self.file(scan=upload('f.png', PNG))
        self.assertEqual(self.reload().form16_state, 'filed')
        for who in STAFF:
            self.permit.stage_no = 10
            self.permit.save()
            self.act(getattr(self, who), 'permit_step10_finish', confirm='on')
            self.assertEqual(self.reload().stage_no, 11, who)
