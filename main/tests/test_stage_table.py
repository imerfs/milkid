"""The stage table (main/stages.py) is the one description of the construction-without-a-permit track: the model reads it for the status line and for
"the staff have something to do". These tests need no database: a PermitFile object in memory is enough."""
from django.test import SimpleTestCase

from main import stages
from main.models import PermitFile


def permit(stage, **states):
    return PermitFile(track='unlicensed', stage_no=stage, state='done', **states)


class Table(SimpleTestCase):
    def test_stage_numbers_run_from_one_without_gaps_and_titles_match_the_model_list(self):
        self.assertEqual([s.number for s in stages.UNLICENSED], list(range(1, 13)))
        self.assertEqual(stages.TITLES, [(s.number, s.title) for s in stages.UNLICENSED])

    def test_every_state_field_is_a_real_field_and_every_text_is_filled(self):
        names = {f.name for f in PermitFile._meta.get_fields()}
        for stage in stages.UNLICENSED:
            if stage.state_field:
                self.assertIn(stage.state_field, names, stage.number)
                self.assertTrue(all(stage.texts.values()), stage.number)
                self.assertTrue(set(stage.staff_states) <= set(stage.texts), stage.number)
            if stage.custom:
                self.assertTrue(hasattr(PermitFile, f'{stage.custom}_text') and hasattr(PermitFile, f'{stage.custom}_needs'), stage.number)


class StatusAndStaff(SimpleTestCase):
    def test_a_single_field_stage_reads_the_table(self):
        self.assertEqual(permit(6, reply_state='uploaded').status_text, 'جوابیه‌های کارشناس منتظر تایید')
        self.assertTrue(permit(6, reply_state='uploaded').needs_staff)
        self.assertFalse(permit(6, reply_state='').needs_staff)           # waiting for the applicant
        self.assertFalse(permit(6, reply_state='returned').needs_staff)

    def test_the_last_built_stages_always_wait_for_the_staff(self):
        for stage in (10, 11):
            self.assertTrue(permit(stage).needs_staff)
        self.assertIn('منتظر', permit(10).status_text)
        self.assertIn('تایید نهایی', permit(10, form16_state='filed').status_text)
        self.assertIn('تایید نهایی', permit(11, summary_state='sent').status_text)

    def test_stage_twelve_has_no_rule_yet(self):
        self.assertFalse(permit(12).needs_staff)
        self.assertIn('تایید شد', permit(12).status_text)

    def test_a_custom_stage_uses_its_methods(self):
        self.assertTrue(permit(3, notice_state='uploaded').needs_staff)
        self.assertFalse(permit(3, notice_state='verified', visit_state='').needs_staff)
        self.assertEqual(permit(3, notice_state='verified', visit_state='requested').status_text, 'درخواست بازدید منتظر کارشناس فنی')

    def test_a_submitted_file_always_needs_the_staff(self):
        self.assertTrue(PermitFile(track='unlicensed', stage_no=7, state='submitted').needs_staff)
