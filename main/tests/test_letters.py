import uuid

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from main.models import Letter, LetterAttachment, LetterRecipient, Notification
from main.tests.helpers import client_for, make_municipality, make_user

VILLAGE = 'روستای الف'


class Office(TestCase):
    def setUp(self):
        self.dehyari = make_user('dehyari', city_village=VILLAGE)
        make_municipality(self.dehyari, VILLAGE)
        self.accountant = make_user('accountant', city_village=VILLAGE)
        self.engineer = make_user('engineer', city_village=VILLAGE)
        self.citizen = make_user('citizen', city_village=VILLAGE)
        self.citizen2 = make_user('citizen', city_village=VILLAGE)
        self.stranger = make_user('accountant', city_village='روستای ب')

    def send(self, sender, to, subject='موضوع آزمایشی', body='متن نامه', **extra):
        data = {'to': [u.id for u in to], 'subject': subject, 'body': body, 'action': 'send',
                'token': str(uuid.uuid4()), 'priority': 'normal'}
        data.update(extra)
        return client_for(sender).post(reverse('main:letter_compose'), data)

    def letter(self, **filters):
        return Letter.objects.get(**filters)


class Composing(Office):
    def test_dehyari_sends_to_staff_and_gets_a_number(self):
        r = self.send(self.dehyari, [self.accountant, self.engineer], cc=[self.citizen.id])
        self.assertEqual(r.status_code, 302)
        letter = self.letter(sender=self.dehyari)
        self.assertEqual(letter.status, 'sent')
        self.assertEqual((letter.sequence, letter.village), (1, VILLAGE))
        self.assertEqual(letter.recipients.count(), 3)
        self.assertEqual(letter.recipients.get(user=self.citizen).kind, 'cc')
        self.assertTrue(Notification.objects.filter(user=self.accountant).exists())

    def test_numbers_count_up_per_village_and_year(self):
        self.send(self.dehyari, [self.accountant])
        self.send(self.dehyari, [self.engineer])
        self.assertEqual(list(Letter.objects.order_by('id').values_list('sequence', flat=True)), [1, 2])

    def test_citizens_may_write_to_staff_but_not_to_other_citizens(self):
        self.assertEqual(self.send(self.citizen, [self.dehyari]).status_code, 302)
        self.assertEqual(self.send(self.citizen, [self.citizen2]).status_code, 403)
        self.assertEqual(Letter.objects.filter(sender=self.citizen).count(), 1)

    def test_recipients_of_another_village_are_refused(self):
        self.assertEqual(self.send(self.dehyari, [self.stranger]).status_code, 403)
        self.assertFalse(Letter.objects.exists())

    def test_admin_can_write_anywhere(self):
        admin = make_user('admin')
        self.assertEqual(self.send(admin, [self.stranger]).status_code, 302)

    def test_validation_at_the_boundary(self):
        self.assertEqual(self.send(self.dehyari, [self.accountant], subject='  ').status_code, 400)
        self.assertEqual(self.send(self.dehyari, [self.accountant], body='').status_code, 400)
        self.assertEqual(self.send(self.dehyari, []).status_code, 400)
        self.assertEqual(self.send(self.dehyari, [self.accountant], subject='ا' * 201).status_code, 400)
        self.assertEqual(self.send(self.dehyari, [self.accountant], priority='bogus').status_code, 400)
        self.assertEqual(self.send(self.dehyari, [self.dehyari]).status_code, 400)  # not to yourself
        self.assertFalse(Letter.objects.exists())

    def test_double_submit_creates_one_letter(self):
        token = str(uuid.uuid4())
        for _ in range(3):
            self.send(self.dehyari, [self.accountant], token=token)
        self.assertEqual(Letter.objects.count(), 1)
        self.assertEqual(Notification.objects.filter(user=self.accountant).count(), 1)

    def test_hourly_cap_stops_a_flood(self):
        for _ in range(30):
            self.assertEqual(self.send(self.dehyari, [self.accountant]).status_code, 302)
        self.assertEqual(self.send(self.dehyari, [self.accountant]).status_code, 429)
        self.assertEqual(Letter.objects.count(), 30)

    def test_draft_is_private_until_sent(self):
        self.send(self.dehyari, [self.accountant], action='draft')
        draft = self.letter(sender=self.dehyari)
        self.assertEqual((draft.status, draft.sequence), ('draft', None))
        self.assertEqual(client_for(self.accountant).get(reverse('main:letter_detail', args=[draft.id])).status_code, 404)
        r = client_for(self.dehyari).post(reverse('main:letter_send', args=[draft.id]))
        self.assertEqual(r.status_code, 302)
        draft.refresh_from_db()
        self.assertEqual((draft.status, draft.sequence), ('sent', 1))
        self.assertEqual(client_for(self.dehyari).post(reverse('main:letter_send', args=[draft.id])).status_code, 302)  # idempotent
        self.assertEqual(Letter.objects.get(pk=draft.pk).sequence, 1)

    def test_body_is_escaped(self):
        self.send(self.dehyari, [self.accountant], body='<script>alert(1)</script>')
        letter = self.letter(sender=self.dehyari)
        page = client_for(self.accountant).get(reverse('main:letter_detail', args=[letter.id])).content.decode()
        self.assertNotIn('<script>alert(1)</script>', page)
        self.assertIn('&lt;script&gt;', page)


