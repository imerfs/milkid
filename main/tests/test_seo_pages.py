import json
import re

from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from main.seo import PAGES
from main.tests.helpers import client_for, make_service, make_user

STATIC_PUBLIC = [n for n in PAGES if n not in ('service_detail', 'property_detail')]


def html(response):
    return response.content.decode()


def meta(page, name):
    m = re.search(r'<meta\s+name="%s"\s+content="([^"]*)"' % name, page)
    return m.group(1) if m else None


def jsonld(page):
    return [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)]


class PublicPageHead(TestCase):
    def pages(self):
        for name in STATIC_PUBLIC:
            response = self.client.get(reverse(f'main:{name}'))
            self.assertEqual(response.status_code, 200, name)
            yield name, html(response)

    def test_each_public_page_has_description_canonical_robots(self):
        for name, page in self.pages():
            description = meta(page, 'description')
            self.assertTrue(description and 50 <= len(description) <= 200, f'{name}: description {description!r}')
            self.assertEqual(meta(page, 'robots'), 'index, follow', name)
            path = reverse(f'main:{name}')
            self.assertIn(f'<link rel="canonical" href="http://testserver{path}">', page, name)
            self.assertIn('property="og:site_name"', page, name)

    def test_descriptions_are_unique(self):
        seen = {}
        for name, page in self.pages():
            d = meta(page, 'description')
            self.assertNotIn(d, seen, f'{name} duplicates {seen.get(d)}')
            seen[d] = name

    def test_titles_are_unique_and_branded(self):
        seen = {}
        for name, page in self.pages():
            title = re.search(r'<title>(.*?)</title>', page, re.S).group(1).strip()
            self.assertTrue(title, name)
            self.assertNotIn(title, seen, f'{name} duplicates {seen.get(title)}')
            seen[title] = name
            self.assertIn('ملک آیدی', title, name)

    def test_exactly_one_h1(self):
        for name, page in self.pages():
            self.assertEqual(len(re.findall(r'<h1\b', page)), 1, name)

    def test_every_image_has_alt(self):
        for name, page in self.pages():
            for img in re.findall(r'<img\b[^>]*>', page):
                self.assertRegex(img, r'\balt="', f'{name}: {img[:80]}')

    def test_favicon_links_present(self):
        for name, page in self.pages():
            self.assertRegex(page, r'<link rel="icon"', name)
            self.assertIn('apple-touch-icon', page, name)


class StructuredData(TestCase):
    def test_home_has_local_business_and_website(self):
        data = jsonld(html(self.client.get(reverse('main:home'))))
        types = [d['@type'] for d in data]
        self.assertIn('LocalBusiness', types)
        self.assertIn('WebSite', types)
        business = next(d for d in data if d['@type'] == 'LocalBusiness')
        self.assertEqual(business['name'], 'ملک آیدی')
        self.assertEqual(business['url'], 'http://testserver/')
        self.assertEqual(business['address']['addressCountry'], 'IR')

    def test_contact_has_local_business(self):
        data = jsonld(html(self.client.get(reverse('main:contact'))))
        self.assertIn('LocalBusiness', [d['@type'] for d in data])

    def test_inner_pages_have_breadcrumb_list(self):
        page = html(self.client.get(reverse('main:services_catalog')))
        crumbs = next(d for d in jsonld(page) if d['@type'] == 'BreadcrumbList')
        names = [i['name'] for i in crumbs['itemListElement']]
        self.assertEqual(names, ['خانه', 'خدمات'])
        self.assertEqual(crumbs['itemListElement'][-1]['item'], 'http://testserver/services/')

    def test_visible_breadcrumb_nav_on_inner_pages(self):
        page = html(self.client.get(reverse('main:about')))
        self.assertIn('aria-label="breadcrumb"', page)
        self.assertIn(reverse('main:home'), page)

    def test_no_phone_published_unless_configured(self):
        data = jsonld(html(self.client.get(reverse('main:home'))))
        business = next(d for d in data if d['@type'] == 'LocalBusiness')
        self.assertNotIn('telephone', business)


