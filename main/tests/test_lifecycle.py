"""ServiceRequest lifecycle, observed through the URLs that change it."""
import json

from django.test import TestCase
from django.urls import reverse

from main.models import Notification
from main.tests.helpers import client_for, make_municipality, make_request, make_user


class LifecycleCase(TestCase):
    def post_json(self, user, url_name, sr, **body):
        return client_for(user).post(
            reverse(f'main:{url_name}', args=[sr.id]),
            data=json.dumps(body), content_type='application/json',
        )

    def assertRecorded(self, sr, status, notified=True):
        sr.refresh_from_db()
        self.assertEqual(sr.status, status)
        self.assertGreaterEqual(len(sr.workflow_history), 1)
        if notified:
            self.assertTrue(Notification.objects.filter(user=sr.user, related_request=sr).exists())


class ExpertTransitions(LifecycleCase):
    def setUp(self):
        self.expert = make_user('engineer')
        self.sr = make_request()

    def test_approve_records_history_and_notifies_owner(self):
        r = self.post_json(self.expert, 'api_expert_approve_direct', self.sr, notes='خوب')
        self.assertEqual(r.status_code, 200)
        self.assertRecorded(self.sr, 'approved')
        self.assertEqual(self.sr.workflow_stage, 'approved')
        self.assertIsNotNone(self.sr.reviewed_at)

    def test_approve_with_completion_flag_completes(self):
        self.post_json(self.expert, 'api_expert_approve_direct', self.sr, notes='x', mark_as_completed=True)
        self.assertRecorded(self.sr, 'completed')

    def test_reject_requires_reason(self):
        r = self.post_json(self.expert, 'api_expert_reject_request', self.sr, reason='')
        self.assertEqual(r.status_code, 400)
        self.sr.refresh_from_db()
        self.assertEqual(self.sr.status, 'pending')

    def test_reject_with_reason(self):
        self.post_json(self.expert, 'api_expert_reject_request', self.sr, reason='ناقص')
        self.assertRecorded(self.sr, 'rejected')
        self.assertIn('ناقص', self.sr.staff_comments)

    def test_request_documents_requires_notes(self):
        r = self.post_json(self.expert, 'api_expert_request_documents', self.sr, notes='')
        self.assertEqual(r.status_code, 400)
        self.sr.refresh_from_db()
        self.assertEqual(self.sr.status, 'pending')

    def test_request_documents(self):
        self.post_json(self.expert, 'api_expert_request_documents', self.sr, notes='سند')
        self.assertRecorded(self.sr, 'requires_documents')

    def test_forward_to_council(self):
        r = self.post_json(self.expert, 'api_expert_forward_request', self.sr, target_role='council')
        self.assertEqual(r.status_code, 200)
        self.assertRecorded(self.sr, 'in_review')
        self.assertEqual((self.sr.workflow_stage, self.sr.referral_target), ('council_review', 'council'))

    def test_forward_rejects_unknown_role(self):
        r = self.post_json(self.expert, 'api_expert_forward_request', self.sr, target_role='nobody')
        self.assertEqual(r.status_code, 400)
        self.sr.refresh_from_db()
        self.assertEqual(self.sr.status, 'pending')


class MayorTransitions(LifecycleCase):
    def setUp(self):
        self.mayor = make_user('dehyari')
        make_municipality(self.mayor, 'روستای الف')
        self.local = make_request(make_user('citizen', city_village='روستای الف'))
        self.foreign = make_request(make_user('citizen', city_village='روستای ب'))

    def test_mayor_approves_local_request(self):
        client_for(self.mayor).post(reverse('main:mayor_request_approve', args=[self.local.id]))
        self.assertRecorded(self.local, 'approved')
        self.assertIsNotNone(self.local.reviewed_at)

    def test_mayor_cannot_approve_other_village(self):
        r = client_for(self.mayor).post(reverse('main:mayor_request_approve', args=[self.foreign.id]))
        self.assertEqual(r.status_code, 403)
        self.foreign.refresh_from_db()
        self.assertEqual(self.foreign.status, 'pending')

    def test_mayor_rejects_local_request(self):
        client_for(self.mayor).post(reverse('main:mayor_request_reject', args=[self.local.id]), {'reason': 'نامعتبر'})
        self.assertRecorded(self.local, 'rejected')
        self.assertIn('نامعتبر', self.local.staff_comments)

    def test_mayor_cannot_reject_other_village(self):
        client_for(self.mayor).post(reverse('main:mayor_request_reject', args=[self.foreign.id]), {'reason': 'x'})
        self.foreign.refresh_from_db()
        self.assertEqual(self.foreign.status, 'pending')


