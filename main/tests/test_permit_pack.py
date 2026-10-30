"""Construction without a permit, step 9: the package of forms, the owner's undertaking and the property undertaking uploaded and confirmed."""
from django.urls import reverse

from main.models import Notification, PermitDocument
from main.office import permit_pack
from main.tests.helpers import client_for
from main.tests.test_permit_bonyad import Step8
from main.tests.test_permit_files import PNG, upload


class Step9(Step8):
    def setUp(self):
        super().setUp()
        self.permit.bonyad_list_state = 'verified'
        self.permit.save()
        self.act(self.dehyari, 'permit_step8_finish', confirm='on')
        self.assertEqual(self.reload().stage_no, 9)

    def commit(self, who=None, **post):
        return client_for(who or self.citizen).post(self.url('permit_pack_commit'), post, follow=True)

    def send_deed(self, who=None, **over):
        post = {'deed': upload('deed.png', PNG)}
        post.update(over)
        return client_for(who or self.citizen).post(self.url('permit_pack_upload'), post, follow=True)


class Package(Step9):
    def test_the_status_and_stage_name(self):
        self.assertEqual(self.permit.status_text, 'منتظر تعهد مالک و تعهدنامه‌ی ملک (از متقاضی)')
        self.assertEqual(self.permit.stage_title, 'بسته‌ی فرم‌ها و تعهدنامه‌ی ملک')

    def test_the_package_lists_every_form_and_paper(self):
        titles = [i['title'] for i in permit_pack.items(self.permit)]
        for name in ('فرم درخواست و تعهدنامه', 'تعهد بهداشتی', 'فرم دفاعیه', 'اخطاریه', 'رضایت همسایگان', 'مدارک مالی', 'محضر و جوابیه‌ی کارشناس دادگستری'):
            self.assertIn(name, titles)

    def test_the_page_and_the_health_undertaking_open_for_the_owner_and_the_three_staff(self):
        for who in (self.citizen, self.clerk, self.engineer, self.dehyari):
            self.assertEqual(client_for(who).get(self.url('permit_pack')).status_code, 200, who.profile.role)
            page = client_for(who).get(self.url('permit_pack_health'))
            self.assertEqual(page.status_code, 200, who.profile.role)
            self.assertContains(page, 'علی رضایی')
        for who in (self.neighbour, self.stranger_clerk):
            self.assertEqual(client_for(who).get(self.url('permit_pack')).status_code, 404, who.profile.role)
            self.assertEqual(client_for(who).get(self.url('permit_pack_health')).status_code, 404, who.profile.role)


class Undertaking(Step9):
    def test_only_the_owner_commits_and_the_tick_is_needed(self):
        self.commit()
        self.assertEqual(self.reload().pack_state, '')
        for who in (self.clerk, self.dehyari, self.neighbour):
            self.commit(who, confirm='on')
            self.assertEqual(self.reload().pack_state, '', who.profile.role)
        self.commit(confirm='on')
        self.assertEqual(self.reload().pack_state, 'committed')
        self.assertIn('تعهدنامه‌ی ملک', self.permit.status_text)

    def test_the_deed_waits_for_the_undertaking_and_needs_a_file(self):
        self.send_deed()
        self.assertEqual(self.reload().pack_state, '')
        self.commit(confirm='on')
        self.send_deed(deed='')
        self.assertEqual(self.reload().pack_state, 'committed')
        self.send_deed(who=self.neighbour)
        self.assertEqual(self.reload().pack_state, 'committed')
        self.send_deed()
        self.assertEqual(self.reload().pack_state, 'uploaded')
        self.assertEqual(PermitDocument.objects.filter(file=self.permit, kind='property_deed').count(), 1)

    def test_a_returned_deed_is_uploaded_again_and_then_confirmed_by_any_of_the_three(self):
        for who in (self.clerk, self.engineer, self.dehyari):
            self.permit.pack_state = 'committed'
            self.permit.save()
            self.send_deed()
            client_for(who).post(self.url('permit_pack_return'), {'notes': ''}, follow=True)
            self.assertEqual(self.reload().pack_state, 'uploaded', who.profile.role)
            client_for(who).post(self.url('permit_pack_return'), {'notes': 'ناخوانا'}, follow=True)
            self.assertEqual(self.reload().pack_state, 'returned', who.profile.role)
            self.send_deed()
            self.assertEqual(self.reload().pack_state, 'uploaded')
            client_for(who).post(self.url('permit_pack_verify'), {}, follow=True)
            self.assertEqual(self.reload().pack_state, 'uploaded', who.profile.role)
            client_for(who).post(self.url('permit_pack_verify'), {'confirm': 'on'}, follow=True)
            self.assertEqual(self.reload().pack_state, 'verified', who.profile.role)

    def test_the_owner_cannot_confirm_and_the_step_ends_only_after_the_deed_is_confirmed(self):
        self.act(self.dehyari, 'permit_step9_finish', confirm='on')
        self.assertEqual(self.reload().stage_no, 9)
        self.commit(confirm='on')
        self.send_deed()
        client_for(self.citizen).post(self.url('permit_pack_verify'), {'confirm': 'on'}, follow=True)
        self.assertEqual(self.reload().pack_state, 'uploaded')
        self.act(self.dehyari, 'permit_step9_finish', confirm='on')
        self.assertEqual(self.reload().stage_no, 9)
        client_for(self.engineer).post(self.url('permit_pack_verify'), {'confirm': 'on'}, follow=True)
        self.act(self.dehyari, 'permit_step9_finish')
        self.assertEqual(self.reload().stage_no, 9)
        for who in (self.citizen, self.neighbour, self.stranger_clerk):
            self.act(who, 'permit_step9_finish', confirm='on')
            self.assertEqual(self.reload().stage_no, 9, who.profile.role)
        for who in (self.clerk, self.engineer, self.dehyari):
            self.permit.stage_no = 9
            self.permit.save()
            self.act(who, 'permit_step9_finish', confirm='on')
            self.assertEqual(self.reload().stage_no, 10, who.profile.role)
        self.assertTrue(Notification.objects.filter(user=self.citizen, title='مرحله‌ی ۹ تایید شد').exists())

    def test_the_urls_exist(self):
        self.assertTrue(reverse('main:permit_pack', args=[self.permit.pk]))