class ServiceDetailSeo(TestCase):
    def test_description_service_schema_and_breadcrumbs(self):
        service = make_service(slug='perm')
        page = html(self.client.get(reverse('main:service_detail', args=['perm'])))
        self.assertIn(service.description[:20], meta(page, 'description'))
        self.assertEqual(meta(page, 'robots'), 'index, follow')
        data = jsonld(page)
        self.assertEqual(next(d for d in data if d['@type'] == 'Service')['name'], service.name)
        crumbs = next(d for d in data if d['@type'] == 'BreadcrumbList')['itemListElement']
        self.assertEqual(crumbs[-1]['name'], service.name)
        self.assertEqual(len(re.findall(r'<h1\b', page)), 1)


class PrivatePagesAreNoindex(TestCase):
    def test_logged_in_pages_are_noindex(self):
        user = make_user('citizen')
        for name in ('my_requests', 'notifications', 'dashboard'):
            response = client_for(user).get(reverse(f'main:{name}'), follow=True)
            self.assertEqual(response.status_code, 200, name)
            self.assertEqual(meta(html(response), 'robots'), 'noindex, nofollow', name)

    def test_service_wizard_step_pages_are_noindex(self):
        page = html(self.client.get(reverse('main:building_permit_step2'), follow=True))
        self.assertIn('noindex', meta(page, 'robots') or '')
        # step 1 is the real application form: only a signed-in citizen sees it
        from main.tests.helpers import client_for, make_user
        page = html(client_for(make_user('citizen')).get(reverse('main:building_permit_step1')))
        self.assertIn('noindex', meta(page, 'robots') or '')


class NotFoundPage(TestCase):
    def test_custom_404(self):
        response = self.client.get('/no-such-page-at-all/')
        self.assertEqual(response.status_code, 404)
        page = html(response)
        self.assertIn('404', page)
        self.assertEqual(meta(page, 'robots'), 'noindex, nofollow')
        self.assertEqual(len(re.findall(r'<h1\b', page)), 1)
        self.assertIn(reverse('main:home'), page)
        self.assertIn(reverse('main:services_catalog'), page)


class IconFiles(TestCase):
    def test_all_manifest_and_head_icons_exist(self):
        manifest = json.load(open(finders.find('manifest.json'), encoding='utf-8'))
        for icon in manifest['icons']:
            path = icon['src'].replace('/static/', '', 1)
            self.assertTrue(finders.find(path), f'missing {path}')
        for path in ('icons/favicon.ico', 'icons/favicon.svg', 'icons/apple-touch-icon.png', 'icons/og-image.png'):
            self.assertTrue(finders.find(path), f'missing {path}')

    def test_favicon_ico_redirects_to_static_file(self):
        response = self.client.get('/favicon.ico')
        self.assertEqual(response.status_code, 301)
        self.assertIn('icons/favicon.ico', response['Location'])


class InternalLinks(TestCase):
    def test_footer_links_to_real_service_pages_and_no_placeholders(self):
        service = make_service(slug='footer-svc')
        page = html(self.client.get(reverse('main:about')))
        footer = page[page.index('<footer'):page.index('</footer>')]
        self.assertIn(reverse('main:service_detail', args=[service.slug]), footer)
        self.assertIn(reverse('main:login'), footer)
        self.assertNotIn('/sitemap.xml', footer)  # the XML map is for crawlers (robots.txt), not a link for people
        self.assertNotIn('<li><a href="#"', footer)  # menu items must be real links (social icons are separate)

    def test_home_footer_contact_and_about_are_real_links(self):
        page = html(self.client.get(reverse('main:home')))
        footer = page[page.index('<footer'):]
        self.assertIn(reverse('main:contact'), footer)
        self.assertIn(reverse('main:about'), footer)

    def test_service_page_links_to_catalog_and_related_services(self):
        a, b = make_service(slug='svc-a'), make_service(name='دیگر', slug='svc-b')
        page = html(self.client.get(reverse('main:service_detail', args=[a.slug])))
        self.assertIn(reverse('main:service_detail', args=[b.slug]), page)
        self.assertIn(reverse('main:services_catalog'), page)