class StatusUpdateRules(LifecycleCase):
    def test_unknown_status_is_ignored(self):
        sr = make_request()
        client_for(make_user('dehyari')).post(
            reverse('main:update_request_status', args=[sr.id]), {'status': 'bogus'})
        sr.refresh_from_db()
        self.assertEqual(sr.status, 'pending')

    def test_completed_request_is_final(self):
        sr = make_request(status='completed')
        client_for(make_user('dehyari')).post(
            reverse('main:update_request_status', args=[sr.id]), {'status': 'pending'})
        sr.refresh_from_db()
        self.assertEqual(sr.status, 'completed')

    def test_status_change_is_logged_and_notified(self):
        sr = make_request()
        client_for(make_user('dehyari')).post(
            reverse('main:update_request_status', args=[sr.id]), {'status': 'in_review'})
        self.assertRecorded(sr, 'in_review')


class InspectionOutcome(LifecycleCase):
    def setUp(self):
        from main.models import Inspection
        self.inspector = make_user('inspector')
        self.sr = make_request(status='in_review')
        self.inspection = Inspection.objects.create(request=self.sr, inspector=self.inspector, status='pending')

    def post(self, **data):
        return client_for(self.inspector).post(
            reverse('main:inspection_detail', args=[self.inspection.id]), data)

    def test_completed_inspection_approves_request_with_history(self):
        self.post(action='complete', report='ok')
        self.assertRecorded(self.sr, 'approved')

    def test_rejected_inspection_rejects_request_with_history(self):
        self.post(action='reject', rejection_reason='خلاف')
        self.assertRecorded(self.sr, 'rejected')

    def test_other_inspector_cannot_touch_inspection(self):
        r = client_for(make_user('inspector')).post(
            reverse('main:inspection_detail', args=[self.inspection.id]), {'action': 'complete'})
        self.assertEqual(r.status_code, 404)
        self.sr.refresh_from_db()
        self.assertEqual(self.sr.status, 'in_review')


class Submit(TestCase):
    """lifecycle.submit is the one way a request is created."""

    def setUp(self):
        self.citizen = make_user('citizen')

    def test_a_new_request_starts_at_the_expert_with_a_history_entry(self):
        from main import lifecycle
        sr = lifecycle.submit(self.citizen, action='ثبت', request_type='other', title='t', description='d')
        sr.refresh_from_db()
        self.assertEqual((sr.status, sr.workflow_stage, sr.referral_target), ('pending', 'expert_review', 'engineer'))
        self.assertEqual(sr.user, self.citizen)
        self.assertEqual(len(sr.workflow_history), 1)
        self.assertEqual(sr.workflow_history[0]['to_role'], 'engineer')

    def test_the_address_the_caller_left_empty_comes_from_the_profile(self):
        from main import lifecycle
        from main.models import CityVillage, County, District, Province
        province = Province.objects.create(name='استان آزمون')
        county = County.objects.create(name='شهرستان آزمون', province=province)
        district = District.objects.create(name='بخش آزمون', county=county)
        village = CityVillage.objects.create(name='روستای آزمون', district=district)
        profile = self.citizen.profile
        profile.province, profile.county, profile.city_village = province.name, county.name, village.name
        profile.save()
        sr = lifecycle.submit(self.citizen, action='ثبت', request_type='other', title='t', description='d')
        self.assertEqual((sr.province, sr.county, sr.city_village), (province, county, village))
        other = Province.objects.create(name='استان دیگر')
        sr = lifecycle.submit(self.citizen, action='ثبت', request_type='other', title='t', description='d', province=other)
        self.assertEqual(sr.province, other)               # what the caller gave is kept
