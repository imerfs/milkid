"""Construction without a permit, step 4: the technical expert's visit report, the electricity office's answer for an overhang, the materials
in the street, and the confirmation that ends the step."""
from decimal import Decimal

from django.urls import reverse

from main.models import Notification, PermitDocument
from main.office import permit_report, permit_site
from main.tests.helpers import client_for
from main.tests.test_permit_files import PDF, PNG, upload
from main.tests.test_permit_notice import Notice, soon

SIMPLE = ('number', 'date', 'visit_date', 'name', 'father', 'national_id', 'phone', 'land_use', 'status', 'address', 'utm_x', 'utm_y', 'permit_area',
          'permit_date', 'permit_no', 'ruling_area', 'ruling_date', 'ruling_no', 'year', 'roof', 'structure', 'deed_area', 'existing_area', 'after_area',
          'parking_provided', 'notes', 'signer', 'materials_note')


def report_post(permit, actor, **over):
    v = permit_report.data(permit, actor)
    post = {k: v[k] for k in SIMPLE}
    for side, _ in permit_report.SIDES:
        for k in ('adjacent', 'existing', 'passage', 'after'):
            post[f'{side}_{k}'] = v['limits'][side][k]
        for k in ('passage', 'sidewalk', 'balcony', 'network'):
            post[f'oh_{side}_{k}'] = v['overhang_rows'][side][k]
    for key, _ in permit_report.FLOORS:
        for k in permit_report.FLOOR_FIELDS:
            post[f'{key}_{k}'] = v['floors'][key][k]
    post['overhang_built'] = 'built'
    post.update(over)
    return {k: val for k, val in post.items() if val is not None}


class Step4(Notice):
    def setUp(self):
        super().setUp()
        self.send()
        self.decide(self.clerk, confirm='on', number='2/4493', date='1402/10/18', addressee='علی رضایی', position='inside', delivery='handed')
        client_for(self.citizen).post(self.url('permit_visit_request'), {'date': soon(), 'slot': 'morning'})
        client_for(self.engineer).post(self.url('permit_visit_complete'), {'confirm': 'on'})
        self.assertEqual(self.reload().stage_no, 4)

    def fill(self, who=None, url_name='permit_report_file', **over):
        who = who or self.engineer
        return client_for(who).post(self.url(url_name), report_post(self.permit, who, **over), follow=True)

    def act(self, who, name, **data):
        return client_for(who).post(self.url(name), data, follow=True)


class Arithmetic(Step4):
    """The sums of the sheet (the sample «گزارش نهایی 404» with 177.69 and 120.7 m² floors)."""

    def values(self, **over):
        v = permit_report.data(self.permit, self.engineer)
        v['floors']['ground'].update({'units': '1', 'res': '177.69'})
        v['floors']['first'].update({'units': '1', 'res': '120.7'})
        v['existing_area'], v['ruling_area'], v['permit_area'] = '252.28', '278.17', '0'
        v.update(over)
        return v

    def test_floors_total_excess_occupation_and_parking(self):
        t = permit_report.totals(self.values())
        self.assertEqual(t['total'], Decimal('298.39'))
        self.assertEqual(t['excess'], Decimal('298.39') - Decimal('278.17'))
        self.assertEqual(round(t['occupation'], 2), Decimal('70.43'))                  # 177.69 / 252.28
        self.assertTrue(t['separation_ok'])
        self.assertEqual((t['units'], t['parking_needed']), (2, 2))

    def test_the_separation_limit_is_160_square_metres(self):
        self.assertFalse(permit_report.totals(self.values(existing_area='159.99'))['separation_ok'])
        self.assertTrue(permit_report.totals(self.values(existing_area='160'))['separation_ok'])

    def test_two_thirds_of_a_closed_overhang_and_the_small_yard_count_as_built(self):
        v = self.values()
        v['floors']['first'].update({'over_yard': '3', 'yard': '1.5'})
        self.assertEqual(permit_report.totals(v)['floors']['first']['residential'], Decimal('120.7') + 2 + Decimal('1.5'))

    def test_an_overhang_over_the_street_is_what_needs_the_electricity_office(self):
        v = self.values()
        self.assertFalse(permit_report.needs_power(v))
        v['floors']['first']['overhang'] = '8'
        self.assertTrue(permit_report.needs_power(v))
        self.assertEqual(permit_report.totals(v)['overhang_passage'], 8)


