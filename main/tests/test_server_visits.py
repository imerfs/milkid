"""Server panel: visitors and devices, sign-in addresses, the heat map and the all-logs view."""
from django.test import Client, TestCase
from django.urls import reverse

from main import devices, visitstats
from main.models import AuditEvent, SiteVisit
from main.tests.helpers import client_for, make_user

IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
PIXEL = 'Mozilla/5.0 (Linux; Android 14; SM-S911B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'
WINDOWS = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0'


class DeviceNames(TestCase):
    def test_phones_desktops_and_bots(self):
        self.assertEqual(devices.parse(IPHONE)['label'], 'iPhone — Safari · iOS')
        self.assertEqual(devices.parse(PIXEL)['model'], 'SM-S911B')
        self.assertEqual(devices.parse(PIXEL)['kind'], 'mobile')
        self.assertEqual(devices.parse(WINDOWS)['label'], 'Edge · Windows')
        self.assertEqual(devices.parse('Googlebot/2.1')['kind'], 'bot')
        self.assertEqual(devices.parse('')['kind'], 'unknown')


class Recording(TestCase):
    def test_a_page_view_keeps_the_address_and_device(self):
        Client(HTTP_USER_AGENT=PIXEL, HTTP_X_REAL_IP='203.0.113.9').get('/')
        visit = SiteVisit.objects.get()
        self.assertEqual((visit.ip, visit.kind, visit.model_name), ('203.0.113.9', 'mobile', 'SM-S911B'))

    def test_a_sign_in_keeps_the_address_and_device(self):
        from django.contrib.auth.signals import user_logged_in
        from django.test import RequestFactory
        user = make_user('citizen')
        request = RequestFactory().get('/', HTTP_USER_AGENT=WINDOWS, HTTP_X_REAL_IP='198.51.100.4')
        user_logged_in.send(sender=type(user), request=request, user=user)
        event = AuditEvent.objects.get(action='login', username=user.username)
        self.assertEqual(event.ip, '198.51.100.4')
        self.assertTrue(event.summary.endswith('| Edge · Windows'))


class Panel(TestCase):
    def setUp(self):
        SiteVisit.objects.create(ip='203.0.113.9', path='/permits/12/pack/', kind='mobile', device='iPhone — Safari · iOS', model_name='iPhone')
        SiteVisit.objects.create(ip='203.0.113.9', path='/permits/97/pack/', kind='mobile', device='iPhone — Safari · iOS', model_name='iPhone')
        SiteVisit.objects.create(ip='192.0.2.1', path='/', kind='bot', device='ربات / ابزار خودکار')
        AuditEvent.objects.create(action='login', username='ali', ip='203.0.113.9', summary='ورود به سامانه | iPhone — Safari · iOS')
        self.admin = client_for(make_user('admin'))

    def test_the_heat_map_groups_pages_and_skips_bots(self):
        heat = visitstats.heatmap()
        self.assertEqual(heat['total'], 2)
        self.assertEqual(heat['pages'][0]['path'], '/permits/#/pack/')
        self.assertEqual(heat['pages'][0]['count'], 2)
        self.assertEqual(sum(r['total'] for r in heat['rows']), 2)

    def test_visitors_and_logins_list_addresses_and_devices(self):
        v = visitstats.visitors()
        self.assertEqual(v['ips'][0]['ip'], '203.0.113.9')
        self.assertEqual(v['ips'][0]['devices'], ['iPhone — Safari · iOS'])
        self.assertIn('iPhone — Safari · iOS', [e['device'] for e in visitstats.logins()['events'] if e['username'] == 'ali'])

    def test_the_admin_sees_the_new_tabs_and_everyone_else_is_refused(self):
        for tab in ('visitors', 'logins', 'heatmap', 'logs'):
            page = self.admin.get(reverse('main:admin_server') + f'?tab={tab}')
            self.assertEqual(page.status_code, 200, tab)
        self.assertContains(self.admin.get(reverse('main:admin_server') + '?tab=visitors'), '203.0.113.9')
        self.assertContains(self.admin.get(reverse('main:admin_server') + '?tab=logs&file=__all__'), 'همه‌ی گزارش‌ها')
        for role in ('citizen', 'dehyari'):
            self.assertIn(client_for(make_user(role)).get(reverse('main:admin_server') + '?tab=visitors').status_code, (302, 403))
