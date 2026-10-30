"""Every stage of the unlicensed track, checked from a file built at that stage (no replay of the earlier steps): the panels, the status line, who may open
the file and the stage's own page. The chain-based tests (test_unlicensed_flow and the step modules) remain the end-to-end proof of the steps themselves."""
from main.office import permits
from main.tests.helpers import client_for
from main.tests.permit_stages import StageFixture

PAGES = {3: 'permit_notice', 4: 'permit_report', 5: 'permit_commit', 6: 'permit_reply', 7: 'permit_dues', 8: 'permit_bonyad', 9: 'permit_pack',
         10: 'permit_form16', 11: 'permit_form16'}
STAFF = ('clerk', 'engineer', 'dehyari')


class EveryStage(StageFixture):
    def go(self, permit, name):
        from django.urls import reverse
        return reverse(f'main:{name}', args=[permit.pk])

    def test_each_stage_reaches_the_right_panels_with_a_status_line(self):
        for number in range(2, 13):
            with self.subTest(stage=number):
                permit = self.at_stage(number)
                self.assertEqual((permit.stage_no, permit.state), (number, 'done'))
                self.assertTrue(permit.status_text, number)
                for name in STAFF:
                    self.assertIn(permit.pk, [f.pk for f in permits.panel_rows(getattr(self, name))['rows']], name)
                for name in ('stranger_clerk', 'neighbour', 'citizen'):
                    self.assertNotIn(permit.pk, [f.pk for f in permits.panel_rows(getattr(self, name))['rows']], name)
                owner = client_for(self.citizen).get(self.go(permit, 'permit_file'))
                self.assertEqual(owner.status_code, 200)
                self.assertEqual(client_for(self.stranger_clerk).get(self.go(permit, 'permit_file')).status_code, 404)
                permit.delete()

    def test_the_stage_pages_open_for_the_staff_of_the_village_only(self):
        for number, page in PAGES.items():
            with self.subTest(stage=number):
                permit = self.at_stage(number)
                for name in STAFF:
                    self.assertEqual(client_for(getattr(self, name)).get(self.go(permit, page)).status_code, 200, f'{page} {name}')
                self.assertNotEqual(client_for(self.stranger_clerk).get(self.go(permit, page)).status_code, 200, page)
                permit.delete()

    def test_the_staff_are_waiting_exactly_where_the_table_says(self):
        waiting = {10: True, 11: True, 12: False}
        for number, expected in waiting.items():
            permit = self.at_stage(number)
            self.assertEqual(permit.needs_staff, expected, number)
            permit.delete()
