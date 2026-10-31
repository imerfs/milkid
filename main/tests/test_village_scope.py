"""One rule for "which requests belong to which village": the list, the single-request check, the permit-file list and the file download check agree."""
from django.contrib.auth.models import User
from django.test import TestCase

from main import request_scope
from main.office.directory import requests_for
from main.tests.helpers import make_municipality, make_request, make_user

A, B = 'روستای الف', 'روستای ب'


def fresh(user):
    return User.objects.get(pk=user.pk)


class OneRule(TestCase):
    def setUp(self):
        self.mayor_b = make_user('dehyari', city_village=B)
        self.muni_b = make_municipality(self.mayor_b, B)
        self.staff_a = fresh(make_user('engineer', city_village=A))
        self.staff_b = fresh(make_user('engineer', city_village=B))
        self.nowhere = fresh(make_user('engineer', city_village='', city_village_name=''))
        self.admin = fresh(make_user('admin'))
        self.by_owner_village = make_request(make_user('citizen', city_village=A))
        self.by_owner_village_name = make_request(make_user('citizen', city_village='', city_village_name=A))
        self.targeted_elsewhere = make_request(make_user('citizen', city_village=A), target_municipality=self.muni_b)
        self.other_village = make_request(make_user('citizen', city_village=B))

    def test_the_rule_by_case(self):
        mine = set(request_scope.visible_requests(self.staff_a).values_list('pk', flat=True))
        self.assertEqual(mine, {self.by_owner_village.pk, self.by_owner_village_name.pk})
        theirs = set(request_scope.visible_requests(self.staff_b).values_list('pk', flat=True))
        self.assertEqual(theirs, {self.targeted_elsewhere.pk, self.other_village.pk})      # the target wins over the applicant's home village

    def test_staff_without_a_village_see_nothing_and_admin_sees_all(self):
        self.assertEqual(request_scope.visible_requests(self.nowhere).count(), 0)
        self.assertEqual(request_scope.visible_requests(self.admin).count(), 4)

    def test_list_and_single_request_check_always_agree(self):
        from main.models import ServiceRequest
        for user in (self.staff_a, self.staff_b, self.nowhere, self.admin):
            listed = set(request_scope.visible_requests(user).values_list('pk', flat=True))
            for sr in ServiceRequest.objects.all():
                self.assertEqual(request_scope.in_scope(user, sr), sr.pk in listed, (user.pk, sr.pk))

    def test_the_directory_rule_is_the_same_q(self):
        pks = set(ServiceRequestPks.filter(requests_for(A)))
        self.assertEqual(pks, {self.by_owner_village.pk, self.by_owner_village_name.pk})


class ServiceRequestPks:
    @staticmethod
    def filter(q):
        from main.models import ServiceRequest
        return ServiceRequest.objects.filter(q).values_list('pk', flat=True)
