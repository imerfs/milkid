"""Build an unlicensed-track permit file at any stage without replaying the earlier steps through HTTP.

The step modules' tests chain by inheritance (Step4 -> Step5 -> ... -> Step11), so a test at stage 10 pays for ten steps of posts in ``setUp``. A test that
only needs "a file that stands at stage N" (the panels, the status text, who may see it) uses ``StageFixture.at_stage(n)`` instead: it files the application
through the real form once and then writes the stage and the finished states of the earlier stages straight from the stage table (main/stages.py).
The chain-based tests stay as the end-to-end proof that the steps really lead from one to the next.
"""
from main import stages
from main.models import PermitFile
from main.tests.test_permit_unlicensed import UnlicensedBase

# the finished state of the stages whose answer depends on several fields (not in the table's ``done_state``)
CUSTOM_DONE = {
    3: {'notice_state': 'verified', 'visit_state': 'done'},
    4: {'report_state': 'filed', 'overhang_state': 'verified', 'materials_state': 'verified'},
    5: {'expert_state': 'introduced', 'consent_state': 'verified', 'deed_state': 'verified'},
    7: {'dues_state': 'issued', 'plan_state': 'confirmed'},
}


class StageFixture(UnlicensedBase):
    """Users: citizen, neighbour, clerk, engineer, dehyari, accountant, stranger_clerk (see test_permit_files.Village)."""

    def at_stage(self, number):
        permit = self.filed()
        fields = {}
        for stage in stages.UNLICENSED:
            if stage.number >= number:
                break
            if stage.state_field and stage.done_state:
                fields[stage.state_field] = stage.done_state
            fields.update(CUSTOM_DONE.get(stage.number, {}))
        PermitFile.objects.filter(pk=permit.pk).update(stage_no=number, state='done', **fields)
        permit.refresh_from_db()
        return permit
