"""Building permit, step 6 (the certificate) and step 7 (the building permit form)."""
from main.models import Notification
from main.office import permit_step6, permit_step7, permits
from main.tests.helpers import client_for, requires_gis_data
from main.tests.test_permit_files import upload
from main.tests.test_permit_step5 import AtStepFive


def cert(**override):
    data = {'number': '7015', 'date': '1405/08/12', 'workshop_no': '5854038341', 'owner': 'علی رضایی', 'area': '135', 'fees_base': '85800000',
            'premium': '10725000', 'slip_no': '5850040418126010', 'slip_date': '1405/08/12', 'cert': [upload('c1.png'), upload('c2.png')]}
    data.update(override)
    return {k: v for k, v in data.items() if v is not None}


class AtStepSix(AtStepFive):
    """Fees paid and the introduction letter issued: the owner brings the certificate."""

    def setUp(self):
        super().setUp()
        self.at_step_six()
        self.pay(self.clerk)
        self.letter()
        self.reload()
        self.assertEqual(self.permit.insurance_state, 'introduced')

    def send_cert(self, who=None, **override):
        return client_for(who or self.citizen).post(self.url('cert_submit'), cert(**override))

    def decide_cert(self, who=None, confirm='on', **override):
        data = {k: v for k, v in cert(**override).items() if k != 'cert'}
        data['confirm'] = confirm
        return client_for(who or self.clerk).post(self.url('cert_verify'), {k: v for k, v in data.items() if v is not None})


@requires_gis_data
class TheCertificate(AtStepSix):
    def test_the_owner_sends_it_and_the_staff_are_told(self):
        self.send_cert()
        permit = self.reload()
        self.assertEqual((permit.insurance_state, permit.stage_no), ('uploaded', 6))
        self.assertEqual(permit.documents.filter(kind='insurance_cert').count(), 2)
        self.assertEqual((permit.insurance['cert']['premium'], permit.insurance['cert']['date']), (10725000, '1405/08/12'))
        self.assertTrue(Notification.objects.filter(user=self.clerk, title='گواهی تامین اجتماعی رسید').exists())
        self.assertEqual(permit.status_text, 'گواهی تامین اجتماعی منتظر تایید')
        self.assertTrue(permit.needs_staff)

    def test_mistakes_save_nothing(self):
        for change in (dict(cert=None), dict(number=''), dict(date='1405/13/40'), dict(premium=''), dict(premium='x'), dict(fees_base=''),
                       dict(slip_no=''), dict(slip_date='bad'), dict(area='abc')):
            self.send_cert(**change)
            self.assertEqual(self.reload().insurance_state, 'introduced', change)

    def test_only_the_owner_sends_it_and_only_once(self):
        for who in (self.clerk, self.neighbour, self.stranger):
            self.send_cert(who)
        self.assertEqual(self.reload().insurance_state, 'introduced')
        self.send_cert()
        self.send_cert(number='999')
        self.assertEqual(self.reload().insurance['cert']['number'], '7015')

    def test_the_system_compares_it_with_the_letter(self):
        self.send_cert(fees_base='1000')
        texts = ' '.join(c['text'] for c in permit_step6.checks(self.reload()))
        self.assertIn('یکی نیست', texts)
        self.assertIn('تکراری نیست', texts)

    def test_the_staff_confirm_and_the_file_moves_to_step_seven(self):
        self.send_cert()
        for who in (self.citizen, self.neighbour, self.stranger, self.officer):
            self.decide_cert(who)
        self.assertEqual(self.reload().stage_no, 6)
        self.decide_cert(confirm=None)
        self.assertEqual(self.reload().stage_no, 6)
        self.decide_cert(premium='10725001')
        permit = self.reload()
        self.assertEqual((permit.stage_no, permit.insurance_state, permit.insurance['cert']['premium']), (7, 'verified', 10725001))
        self.assertTrue(Notification.objects.filter(user=self.citizen, title='گواهی تامین اجتماعی تایید شد').exists())
        self.assertEqual(permit.status_text, 'پروانه در حال تهیه (دهیاری)')

    def test_sending_back_lets_the_owner_upload_again(self):
        self.send_cert()
        client_for(self.clerk).post(self.url('cert_return'), {'notes': ''})
        self.assertEqual(self.reload().insurance_state, 'uploaded')
        client_for(self.clerk).post(self.url('cert_return'), {'notes': 'هولوگرام ناخوانا'})
        self.assertEqual(self.reload().insurance_state, 'returned')
        self.send_cert(number='7016')
        permit = self.reload()
        self.assertEqual((permit.insurance_state, permit.insurance['cert']['number']), ('uploaded', '7016'))
        self.assertEqual(permit.documents.filter(kind='insurance_cert').count(), 2)

    def test_the_payments_stay_frozen(self):
        self.send_cert()
        self.pay(self.clerk, slip_no='88')
        self.assertEqual(len(self.reload().insurance['payments']), 1)

    def test_the_page_shows_each_side_its_part(self):
        owner = client_for(self.citizen).get(self.url('fees')).content.decode()
        self.assertIn('ارسال گواهی به دهیاری', owner)
        self.send_cert()
        staff = client_for(self.clerk).get(self.url('fees')).content.decode()
        self.assertIn('اصل گواهی را دیدم', staff)
        self.assertNotIn('اصل گواهی را دیدم', client_for(self.citizen).get(self.url('fees')).content.decode())


