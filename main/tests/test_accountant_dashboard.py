"""The accountant's online-payments tab of the single-page workspace (rows, approve/reject URLs, filters)."""
from django.test import TestCase
from django.urls import reverse

from main.models import Payment
from main.tests.helpers import client_for, make_municipality, make_payment, make_user as _make_user
from django.contrib.auth.models import User


class OnlinePaymentsTab(TestCase):
    def setUp(self):
        dehyar = _make_user('dehyari')
        muni = make_municipality(dehyar)
        self.accountant = User.objects.get(pk=_make_user('accountant', city_village=muni.city_village).pk)
        self.pending = make_payment()
        self.pending.description = 'مالیات آزمون-pending'
        self.pending.receipt_number = 'RCPT-PENDING-1'
        self.pending.save()
        self.done = make_payment()
        Payment.objects.filter(pk=self.done.pk).update(
            status='completed', description='جریمه-done', receipt_number='RCPT-DONE-1', amount=7000)

    def tab(self, **params):
        return client_for(self.accountant).get(reverse('main:acc_panel'), {'tab': 'online', **params})

    def test_dashboard_page_has_no_old_payment_widgets(self):
        html = client_for(self.accountant).get(reverse('main:accountant_dashboard')).content.decode()
        self.assertNotIn('financial-chart', html)
        self.assertNotIn('RCPT-PENDING-1', html)

    def test_shows_real_pending_payment_with_approve_url(self):
        html = self.tab().content.decode()
        self.assertIn('مالیات آزمون-pending', html)
        self.assertIn(reverse('main:api_approve_payment', args=[self.pending.id]), html)
        self.assertIn(reverse('main:api_reject_payment', args=[self.pending.id]), html)

    def test_shows_real_transactions_not_mock_rows(self):
        html = self.tab().content.decode()
        self.assertIn('RCPT-DONE-1', html)
        self.assertNotIn('T89761', html)

    def test_search_and_status_filter_the_table(self):
        table = self.tab(q='RCPT-DONE').content.decode().split('<tbody>')[-1]
        self.assertIn('RCPT-DONE-1', table)
        self.assertNotIn('RCPT-PENDING-1', table)
        table = self.tab(pay_status='completed').content.decode().split('id="online-all"')[-1]
        self.assertIn('RCPT-DONE-1', table)
        self.assertNotIn('RCPT-PENDING-1', table)

    def test_citizen_cannot_open_the_tab(self):
        r = client_for(_make_user('citizen')).get(reverse('main:acc_panel'), {'tab': 'online'})
        self.assertEqual(r.status_code, 302)
