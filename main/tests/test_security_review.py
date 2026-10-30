"""Regressions from the authorization / request-handling security review."""
import json
import shutil
import tempfile

from django.core.cache import cache
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse

from main.models import Conversation, Payment, RequestDocument
from main.tests.helpers import client_for, make_request, make_user


def _staff(role, village):
    return make_user(role, city_village=village, city_village_name=village)


_MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=_MEDIA)
class CrossVillageStaffScope(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA, ignore_errors=True)

    def setUp(self):
        self.owner = make_user('citizen', city_village='Alpha', city_village_name='Alpha')
        self.sr = make_request(self.owner)
        self.doc = RequestDocument.objects.create(request=self.sr, document_name='id')
        self.doc.document.save('id.txt', ContentFile(b'secret'))

    def download(self, user):
        return client_for(user).get(reverse('main:dashboard_download_document', args=[self.doc.id]))

    def test_staff_of_another_village_cannot_download_document(self):
        self.assertEqual(self.download(_staff('engineer', 'Beta')).status_code, 403)

    def test_staff_of_same_village_and_owner_can_download(self):
        self.assertEqual(self.download(_staff('engineer', 'Alpha')).status_code, 200)
        self.assertEqual(self.download(self.owner).status_code, 200)

    def test_expert_details_api_is_scoped_to_village(self):
        url = reverse('main:api_expert_request_details', args=[self.sr.id])
        self.assertEqual(client_for(_staff('engineer', 'Beta')).get(url).status_code, 404)
        self.assertEqual(client_for(_staff('engineer', 'Alpha')).get(url).status_code, 200)

    def test_foreign_staff_cannot_reject_request(self):
        url = reverse('main:api_expert_reject_request', args=[self.sr.id])
        resp = client_for(_staff('engineer', 'Beta')).post(
            url, json.dumps({'reason': 'x'}), content_type='application/json')
        self.assertEqual(resp.status_code, 404)
        self.sr.refresh_from_db()
        self.assertNotEqual(self.sr.status, 'rejected')


class MethodAndRedirectHardening(TestCase):
    def test_update_status_and_process_payment_refuse_get(self):
        sr = make_request()
        resp = client_for(make_user('dehyari')).get(reverse('main:update_request_status', args=[sr.id]))
        self.assertEqual(resp.status_code, 405)
        self.assertEqual(client_for(make_user('citizen')).get(reverse('main:process_payment', args=[1])).status_code, 405)
        self.assertEqual(Payment.objects.count(), 0)

    def test_switch_municipality_rejects_backslash_open_redirect(self):
        user = make_user('citizen')
        for target in ('/\\evil.example', '//evil.example', 'https://evil.example'):
            resp = client_for(user).post(reverse('main:switch_municipality'), {'next': target})
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(resp['Location'], reverse('main:my_municipality'), target)
        resp = client_for(user).post(reverse('main:switch_municipality'), {'next': '/dashboard/'})
        self.assertEqual(resp['Location'], '/dashboard/')


class MessagingIsolation(TestCase):
    def send_quick(self, sender, recipient, body='hi'):
        return client_for(sender).post(reverse('main:api_send_quick_message'),
                                       json.dumps({'recipient_id': recipient.id, 'message_body': body}),
                                       content_type='application/json')

    def test_quick_message_never_lands_in_a_stranger_conversation(self):
        a, b, c = make_user('citizen'), make_user('citizen'), make_user('citizen')
        self.send_quick(a, b, 'for b')
        # same (empty) display name as a: the old get_or_create-by-subject reused a's conversation
        self.send_quick(c, make_user('citizen'), 'for d')
        self.send_quick(a, c, 'for c')
        convs = {frozenset(conv.participants.values_list('id', flat=True)) for conv in Conversation.objects.all()}
        self.assertIn(frozenset({a.id, b.id}), convs)
        self.assertIn(frozenset({a.id, c.id}), convs)
        for conv in Conversation.objects.all():
            self.assertEqual(conv.participants.count(), 2)
            self.assertEqual(conv.messages.count(), 1)

    def test_related_request_of_a_stranger_is_not_attached(self):
        victim_request = make_request(make_user('citizen'))
        a, b = make_user('citizen'), make_user('citizen')
        client_for(a).post(reverse('main:start_conversation'), {
            'recipient': b.id, 'recipient_id': b.id, 'subject': 's', 'message': 'm', 'body': 'm',
            'message_body': 'm', 'related_request': victim_request.id, 'related_request_id': victim_request.id})
        for conv in Conversation.objects.all():
            self.assertIsNone(conv.related_request_id)


class CityVillageEndpointThrottle(TestCase):
    def test_anonymous_requests_are_rate_limited(self):
        cache.clear()
        url = reverse('main:api_geo_request_city_village')
        codes = [client_for().post(url, json.dumps({'name': 'x'}), content_type='application/json').status_code
                 for _ in range(12)]
        self.assertEqual(codes[-1], 429)
        self.assertNotIn(429, codes[:10])
        cache.clear()
