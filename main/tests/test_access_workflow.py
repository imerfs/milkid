from django.test import TestCase
from django.urls import reverse

from main.models import Vote
from main.tests.helpers import client_for, make_request, make_user


class RequestStatusAccess(TestCase):
    def post_status(self, user, service_request, status='approved'):
        return client_for(user).post(
            reverse('main:update_request_status', args=[service_request.id]),
            {'status': status, 'admin_notes': 'x'},
        )

    def test_citizen_cannot_change_status_of_own_request(self):
        owner = make_user('citizen')
        sr = make_request(owner)
        self.post_status(owner, sr)
        sr.refresh_from_db()
        self.assertEqual(sr.status, 'pending')

    def test_anonymous_cannot_change_status(self):
        sr = make_request()
        self.post_status(None, sr)
        sr.refresh_from_db()
        self.assertEqual(sr.status, 'pending')

    def test_dehyari_can_change_status(self):
        sr = make_request()
        self.post_status(make_user('dehyari'), sr, 'in_review')
        sr.refresh_from_db()
        self.assertEqual(sr.status, 'in_review')


class CouncilVoteAccess(TestCase):
    def vote(self, user, sr):
        return client_for(user).post(
            reverse('main:council_submit_vote', args=[sr.id]),
            {'vote': 'approve', 'reason': 'ok'},
        )

    def test_citizen_cannot_vote(self):
        sr = make_request()
        self.vote(make_user('citizen'), sr)
        self.assertEqual(Vote.objects.count(), 0)

    def test_council_member_can_vote(self):
        sr = make_request()
        member = make_user('council')
        self.vote(member, sr)
        self.assertEqual(Vote.objects.filter(request=sr, council_member=member).count(), 1)


class ExpertEndpointsAccess(TestCase):
    ENDPOINTS = [
        'api_expert_approve_direct', 'api_expert_reject_request',
        'api_expert_request_documents', 'api_expert_forward_request',
    ]

    def test_citizen_and_anonymous_cannot_use_expert_endpoints(self):
        owner = make_user('citizen')
        for name in self.ENDPOINTS:
            for user in (owner, None):
                sr = make_request(owner)
                client_for(user).post(reverse(f'main:{name}', args=[sr.id]), {'notes': 'x', 'reason': 'x'})
                sr.refresh_from_db()
                self.assertEqual(sr.status, 'pending', f'{name} as {user}')

    def test_engineer_can_approve_directly(self):
        sr = make_request()
        response = client_for(make_user('engineer')).post(
            reverse('main:api_expert_approve_direct', args=[sr.id]), {'notes': 'ok'})
        self.assertEqual(response.status_code, 200)
        sr.refresh_from_db()
        self.assertEqual(sr.status, 'approved')

    def test_expert_dashboard_closed_to_citizens(self):
        response = client_for(make_user('citizen')).get(reverse('main:dehyari_expert_dashboard'))
        self.assertEqual(response.status_code, 302)