class Mailboxes(Office):
    def setUp(self):
        super().setUp()
        self.send(self.dehyari, [self.accountant], subject='نامه اول')
        self.letter_obj = Letter.objects.get(subject='نامه اول')

    def page(self, user, name='letters_inbox', **params):
        return client_for(user).get(reverse(f'main:{name}'), params)

    def test_inbox_sent_and_unread_state(self):
        self.assertIn('نامه اول', self.page(self.accountant).content.decode())
        self.assertIn('نامه اول', self.page(self.dehyari, 'letters_sent').content.decode())
        self.assertNotIn('نامه اول', self.page(self.engineer).content.decode())
        row = LetterRecipient.objects.get(user=self.accountant)
        self.assertIsNone(row.read_at)

    def test_opening_marks_read_for_that_recipient_only(self):
        self.send(self.dehyari, [self.accountant, self.engineer], subject='دو گیرنده')
        two = Letter.objects.get(subject='دو گیرنده')
        client_for(self.accountant).get(reverse('main:letter_detail', args=[two.id]))
        self.assertIsNotNone(two.recipients.get(user=self.accountant).read_at)
        self.assertIsNone(two.recipients.get(user=self.engineer).read_at)

    def test_sender_opening_does_not_create_read_receipts(self):
        client_for(self.dehyari).get(reverse('main:letter_detail', args=[self.letter_obj.id]))
        self.assertFalse(LetterRecipient.objects.filter(user=self.dehyari).exists())

    def test_strangers_cannot_open_a_letter_or_its_attachment(self):
        for who in (self.engineer, self.stranger, self.citizen):
            self.assertEqual(client_for(who).get(reverse('main:letter_detail', args=[self.letter_obj.id])).status_code, 404)

    def test_anonymous_is_sent_to_login(self):
        self.assertEqual(self.client.get(reverse('main:letters_inbox')).status_code, 302)

    def test_empty_states(self):
        self.assertIn('نامه‌ای', self.page(self.engineer).content.decode())
        self.assertIn('پیش‌نویسی', self.page(self.engineer, 'letters_drafts').content.decode())

    def test_archive_and_unarchive_by_recipient(self):
        url = reverse('main:letter_archive', args=[self.letter_obj.id])
        client_for(self.accountant).post(url)
        self.assertNotIn('نامه اول', self.page(self.accountant).content.decode())
        self.assertIn('نامه اول', self.page(self.accountant, 'letters_archive').content.decode())
        client_for(self.accountant).post(url)   # toggles back
        self.assertIn('نامه اول', self.page(self.accountant).content.decode())

    def test_only_a_recipient_can_archive(self):
        self.assertEqual(client_for(self.engineer).post(reverse('main:letter_archive', args=[self.letter_obj.id])).status_code, 404)

    def test_unread_filter_and_search(self):
        self.send(self.dehyari, [self.accountant], subject='گزارش مالی')
        client_for(self.accountant).get(reverse('main:letter_detail', args=[Letter.objects.get(subject='گزارش مالی').id]))
        unread = self.page(self.accountant, unread='1').content.decode()
        self.assertIn('نامه اول', unread)
        self.assertNotIn('گزارش مالی', unread)
        found = self.page(self.accountant, q='مالی').content.decode()
        self.assertIn('گزارش مالی', found)
        self.assertNotIn('نامه اول', found)

    def test_confidential_subject_is_masked_in_notifications(self):
        self.send(self.dehyari, [self.engineer], subject='حقوق فلان کارمند', confidential='on')
        for note in Notification.objects.filter(user=self.engineer):
            self.assertNotIn('حقوق فلان', note.title + note.message)


