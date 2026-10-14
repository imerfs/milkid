"""Role gates: wrong role / anonymous never reach role-specific pages."""
from django.test import TestCase
from django.urls import reverse

from main.tests.helpers import client_for, make_user

# url name -> (kwargs, roles that must be turned away)
MAYOR = [
    ('dehyari_dashboard', {}), ('mayor_staff_list', {}), ('mayor_staff_add', {}),
    ('mayor_staff_edit', {'staff_id': 1}), ('mayor_staff_delete', {'staff_id': 1}),
    ('mayor_requests_list', {}), ('mayor_request_approve', {'request_id': 1}),
    ('mayor_request_reject', {'request_id': 1}), ('mayor_request_assign', {'request_id': 1}),
    ('mayor_violations_list', {}), ('mayor_violation_create', {}),
    ('mayor_violation_update', {'violation_id': 1}), ('mayor_announcements_list', {}),
    ('mayor_announcement_create', {}),
]
COUNCIL = [
    ('council_dashboard', {}), ('council_voting_list', {}), ('council_review_requests', {}),
    ('council_request_detail', {'request_id': 1}), ('council_add_comment', {'request_id': 1}),
    ('council_financial_reports', {}),
]
STAFF = [
    ('staff_dashboard', {}), ('engineer_dashboard', None), ('inspector_dashboard', {}),
    ('accountant_dashboard', {}), ('inspection_list', {}), ('inspection_detail', {'inspection_id': 1}),
    ('create_inspection', {'request_id': 1}), ('violation_list', {}),
    ('violation_detail', {'violation_id': 1}), ('technical_report_list', {}),
    ('technical_report_create', {}), ('technical_report_detail', {'report_id': 1}),
    ('technical_report_export', {}), ('assign_request_to_engineer', {'request_id': 1}),
]


class RoleGates(TestCase):
    def assertTurnedAway(self, name, kwargs, user, expect):
        url = reverse(f'main:{name}', kwargs=kwargs or {})
        response = client_for(user).get(url)
        self.assertEqual(response.status_code, 302, f'{name} as {user}')
        self.assertEqual(response.url.split('?')[0], reverse(f'main:{expect}'), f'{name} as {user}')

    def check(self, urls, blocked_roles):
        for role in blocked_roles:
            user = make_user(role)
            for name, kwargs in urls:
                if kwargs is None:   # url shared with another view; skip
                    continue
                self.assertTurnedAway(name, kwargs, user, 'dashboard')
        for name, kwargs in urls:
            if kwargs is not None:
                self.assertTurnedAway(name, kwargs, None, 'login')

    def test_mayor_pages_closed_to_non_dehyari(self):
        self.check(MAYOR, ['citizen', 'owner', 'council', 'inspector', 'accountant', 'engineer'])

    def test_council_pages_closed_to_citizens(self):
        self.check(COUNCIL, ['citizen', 'owner', 'inspector', 'accountant', 'engineer'])

    def test_staff_pages_closed_to_citizens(self):
        self.check(STAFF, ['citizen', 'owner', 'resident'])

    def test_dashboard_pages_are_role_specific(self):
        self.assertTurnedAway('inspector_dashboard', {}, make_user('accountant'), 'dashboard')
        self.assertTurnedAway('accountant_dashboard', {}, make_user('inspector'), 'dashboard')

    def test_council_member_reaches_voting_tab(self):
        response = client_for(make_user('council')).get(reverse('main:council_voting_list'), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'صندوق رای‌گیری')

    def test_dehyari_is_not_bounced_from_mayor_requests(self):
        response = client_for(make_user('dehyari')).get(reverse('main:mayor_requests_list'), HTTP_X_PANEL='1')
        self.assertNotEqual(response.status_code, 302)
