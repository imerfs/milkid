"""Approving and rejecting property ads and their edits, through the admin JSON endpoints and the review module."""
from django.test import TestCase
from django.urls import reverse

from main import ad_review
from main.models import Notification, PropertyAdvertisementEditLog
from main.tests.helpers import client_for, make_ad, make_user


class AdReview(TestCase):
    def setUp(self):
        self.admin = make_user('admin')
        self.owner = make_user('citizen')
        self.ad = make_ad('pending', owner=self.owner)

    def edit(self, **data):
        return PropertyAdvertisementEditLog.objects.create(
            advertisement=self.ad, user=self.owner, edit_data=data, edit_reason='اصلاح')

    def test_approve_publishes_records_who_and_tells_the_advertiser(self):
        ad_review.approve_ad(self.ad, self.admin)
        self.ad.refresh_from_db()
        self.assertEqual((self.ad.status, self.ad.approved_by), ('approved', self.admin))
        self.assertIsNotNone(self.ad.approved_at)
        self.assertTrue(Notification.objects.filter(user=self.owner).exists())

    def test_reject_keeps_the_reason(self):
        ad_review.reject_ad(self.ad, self.admin, 'ناقص')
        self.ad.refresh_from_db()
        self.assertEqual((self.ad.status, self.ad.admin_notes), ('rejected', 'ناقص'))

    def test_an_approved_edit_is_applied_to_the_ad(self):
        edit = self.edit(address='نشانی جدید', total_area='250')
        self.assertTrue(ad_review.approve_edit(edit, self.admin))
        self.ad.refresh_from_db()
        edit.refresh_from_db()
        self.assertEqual((self.ad.address, int(self.ad.total_area)), ('نشانی جدید', 250))
        self.assertEqual((edit.status, edit.reviewed_by), ('approved', self.admin))

    def test_a_rejected_edit_changes_nothing(self):
        edit = self.edit(address='نشانی جدید')
        ad_review.reject_edit(edit, self.admin)
        self.ad.refresh_from_db()
        edit.refresh_from_db()
        self.assertEqual(self.ad.address, 'addr')
        self.assertEqual(edit.status, 'rejected')

    def test_the_json_endpoints_use_the_same_verbs(self):
        client = client_for(self.admin)
        edit = self.edit(address='از طریق API')
        self.assertEqual(client.post(reverse('main:api_admin_approve_ad_edit', args=[edit.pk])).status_code, 200)
        self.ad.refresh_from_db()
        self.assertEqual(self.ad.address, 'از طریق API')
        self.assertEqual(client.post(reverse('main:api_admin_approve_property_ad', args=[self.ad.pk]),
                                     HTTP_X_REQUESTED_WITH='XMLHttpRequest').status_code, 200)
        self.ad.refresh_from_db()
        self.assertEqual(self.ad.status, 'approved')
