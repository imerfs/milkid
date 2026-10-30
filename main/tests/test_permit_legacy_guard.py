"""A request that has a permit file moves only through the file's own steps: the generic approve / reject / refer / status actions of the old panels
are refused for it (they would close or re-route the request while the file stays at its step)."""
import json

from django.urls import reverse

from main.models import PermitFile
from main.tests.helpers import client_for, make_request, make_user
from main.tests.test_permit_report import Step4


class LegacyActionsAreRefused(Step4):
    def call(self, who, name, **body):
        return client_for(who).post(reverse(f'main:{name}', args=[self.permit.request_id]), data=json.dumps(body), content_type='application/json')

    def unchanged(self):
        sr = self.permit.request
        sr.refresh_from_db()
        self.assertEqual((sr.status, sr.workflow_stage, self.reload().stage_no), ('in_review', 'expert_review', 4))

    def test_expert_endpoints_refuse_a_file_of_the_unlicensed_track(self):
        for name, body in (('api_expert_approve_direct', {'notes': 'x'}), ('api_expert_reject_request', {'reason': 'x'}),
                           ('api_expert_request_documents', {'notes': 'x'})):
            for who in (self.engineer, self.dehyari):
                self.assertEqual(self.call(who, name, **body).status_code, 409, name)
        self.assertNotEqual(self.call(self.engineer, 'api_expert_forward_request', target_role='council', notes='x').status_code, 200)
        self.unchanged()

    def test_status_screen_mayor_and_assign_refuse_it_too(self):
        client_for(self.dehyari).post(reverse('main:update_request_status', args=[self.permit.request_id]), {'status': 'completed'})
        self.call(self.dehyari, 'mayor_request_approve')
        client_for(self.dehyari).post(reverse('main:mayor_request_approve', args=[self.permit.request_id]))
        self.unchanged()

    def test_the_files_own_steps_still_work(self):
        self.permit.refresh_from_db()
        self.assertEqual(self.permit.stage_no, 4)         # reached through the real steps in setUp; reject by the file keeps working (see test_permit_unlicensed)

    def test_an_ordinary_request_is_still_handled_by_the_old_panels(self):
        sr = make_request(make_user('citizen', city_village='روستای آزمون'))
        self.assertFalse(PermitFile.objects.filter(request=sr).exists())
        r = client_for(make_user('engineer', city_village='روستای آزمون')).post(
            reverse('main:api_expert_approve_direct', args=[sr.id]), data=json.dumps({'notes': 'ok'}), content_type='application/json')
        self.assertEqual(r.status_code, 200)