class AtStepSeven(AtStepSix):
    def setUp(self):
        super().setUp()
        self.send_cert()
        self.decide_cert()
        self.reload()
        self.assertEqual(self.permit.stage_no, 7)

    def form(self, **change):
        data = {f'f_{k}': v for k, v in permit_step7.payload(self.permit).items()}
        data.update({f'f_{k}': v for k, v in change.items()})
        return data


@requires_gis_data
class TheLicenceForm(AtStepSeven):
    def test_it_is_filled_from_the_file(self):
        f = permit_step7.payload(self.permit)
        self.assertEqual((f['owner'], f['kind']), ('علی رضایی', 'مسکونی'))
        self.assertEqual((f['fee_slip_no'], f['ins_slip_no'], f['ins_code']), ('005952', '5850040418126010', '5854038341'))
        self.assertEqual((f['sup_name'], f['calc_name']), ('سعید احمدی', 'حسین کریمی'))
        self.assertEqual((f['built_allowed'], f['density_pct']), (135, 60))
        self.assertEqual((f['sd_north_actual'], f['sd_north_passage']), (10.0, 12))
        self.assertEqual((f['fl_ground_count'], f['fl_ground_area'], f['fl_basement_area']), (1, 135, ''))
        self.assertEqual(f['usage'], 'residential')
        self.assertTrue(f['permit_no'])

    def test_the_staff_change_and_save_it(self):
        client_for(self.clerk).post(self.url('licence_save'), self.form(owner='علی رضایی‌نژاد', structure='steel', section='۲ ثبتی بیرجند', usage='junk'))
        f = permit_step7.payload(self.reload())
        self.assertEqual((f['owner'], f['structure'], f['section'], f['usage']), ('علی رضایی‌نژاد', 'steel', '۲ ثبتی بیرجند', ''))

    def test_only_the_staff_edit_it(self):
        for who in (self.citizen, self.neighbour, self.stranger, self.officer):
            client_for(who).post(self.url('licence_save'), self.form(owner='x'))
        self.assertFalse(self.reload().licence)

    def test_issuing_needs_the_tick_and_a_number_and_freezes_the_form(self):
        client_for(self.clerk).post(self.url('licence_issue'), self.form())
        self.assertEqual(self.reload().licence_state, '')
        client_for(self.clerk).post(self.url('licence_issue'), {**self.form(permit_no=''), 'signed': 'on'})
        self.assertEqual(self.reload().licence_state, '')
        client_for(self.citizen).post(self.url('licence_issue'), {**self.form(), 'signed': 'on'})
        self.assertEqual(self.reload().licence_state, '')
        client_for(self.clerk).post(self.url('licence_issue'), {**self.form(permit_no='18/1286', issue_date='1405/08/20'), 'signed': 'on'})
        permit = self.reload()
        self.assertEqual((permit.licence_state, permit.licence_by, permit.licence['f']['permit_no']), ('issued', self.clerk, '18/1286'))
        self.assertEqual(permit.status_text, 'پروانه صادر و تحویل شد')
        self.assertTrue(Notification.objects.filter(user=self.citizen, title='پروانه‌ی ساختمان شما صادر شد').exists())
        client_for(self.clerk).post(self.url('licence_save'), self.form(owner='دیگر'))
        self.assertEqual(self.reload().licence['f']['owner'], 'علی رضایی')

    def test_the_pages(self):
        staff = client_for(self.clerk).get(self.url('licence')).content.decode()
        self.assertIn('name="f_permit_no"', staff)
        self.assertIn('pfl-print', staff)
        owner = client_for(self.citizen).get(self.url('licence')).content.decode()
        self.assertNotIn('pfl-print', owner)
        self.assertIn('امضا و تحویل دستی', owner)
        for who in (self.neighbour, self.stranger):
            self.assertEqual(client_for(who).get(self.url('licence')).status_code, 404)

    def test_not_before_step_seven(self):
        self.permit.stage_no = 6
        self.permit.save()
        self.assertEqual(client_for(self.clerk).get(self.url('licence')).status_code, 302)

    def test_the_staff_panels_count_it_until_it_is_issued(self):
        self.assertEqual(permits.panel_rows(self.clerk)['waiting'], 1)
        client_for(self.clerk).post(self.url('licence_issue'), {**self.form(), 'signed': 'on'})
        self.assertEqual(permits.panel_rows(self.clerk)['waiting'], 0)
