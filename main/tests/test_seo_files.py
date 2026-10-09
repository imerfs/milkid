import xml.etree.ElementTree as ET

from django.test import TestCase
from django.urls import reverse

from main.tests.helpers import make_ad, make_service


class RobotsTxt(TestCase):
    def test_served_as_plain_text_with_sitemap_and_private_areas_blocked(self):
        r = self.client.get('/robots.txt')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r['Content-Type'].startswith('text/plain'))
        body = r.content.decode()
        self.assertIn('User-agent: *', body)
        for private in ('/admin/', '/dashboard/', '/api/', '/mayor/', '/council/'):
            self.assertIn(f'Disallow: {private}', body)
        self.assertIn('Sitemap: http://testserver/sitemap.xml', body)

    def test_public_pages_are_not_blocked(self):
        lines = self.client.get('/robots.txt').content.decode().splitlines()
        for public in ('/services/', '/properties/', '/about/', '/'):
            self.assertNotIn(f'Disallow: {public}', lines)


class SitemapXml(TestCase):
    def locs(self):
        r = self.client.get('/sitemap.xml')
        self.assertEqual(r.status_code, 200)
        self.assertIn('xml', r['Content-Type'])
        ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        return [e.text for e in ET.fromstring(r.content).findall('s:url/s:loc', ns)]

    def test_lists_public_static_pages(self):
        locs = self.locs()
        for name in ('home', 'about', 'contact', 'services_catalog', 'property_marketplace', 'login', 'register'):
            self.assertIn('http://testserver' + reverse(f'main:{name}'), locs)

    def test_lists_active_services_and_approved_ads_only(self):
        active = make_service(slug='active-one')
        inactive = make_service(name='x', slug='inactive-one', is_active=False)
        approved, pending = make_ad('approved'), make_ad('pending')
        locs = self.locs()
        self.assertIn('http://testserver' + reverse('main:service_detail', args=[active.slug]), locs)
        self.assertNotIn('http://testserver' + reverse('main:service_detail', args=[inactive.slug]), locs)
        self.assertIn('http://testserver' + reverse('main:property_detail', args=[approved.id]), locs)
        self.assertNotIn('http://testserver' + reverse('main:property_detail', args=[pending.id]), locs)

    def test_never_lists_private_pages(self):
        for loc in self.locs():
            for private in ('/dashboard', '/admin', '/api/', '/mayor', '/council', '/my-', '/manage-'):
                self.assertNotIn(private, loc)


class LlmsTxt(TestCase):
    def test_markdown_summary_with_absolute_links(self):
        r = self.client.get('/llms.txt')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r['Content-Type'].startswith('text/plain'))
        body = r.content.decode()
        self.assertTrue(body.startswith('# '))
        self.assertIn('http://testserver/services/', body)
        self.assertIn('http://testserver/sitemap.xml', body)
