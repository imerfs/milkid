from django.test import TestCase
from django.urls import reverse

from main.models import Announcement
from main.tests.helpers import client_for, make_user


class MessagingPagesDoNotCrash(TestCase):
    def setUp(self):
        self.admin = make_user('admin')
        self.citizen = make_user('citizen')
        Announcement.objects.create(title='برای همه', content='x', created_by=self.admin, target_roles=[])
        Announcement.objects.create(title='فقط دهیار', content='x', created_by=self.admin, target_roles=['dehyari'])
        Announcement.objects.create(title='شهروندان', content='x', created_by=self.admin, target_roles=['citizen'])

    def test_dashboard_and_announcement_list_filter_by_role(self):
        for name in ('messaging_dashboard', 'announcement_list'):
            page = client_for(self.citizen).get(reverse(f'main:{name}'))
            self.assertEqual(page.status_code, 200, name)
        listed = client_for(self.citizen).get(reverse('main:announcement_list')).content.decode()
        self.assertIn('برای همه', listed)
        self.assertIn('شهروندان', listed)
        self.assertNotIn('فقط دهیار', listed)
