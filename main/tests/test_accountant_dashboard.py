from django.test import TestCase
from django.urls import reverse

from main.models import Payment
from main.tests.helpers import client_for, make_payment, make_user


class AccountantDashboardPage(TestCase):
    def setUp(self):
        self.accountant = make_user('accountant')
        self.pending = make_payment()
        self.pending.description = 'مالیات آزمون-pending'
        self.pending.receipt_number = 'RCPT-PENDING-1'
        self.pending.save()
        self.done = make_payment()
        Payment.objects.filter(pk=self.done.pk).update(
            status='completed', description='جریمه-done', receipt_number='RCPT-DONE-1', amount=7000)

    def page(self, **params):
        return client_for(self.accountant).get(reverse('main:accountant_dashboard'), params)

    def test_shows_real_pending_payment_with_approve_url(self):
        html = self.page().content.decode()
        self.assertIn('مالیات آزمون-pending', html)
        self.assertIn(reverse('main:api_approve_payment', args=[self.pending.id]), html)
        self.assertIn(reverse('main:api_reject_payment', args=[self.pending.id]), html)

    def test_shows_real_transactions_not_mock_rows(self):
        html = self.page().content.decode()
        self.assertIn('RCPT-DONE-1', html)
        self.assertNotIn('T89761', html)
        self.assertNotIn('خرید تجهیزات', html)

    def test_search_filters_the_table(self):
        table = self.page(search='RCPT-DONE').content.decode().split('<tbody>')[1]
        self.assertIn('RCPT-DONE-1', table)
        self.assertNotIn('RCPT-PENDING-1', table)

    def test_chart_data_comes_from_the_database(self):
        html = self.page().content.decode()
        self.assertIn('7000.0', html)  # this month's completed amount