class Filling(Step4):
    def test_the_form_is_filled_from_the_file(self):
        page = client_for(self.engineer).get(self.url('permit_report'))
        self.assertEqual(page.status_code, 200)
        v = page.context['v']
        self.assertEqual((v['name'], v['father'], v['national_id'], v['status']), ('علی رضایی', 'حسن', self.permit.people.first().national_id, 'بهره‌برداری'))
        self.assertEqual((v['floors']['ground']['units'], v['floors']['ground']['res']), ('1', '70.28'))      # 70.28 m², one floor, from the filing
        self.assertEqual(v['signer'], self.engineer.username)
        self.assertIn('prp-data', page.content.decode())
        self.assertEqual(v['permit_area'], '0')

    def test_only_the_technical_expert_and_the_dehyari_fill_it(self):
        for who in (self.clerk, self.accountant, self.citizen, self.neighbour, self.stranger_clerk):
            self.fill(who)
            self.assertEqual(self.reload().report_state, '', who.profile.role)
            self.assertEqual(self.reload().report, {}, who.profile.role)
        for who in (self.engineer, self.dehyari):
            self.permit.report_state, self.permit.report = '', {}
            self.permit.save()
            self.fill(who, url_name='permit_report_save')
            self.assertEqual(self.reload().report['name'], 'علی رضایی', who.profile.role)

    def test_a_draft_is_not_shown_to_the_owner_until_it_is_filed(self):
        self.fill(url_name='permit_report_save')
        self.assertFalse(client_for(self.citizen).get(self.url('permit_report')).context['shown'])
        self.assertEqual(self.reload().report_state, '')
        self.fill()
        self.assertEqual(self.reload().report_state, 'filed')
        self.assertTrue(client_for(self.citizen).get(self.url('permit_report')).context['shown'])
        self.assertTrue(Notification.objects.filter(user=self.citizen, title='گزارش بازدید در پرونده‌ی شما است').exists())

    def test_bad_numbers_change_nothing(self):
        for bad in ({'ground_res': 'abc'}, {'ground_res': '-4'}, {'date': '1405/13/40'}, {'name': ''}, {'ground_res': '0', 'first_res': '0'},
                    {'north_existing': '99999999'}):
            self.fill(**bad)
            self.assertEqual(self.reload().report_state, '', bad)

    def test_the_report_is_not_open_before_step_four_and_not_for_other_tracks(self):
        from main.tests.test_permit_files import Village
        permit = Village.filed(self)
        self.assertEqual(client_for(self.engineer).get(reverse('main:permit_report', args=[permit.pk])).status_code, 404)
        for who in (self.neighbour, self.stranger_clerk, self.accountant):
            self.assertEqual(client_for(who).get(self.url('permit_report')).status_code, 404, who.profile.role)

    def test_the_file_page_links_to_it_and_says_what_waits(self):
        page = client_for(self.citizen).get(reverse('main:permit_file', args=[self.permit.pk])).content.decode()
        self.assertIn(self.url('permit_report'), page)
        self.assertEqual(self.permit.status_text, 'منتظر گزارش بازدید (کارشناس فنی)')
        self.assertTrue(self.permit.needs_staff)


class Requirements(Step4):
    def test_nothing_needed_when_the_report_has_no_overhang_and_no_materials(self):
        self.fill()
        permit = self.reload()
        self.assertEqual((permit.overhang_state, permit.materials_state), ('', ''))
        self.assertEqual(permit.status_text, 'گزارش در پرونده است؛ منتظر تایید نهایی مرحله')

    def test_an_overhang_over_the_street_requires_the_electricity_office(self):
        self.fill(first_overhang='8', oh_north_balcony='1.2', oh_north_passage='12', oh_north_network='5')
        permit = self.reload()
        self.assertEqual(permit.overhang_state, 'required')
        self.assertIn('پاسخ اداره برق', permit.status_text)
        power = permit_site.power_payload(permit)
        self.assertEqual(power['rows'][0]['side'], 'شمال')
        self.assertEqual((power['rows'][0]['balcony'], power['rows'][0]['network']), ('1.2', '5'))
        page = client_for(self.citizen).get(self.url('permit_report')).content.decode()
        self.assertIn('نامه‌ی اداره برق', page)

    def test_materials_in_the_street_are_required(self):
        self.fill(materials='on', materials_note='شن و ماسه')
        self.assertEqual(self.reload().materials_state, 'required')
        self.assertIn('عکس جمع‌آوری مصالح', self.reload().status_text)

    def test_refiling_without_the_need_clears_it_unless_already_confirmed(self):
        self.fill(first_overhang='8', materials='on')
        self.assertEqual((self.reload().overhang_state, self.reload().materials_state), ('required', 'required'))
        self.fill(first_overhang='')
        self.assertEqual((self.reload().overhang_state, self.reload().materials_state), ('', ''))


