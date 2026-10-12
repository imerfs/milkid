"""An advertisement nobody has approved must not be readable by strangers, by listing or by its address."""
from django.test import TestCase
from django.urls import reverse

from main.tests.helpers import client_for, make_ad, make_user


class AdVisibility(TestCase):
    def detail(self, ad, client):
        return client.get(reverse('main:property_detail', args=[ad.id]))

    def test_approved_ad_is_public(self):
        ad = make_ad('approved')
        self.assertEqual(self.detail(ad, client_for()).status_code, 200)

    def test_pending_rejected_and_expired_ads_are_hidden_from_strangers(self):
        for status in ('pending', 'rejected', 'expired'):
            ad = make_ad(status)
            with self.subTest(status=status):
                self.assertEqual(self.detail(ad, client_for()).status_code, 404)
                self.assertEqual(self.detail(ad, client_for(make_user('citizen'))).status_code, 404)

    def test_the_owner_still_sees_their_own_unapproved_ad(self):
        owner = make_user('citizen')
        ad = make_ad('pending', owner)
        self.assertEqual(self.detail(ad, client_for(owner)).status_code, 200)

    def test_admin_sees_every_ad(self):
        ad = make_ad('pending')
        self.assertEqual(self.detail(ad, client_for(make_user('admin'))).status_code, 200)

    def test_listing_never_shows_unapproved_ads_to_the_public_even_with_a_status_parameter(self):
        ad = make_ad('pending')
        ad.address = 'آدرس-محرمانه-۱۲۳'
        ad.save()
        html = client_for().get(reverse('main:property_listings'), {'status': 'all'}).content.decode()
        self.assertNotIn('آدرس-محرمانه-۱۲۳', html)


class ListingFilters(TestCase):
    def test_header_search_box_name_is_understood(self):
        ad = make_ad('approved')
        ad.address = 'خیابان-یکتا-۹۹'
        ad.save()
        other = make_ad('approved')
        other.address = 'بلوار-دیگر'
        other.save()
        html = client_for().get(reverse('main:property_listings'), {'query': 'یکتا'}).content.decode()
        self.assertIn('خیابان-یکتا-۹۹', html)
        self.assertNotIn('بلوار-دیگر', html)

    def test_filters_and_pagination_update_only_the_results_through_htmx(self):
        html = client_for().get(reverse('main:property_listings')).content.decode()
        self.assertIn('/static/vendor/htmx/htmx.min.js', html)
        self.assertIn('id="ads-results"', html)
        self.assertGreaterEqual(html.count('hx-select="#ads-results"'), 4)      # 3 forms + the results (pagination links)
        self.assertGreaterEqual(html.count('hx-push-url="true"'), 4)            # the address bar still changes
