from django.test import TestCase
from django.urls import reverse

from main.tests.helpers import client_for, make_payment, make_user


class PaymentReviewAccess(TestCase):
    """Only finance/municipality roles may approve or reject a payment."""

    def approve(self, user, payment):
        return client_for(user).post(reverse('main:api_approve_payment', args=[payment.id]))

    def test_anonymous_cannot_approve(self):
        payment = make_payment()
        response = self.approve(None, payment)
        self.assertIn(response.status_code, (302, 401, 403))
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'pending')

    def test_citizen_cannot_approve_own_payment(self):
        owner = make_user('citizen')
        payment = make_payment(owner)
        response = self.approve(owner, payment)
        self.assertEqual(response.status_code, 403)
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'pending')

    def test_accountant_can_approve(self):
        payment = make_payment()
        response = self.approve(make_user('accountant'), payment)
        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'completed')

    def test_citizen_cannot_reject(self):
        payment = make_payment()
        response = client_for(make_user('citizen')).post(
            reverse('main:api_reject_payment', args=[payment.id]))
        self.assertEqual(response.status_code, 403)
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'pending')