class Replies(Office):
    def test_reply_goes_to_the_sender_and_links_to_the_parent(self):
        self.send(self.dehyari, [self.accountant], subject='گزارش بده')
        parent = Letter.objects.get(subject='گزارش بده')
        r = client_for(self.accountant).post(reverse('main:letter_reply', args=[parent.id]), {
            'subject': 'پاسخ: گزارش بده', 'body': 'ارسال شد', 'action': 'send', 'token': str(uuid.uuid4()),
            'priority': 'normal'})
        self.assertEqual(r.status_code, 302)
        reply = Letter.objects.get(parent=parent)
        self.assertEqual([x.user for x in reply.recipients.all()], [self.dehyari])
        page = client_for(self.dehyari).get(reverse('main:letter_detail', args=[reply.id])).content.decode()
        self.assertIn('گزارش بده', page)

    def test_cannot_reply_to_a_letter_you_cannot_see(self):
        self.send(self.dehyari, [self.accountant])
        parent = Letter.objects.get()
        r = client_for(self.engineer).get(reverse('main:letter_reply', args=[parent.id]))
        self.assertEqual(r.status_code, 404)


class Attachments(Office):
    def pdf(self, name='a.pdf', size=100):
        return SimpleUploadedFile(name, b'%PDF-1.4\n' + b'0' * size, content_type='application/pdf')

    def test_pdf_is_stored_and_downloadable_by_recipient_only(self):
        self.send(self.dehyari, [self.accountant], attachments=[self.pdf()])
        att = LetterAttachment.objects.get()
        self.assertEqual(att.original_name, 'a.pdf')
        r = client_for(self.accountant).get(reverse('main:letter_attachment', args=[att.id]))
        self.assertEqual(r.status_code, 200)
        self.assertIn('attachment', r['Content-Disposition'])
        self.assertEqual(client_for(self.engineer).get(reverse('main:letter_attachment', args=[att.id])).status_code, 404)

    def test_dangerous_types_and_too_many_files_are_refused(self):
        bad = SimpleUploadedFile('virus.exe', b'MZ' + b'0' * 50, content_type='application/octet-stream')
        self.assertEqual(self.send(self.dehyari, [self.accountant], attachments=[bad]).status_code, 400)
        many = [self.pdf(f'{i}.pdf') for i in range(6)]
        self.assertEqual(self.send(self.dehyari, [self.accountant], attachments=many).status_code, 400)
        self.assertFalse(Letter.objects.exists())

    def test_renamed_executable_is_caught_by_content_check(self):
        fake = SimpleUploadedFile('fake.pdf', b'MZ\x90\x00' + b'0' * 50, content_type='application/pdf')
        self.assertEqual(self.send(self.dehyari, [self.accountant], attachments=[fake]).status_code, 400)
