from django.test import TestCase
from django.urls import reverse

from main.models import Announcement, Conversation, Message, Notification
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


class MessagingActions(TestCase):
    def setUp(self):
        self.a = make_user('dehyari')
        self.b = make_user('citizen')
        self.outsider = make_user('citizen')
        self.conv = Conversation.objects.create(subject='موضوع آزمایشی')
        self.conv.participants.add(self.a, self.b)
        Message.objects.create(conversation=self.conv, sender=self.a, body='سلام دنیا')

    def post(self, user, name, *args):
        return client_for(user).post(reverse(f'main:{name}', args=args))

    def test_export_downloads_text_for_participants_only(self):
        resp = client_for(self.b).get(reverse('main:conversation_export', args=[self.conv.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('attachment', resp['Content-Disposition'])
        self.assertIn('سلام دنیا', resp.content.decode())
        self.assertEqual(client_for(self.outsider).get(
            reverse('main:conversation_export', args=[self.conv.id])).status_code, 404)

    def test_mute_toggles_and_suppresses_notifications(self):
        self.assertTrue(self.post(self.b, 'conversation_mute', self.conv.id).json()['is_muted'])
        client_for(self.a).post(reverse('main:conversation_detail', args=[self.conv.id]),
                                {'message_body': 'پیام جدید'})
        self.assertFalse(Notification.objects.filter(user=self.b, notification_type='new_message').exists())
        self.assertFalse(self.post(self.b, 'conversation_mute', self.conv.id).json()['is_muted'])

    def test_archive_hides_from_list_and_shows_in_archive(self):
        self.post(self.b, 'conversation_archive', self.conv.id)
        c = client_for(self.b)
        self.assertNotIn('موضوع آزمایشی', c.get(reverse('main:conversation_list')).content.decode())
        self.assertIn('موضوع آزمایشی', c.get(reverse('main:conversation_list') + '?archived=1').content.decode())
        self.assertIn('موضوع آزمایشی', client_for(self.a).get(reverse('main:conversation_list')).content.decode())

    def test_leave_removes_participant_and_blocks_strangers(self):
        self.assertEqual(self.post(self.outsider, 'conversation_leave', self.conv.id).status_code, 404)
        self.assertTrue(self.post(self.b, 'conversation_leave', self.conv.id).json()['success'])
        self.assertFalse(self.conv.participants.filter(id=self.b.id).exists())

    def test_detail_shows_unmute_label_when_muted(self):
        url = reverse('main:conversation_detail', args=[self.conv.id])
        self.assertIn('بی‌صدا کردن', client_for(self.b).get(url).content.decode())
        self.post(self.b, 'conversation_mute', self.conv.id)
        self.assertIn('فعال کردن اعلان', client_for(self.b).get(url).content.decode())

    def test_actions_require_post(self):
        resp = client_for(self.b).get(reverse('main:conversation_mute', args=[self.conv.id]))
        self.assertEqual(resp.status_code, 405)


class AnnouncementActions(TestCase):
    def setUp(self):
        self.owner = make_user('dehyari')
        self.other = make_user('dehyari')
        self.citizen = make_user('citizen')
        self.ann = Announcement.objects.create(title='اولیه', content='متن', created_by=self.owner, target_roles=[])
        Announcement.objects.create(title='اطلاعیه دیگر', content='x', created_by=self.owner, target_roles=[])
        Announcement.objects.create(title='فقط مهندس', content='x', created_by=self.owner, target_roles=['engineer'])

    def test_owner_can_edit(self):
        url = reverse('main:announcement_edit', args=[self.ann.id])
        self.assertEqual(client_for(self.owner).get(url).status_code, 200)
        resp = client_for(self.owner).post(url, {'title': 'جدید', 'content': 'متن جدید', 'priority': 'high'})
        self.assertEqual(resp.status_code, 302)
        self.ann.refresh_from_db()
        self.assertEqual((self.ann.title, self.ann.priority), ('جدید', 'high'))

    def test_edit_rejects_blank_and_non_owner(self):
        url = reverse('main:announcement_edit', args=[self.ann.id])
        client_for(self.owner).post(url, {'title': '', 'content': 'x'})
        client_for(self.other).post(url, {'title': 'هک', 'content': 'x'})
        self.ann.refresh_from_db()
        self.assertEqual(self.ann.title, 'اولیه')

    def test_delete_deactivates_for_owner_only(self):
        url = reverse('main:announcement_delete', args=[self.ann.id])
        self.assertEqual(client_for(self.other).post(url).status_code, 403)
        self.assertEqual(client_for(self.owner).get(url).status_code, 405)
        self.assertTrue(client_for(self.owner).post(url).json()['success'])
        self.ann.refresh_from_db()
        self.assertFalse(self.ann.is_active)

    def test_detail_lists_related_visible_to_role_only(self):
        page = client_for(self.citizen).get(reverse('main:announcement_detail', args=[self.ann.id])).content.decode()
        self.assertIn('اطلاعیه دیگر', page)
        self.assertNotIn('فقط مهندس', page)
