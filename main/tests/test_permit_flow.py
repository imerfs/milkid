"""The building-permit track, every stage: a filed application reaches the panels of the clerk and the dehyari of the village (and nobody else's), the owner
sees where the file stands, the stage's pages open for the staff and not for outsiders, and the file moves through the real step-by-step chain up to the
end-of-work certificate (stage 9) and the services / extension pages (the tenth area).

Each class starts from a file that really went through the earlier steps (the step modules build on each other).
"""
# pylint: disable=no-member   # the mixin runs inside the TestCase classes it is combined with
from django.urls import reverse

from main.models import Notification
from main.office import permits
from main.tests.helpers import client_for
from main.tests.test_permit_endwork import AtTheEnd
from main.tests.test_permit_extension import Issued
from main.tests.test_permit_step2 import Village as Stage1Base
from main.tests.test_permit_step3 import AtStepThree
from main.tests.test_permit_step4 import AtStepFour
from main.tests.test_permit_step5 import AtStepFive
from main.tests.test_permit_step6 import AtStepSeven, AtStepSix
from main.tests.test_permit_supervision import Supervised

STAFF = ('clerk', 'dehyari')


class Routing:
    stage = None
    pages = ()

    def go(self, name):
        return reverse(f'main:{name}', args=[self.permit.pk])

    def test_the_file_is_at_the_expected_stage(self):
        self.permit.refresh_from_db()
        self.assertEqual(self.permit.stage_no, self.stage)
        self.assertFalse(self.permit.unlicensed)
        self.assertTrue(self.permit.status_text)

    def test_the_staff_of_the_village_were_told_and_have_it_in_their_panel(self):
        for name in STAFF:
            self.assertIn(self.permit.pk, [f.pk for f in permits.panel_rows(getattr(self, name))['rows']], name)
            self.assertTrue(Notification.objects.filter(user=getattr(self, name)).exists(), name)
        for name in ('stranger', 'citizen', 'neighbour'):
            self.assertNotIn(self.permit.pk, [f.pk for f in permits.panel_rows(getattr(self, name))['rows']], name)
        self.assertFalse(Notification.objects.filter(user=self.stranger, title__contains='پروانه').exists())

    def test_the_owner_sees_the_status_and_bystanders_do_not(self):
        page = client_for(self.citizen).get(self.go('permit_file'))
        self.assertEqual(page.status_code, 200)
        self.assertEqual(client_for(self.neighbour).get(self.go('permit_file')).status_code, 404)
        self.assertEqual(client_for(self.stranger).get(self.go('permit_file')).status_code, 404)

    def test_the_stage_pages_open_for_the_staff_and_not_for_outsiders(self):
        for page in self.pages:
            for name in STAFF:
                self.assertEqual(client_for(getattr(self, name)).get(self.go(page)).status_code, 200, f'{page} {name}')
            for name in ('stranger', 'neighbour'):
                self.assertNotEqual(client_for(getattr(self, name)).get(self.go(page)).status_code, 200, f'{page} {name}')


class Stage1(Routing, Stage1Base):
    stage, pages = 1, ('permit_file',)


class Stage3(Routing, AtStepThree):
    stage, pages = 3, ('permit_forms',)


class Stage4(Routing, AtStepFour):
    stage, pages = 4, ('permit_design',)


class Stage5(Routing, AtStepFive):
    stage, pages = 5, ('permit_fees',)


class Stage6(Routing, AtStepSix):
    stage, pages = 6, ('permit_fees',)


class Stage7(Routing, AtStepSeven):
    stage, pages = 7, ('permit_licence',)


class IssuedPermit(Routing, Issued):
    stage, pages = 7, ('permit_licence', 'permit_services', 'permit_extension')


class UnderSupervision(Routing, Supervised):
    stage, pages = 7, ('permit_supervision', 'permit_services', 'permit_extension')


class EndOfWork(Routing, AtTheEnd):
    stage, pages = 9, ('permit_endwork', 'permit_supervision')
