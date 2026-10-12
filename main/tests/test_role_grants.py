from django.test import TestCase
from django.urls import reverse

from main.models import Notification, RoleGrant, UserProfile
from main.tests.helpers import client_for, make_municipality, make_user


class Village(TestCase):
    def setUp(self):
        self.dehyari = make_user('dehyari')
        make_municipality(self.dehyari, 'روستای الف')
        self.resident = make_user('citizen', city_village='روستای الف')
        self.stranger = make_user('citizen', city_village='روستای ب')

    def grant(self, target, role, who=None):
        return client_for(who or self.dehyari).post(
            reverse('main:role_grant'), {'user_id': target.id, 'role': role})

    def role(self, user):
        return UserProfile.objects.get(user=user).role


class GrantingRoles(Village):
    def test_dehyari_grants_each_staff_role(self):
        for role in ('accountant', 'engineer', 'inspector', 'council'):
            user = make_user('citizen', city_village='روستای الف')
            self.grant(user, role)
            self.assertEqual(self.role(user), role)

    def test_grant_is_recorded_and_user_is_notified(self):
        self.grant(self.resident, 'accountant')
        record = RoleGrant.objects.get(user=self.resident)
        self.assertEqual((record.role, record.previous_role, record.granted_by), ('accountant', 'citizen', self.dehyari))
        self.assertIsNone(record.revoked_at)
        self.assertTrue(Notification.objects.filter(user=self.resident).exists())

    def test_granting_the_same_role_twice_changes_nothing(self):
        self.grant(self.resident, 'engineer')
        self.grant(self.resident, 'engineer')
        self.assertEqual(RoleGrant.objects.filter(user=self.resident).count(), 1)
        self.assertEqual(Notification.objects.filter(user=self.resident).count(), 1)

    def test_changing_role_closes_the_old_grant_and_keeps_history(self):
        self.grant(self.resident, 'engineer')
        self.grant(self.resident, 'inspector')
        self.assertEqual(self.role(self.resident), 'inspector')
        grants = RoleGrant.objects.filter(user=self.resident).order_by('id')
        self.assertEqual([g.role for g in grants], ['engineer', 'inspector'])
        self.assertIsNotNone(grants[0].revoked_at)
        self.assertIsNone(grants[1].revoked_at)
        self.assertEqual(grants[1].previous_role, 'engineer')

    def test_only_the_four_staff_roles_can_be_granted(self):
        for role in ('admin', 'dehyari', 'owner', 'bogus', ''):
            response = self.grant(self.resident, role)
            self.assertEqual(response.status_code, 400, role)
            self.assertEqual(self.role(self.resident), 'citizen', role)

    def test_user_of_another_village_is_not_found(self):
        response = self.grant(self.stranger, 'accountant')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.role(self.stranger), 'citizen')

    def test_protected_accounts_cannot_be_changed(self):
        other_dehyari = make_user('dehyari', city_village='روستای الف')
        admin = make_user('admin', city_village='روستای الف')
        for target in (self.dehyari, other_dehyari, admin):
            self.assertEqual(self.grant(target, 'accountant').status_code, 403)
        self.assertEqual(self.role(self.dehyari), 'dehyari')
        self.assertEqual(self.role(admin), 'admin')

    def test_nobody_else_can_grant(self):
        for role in ('citizen', 'accountant', 'council', 'engineer'):
            who = make_user(role, city_village='روستای الف')
            self.assertIn(self.grant(self.resident, 'engineer', who).status_code, (302, 403))
        self.assertEqual(self.role(self.resident), 'citizen')
        self.assertEqual(self.client.post(reverse('main:role_grant'), {'user_id': self.resident.id, 'role': 'engineer'}).status_code, 302)
        self.assertEqual(self.role(self.resident), 'citizen')

    def test_dehyari_without_a_municipality_cannot_grant(self):
        lone = make_user('dehyari')
        self.assertEqual(self.grant(self.resident, 'engineer', lone).status_code, 404)

    def test_get_is_not_allowed_to_change_roles(self):
        r = client_for(self.dehyari).get(reverse('main:role_grant'))
        self.assertEqual(r.status_code, 405)


class RevokingRoles(Village):
    def revoke(self, target, who=None):
        return client_for(who or self.dehyari).post(reverse('main:role_revoke', args=[target.id]))

    def test_revoke_returns_user_to_citizen_and_closes_grant(self):
        self.grant(self.resident, 'inspector')
        self.revoke(self.resident)
        self.assertEqual(self.role(self.resident), 'citizen')
        self.assertIsNotNone(RoleGrant.objects.get(user=self.resident).revoked_at)

    def test_revoke_twice_is_harmless(self):
        self.grant(self.resident, 'inspector')
        self.revoke(self.resident)
        self.assertEqual(self.revoke(self.resident).status_code, 302)
        self.assertEqual(self.role(self.resident), 'citizen')

    def test_cannot_revoke_dehyari_or_stranger(self):
        self.assertEqual(self.revoke(self.dehyari).status_code, 403)
        self.assertEqual(self.revoke(self.stranger).status_code, 404)


class RolesPage(Village):
    def test_lists_staff_and_finds_residents_of_the_village_only(self):
        self.grant(self.resident, 'accountant')
        page = client_for(self.dehyari).get(reverse('main:role_grants')).content.decode()
        self.assertIn(self.resident.username, page)
        found = client_for(self.dehyari).get(reverse('main:role_grants'), {'q': 'citizen'}).content.decode()
        self.assertNotIn(self.stranger.username, found)

    def test_empty_state_when_nobody_has_a_role_yet(self):
        page = client_for(self.dehyari).get(reverse('main:role_grants')).content.decode()
        self.assertIn('هنوز نقشی', page)

    def test_citizen_cannot_open_the_page(self):
        self.assertEqual(client_for(self.resident).get(reverse('main:role_grants')).status_code, 302)


class LegacyStaffScreensCannotEscalate(Village):
    """The older mayor_staff_* screens used to accept any role string from the form."""

    def test_staff_edit_ignores_non_staff_roles(self):
        self.grant(self.resident, 'accountant')
        profile = UserProfile.objects.get(user=self.resident)
        client_for(self.dehyari).post(reverse('main:mayor_staff_edit', args=[profile.id]), {'role': 'admin'})
        self.assertEqual(self.role(self.resident), 'accountant')

    def test_staff_delete_only_removes_staff_never_citizens_or_self(self):
        mine = UserProfile.objects.get(user=self.dehyari)
        res = UserProfile.objects.get(user=self.resident)
        for profile in (mine, res):
            client_for(self.dehyari).post(reverse('main:mayor_staff_delete', args=[profile.id]))
        self.assertTrue(UserProfile.objects.filter(user=self.dehyari).exists())
        self.assertTrue(UserProfile.objects.filter(user=self.resident).exists())