class Electricity(Step4):
    def setUp(self):
        super().setUp()
        self.fill(first_overhang='8')

    def reply(self, who=None, **over):
        data = {'scan': upload('reply.png', PNG), 'letter_no': '1403/77', 'letter_date': '1405/08/01', 'verdict': 'approved', **over}
        data = {k: v for k, v in data.items() if v is not None}
        return client_for(who or self.citizen).post(self.url('permit_power_upload'), data, follow=True)

    def test_the_owner_uploads_the_answer_and_the_staff_confirm(self):
        for bad in ({'scan': None}, {'letter_no': ''}, {'letter_date': '1499/01/01'}, {'letter_date': ''}, {'verdict': 'x'}):
            self.reply(**bad)
            self.assertEqual(self.reload().overhang_state, 'required', bad)
        self.reply(who=self.clerk)
        self.assertEqual(self.reload().overhang_state, 'required')                   # only the owner
        self.reply()
        permit = self.reload()
        self.assertEqual((permit.overhang_state, permit.overhang['letter_no'], permit.overhang['verdict']), ('replied', '1403/77', 'approved'))
        self.assertEqual(PermitDocument.objects.filter(file=permit, kind='power_reply').count(), 1)
        self.assertTrue(Notification.objects.filter(user=self.clerk, title='پاسخ اداره برق رسید').exists())
        self.reply(letter_no='999')                                                 # again: refused
        self.assertEqual(self.reload().overhang['letter_no'], '1403/77')

    def test_each_of_the_three_staff_confirms_and_the_tick_is_needed(self):
        for who in (self.clerk, self.engineer, self.dehyari):
            self.permit.overhang_state = 'required'
            self.permit.save()
            self.reply()
            self.act(who, 'permit_power_verify')
            self.assertEqual(self.reload().overhang_state, 'replied', who.profile.role)       # no tick
            self.act(who, 'permit_power_verify', confirm='on')
            self.assertEqual(self.reload().overhang_state, 'verified', who.profile.role)
            self.assertEqual(self.reload().overhang['checked']['by'], who.username)

    def test_outsiders_cannot_confirm(self):
        self.reply()
        for who in (self.citizen, self.accountant, self.stranger_clerk, self.neighbour):
            self.act(who, 'permit_power_verify', confirm='on')
            self.assertEqual(self.reload().overhang_state, 'replied', who.profile.role)

    def test_sending_back_needs_a_reason_and_the_old_scan_is_kept(self):
        self.reply()
        self.act(self.engineer, 'permit_power_return', notes='')
        self.assertEqual(self.reload().overhang_state, 'replied')
        self.act(self.engineer, 'permit_power_return', notes='نامه ناخوانا است')
        self.assertEqual(self.reload().overhang_state, 'returned')
        old = PermitDocument.objects.get(file=self.permit, kind='power_reply').pk
        self.reply(scan=None, verdict='denied')
        permit = self.reload()
        self.assertEqual((permit.overhang_state, permit.overhang['verdict']), ('replied', 'denied'))
        self.assertEqual(PermitDocument.objects.get(file=permit, kind='power_reply').pk, old)


class Materials(Step4):
    def setUp(self):
        super().setUp()
        self.fill(materials='on')

    def photos(self, who=None, **over):
        data = {'photo': [upload('a.png', PNG), upload('b.png', PNG)], 'cleared': 'on', **over}
        data = {k: v for k, v in data.items() if v is not None}
        return client_for(who or self.citizen).post(self.url('permit_materials_upload'), data, follow=True)

    def test_photos_and_the_tick_are_needed_and_only_the_owner_sends(self):
        self.photos(photo=None)
        self.photos(cleared=None)
        self.photos(photo=[upload('x.pdf', PDF)])                         # photos only
        self.photos(who=self.clerk)
        self.assertEqual(self.reload().materials_state, 'required')
        self.photos()
        permit = self.reload()
        self.assertEqual(permit.materials_state, 'uploaded')
        self.assertEqual(PermitDocument.objects.filter(file=permit, kind='materials_photo').count(), 2)
        self.assertTrue(Notification.objects.filter(user=self.engineer, title='عکس جمع‌آوری مصالح').exists())

    def test_the_staff_confirm_or_send_back(self):
        self.photos()
        self.act(self.dehyari, 'permit_materials_verify')
        self.assertEqual(self.reload().materials_state, 'uploaded')
        self.act(self.engineer, 'permit_materials_return', notes='')
        self.assertEqual(self.reload().materials_state, 'uploaded')
        self.act(self.engineer, 'permit_materials_return', notes='هنوز شن در جوی هست')
        self.assertEqual(self.reload().materials_state, 'returned')
        self.assertIn('هنوز شن در جوی هست', client_for(self.citizen).get(self.url('permit_report')).content.decode())
        self.photos(photo=None)                                          # the old photos stay
        self.assertEqual(self.reload().materials_state, 'uploaded')
        for who in (self.clerk, self.engineer, self.dehyari):
            self.permit.materials_state = 'uploaded'
            self.permit.save()
            self.act(who, 'permit_materials_verify', confirm='on')
            self.assertEqual(self.reload().materials_state, 'verified', who.profile.role)


class Ending(Step4):
    def test_nothing_ends_before_the_report_is_in_the_file(self):
        self.act(self.clerk, 'permit_step4_finish', confirm='on')
        self.assertEqual(self.reload().stage_no, 4)

    def test_each_of_the_three_staff_ends_a_step_with_no_requirements_and_the_tick_is_needed(self):
        self.fill()
        self.act(self.clerk, 'permit_step4_finish')
        self.assertEqual(self.reload().stage_no, 4)
        for who in (self.clerk, self.engineer, self.dehyari):
            self.permit.stage_no = 4
            self.permit.save()
            self.act(who, 'permit_step4_finish', confirm='on', notes='مطابق گزارش')
            self.assertEqual(self.reload().stage_no, 5, who.profile.role)
        self.assertTrue(Notification.objects.filter(user=self.citizen, title='مرحله‌ی ۴ تایید شد').exists())
        self.assertEqual(self.reload().status_text, self.permit.step5_text())
        self.assertIn('منتظر معرفی به کارشناس دادگستری', self.permit.status_text)

    def test_outsiders_cannot_end_it(self):
        self.fill()
        for who in (self.citizen, self.accountant, self.stranger_clerk, self.neighbour):
            self.act(who, 'permit_step4_finish', confirm='on')
            self.assertEqual(self.reload().stage_no, 4, who.profile.role)

    def test_an_outstanding_electricity_answer_or_materials_block_the_end(self):
        self.fill(first_overhang='8', materials='on')
        self.act(self.dehyari, 'permit_step4_finish', confirm='on')
        self.assertEqual(self.reload().stage_no, 4)
        self.assertEqual(permit_site.blocking(self.permit), ['پاسخ اداره برق درباره‌ی پیش‌آمدگی هنوز تایید نشده است.', 'جمع‌آوری مصالح از معبر هنوز تایید نشده است.'])
        client_for(self.citizen).post(self.url('permit_power_upload'), {'scan': upload('r.png', PNG), 'letter_no': '1', 'letter_date': '1405/08/01', 'verdict': 'approved'})
        self.act(self.engineer, 'permit_power_verify', confirm='on')
        self.act(self.dehyari, 'permit_step4_finish', confirm='on')
        self.assertEqual(self.reload().stage_no, 4)                                  # materials still outstanding
        client_for(self.citizen).post(self.url('permit_materials_upload'), {'photo': upload('p.png', PNG), 'cleared': 'on'})
        self.act(self.clerk, 'permit_materials_verify', confirm='on')
        self.assertEqual(permit_site.blocking(self.reload()), [])
        self.act(self.dehyari, 'permit_step4_finish', confirm='on')
        self.assertEqual(self.reload().stage_no, 5)

    def test_waiting_items_count_in_the_staff_lists(self):
        self.assertTrue(self.permit.needs_staff)                                      # the report
        self.fill()
        self.assertTrue(self.reload().needs_staff)                                    # the final confirmation
        self.act(self.dehyari, 'permit_step4_finish', confirm='on')
        self.assertTrue(self.reload().needs_staff)                                    # step 5 starts with the introduction
