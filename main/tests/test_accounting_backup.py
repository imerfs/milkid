"""Accounting backup and restore, the safety backups and letters linked to records."""
import gzip
import json
from datetime import date

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse

from main.accounting import backup, bills, letter_links, ledger, yearend
from main.models import (Account, AuditEvent, BackupFile, Bill, Contract, FiscalYear, Letter, LetterLink, Party, Voucher, VoucherLine)
from main.office.errors import Conflict, Forbidden, Invalid
from main.tests.helpers import client_for, isolate_private_media, make_municipality
from main.tests.test_accounting_ledger import LedgerBase, line, make_user


def raw(item):
    with item.file.open('rb') as handle:
        return handle.read()


class BackupBase(LedgerBase):
    def setUp(self):
        self._media_root = isolate_private_media(self)
        super().setUp()
        self.party = Party.objects.create(municipality=self.muni, name='آقای الف')
        self.v1, self.v2 = self.voucher(1000), self.voucher(500, on=date(2025, 6, 1))
        self.bill = bills.issue_bill(self.dehyar, self.year, self.d, self.party, self.tax, 900, 'عوارض')
        bills.record_payment(self.dehyar, self.bill, self.d, 400, self.bank, 'cash')

    def counts(self, muni=None):
        muni = muni or self.muni
        return {model._meta.label: model._base_manager.filter(**{lookup: muni}).count() for model, lookup in backup.tables()
                if model._base_manager.filter(**{lookup: muni}).exists()}


class SnapshotTests(BackupBase):
    def test_the_backup_contains_every_accounting_table_of_the_municipality_only(self):
        other_mayor = make_user('dehyari')
        other = make_municipality(other_mayor)
        Account.objects.create(municipality=other, code='1', title='دیگری', kind='asset', nature='debit')
        data = backup.snapshot(self.muni)
        self.assertEqual(data['municipality'], self.muni.id)
        for label in ('main.Account', 'main.Voucher', 'main.VoucherLine', 'main.Bill', 'main.BillPayment', 'main.Party'):
            self.assertIn(label, data['tables'])
        self.assertTrue(all(o['fields']['municipality'] == self.muni.id for o in data['tables']['main.Account']))
        self.assertNotIn('main.AuditEvent', data['tables'])

    def test_files_are_gzip_with_a_checksum_and_the_list_is_per_municipality(self):
        item = backup.create(self.dehyar, note='آزمون')
        self.assertEqual((item.kind, item.note), ('manual', 'آزمون'))
        content = raw(item)
        self.assertEqual(content[:2], b'\x1f\x8b')
        self.assertEqual(len(content), item.size)
        self.assertEqual(backup.load(content)['rows'], item.rows)
        self.assertEqual(list(backup.backups_for(self.dehyar)), [item])
        other_mayor = make_user('dehyari')
        make_municipality(other_mayor)
        self.assertEqual(list(backup.backups_for(other_mayor)), [])

    def test_prune_keeps_the_newest_automatic_ones_and_all_manual_ones(self):
        manual = backup.create_for(self.muni, kind='manual')
        for _ in range(5):
            backup.create_for(self.muni, kind='auto')
        self.assertEqual(backup.prune(self.muni, keep=2), 3)
        self.assertEqual(BackupFile.objects.filter(kind='auto').count(), 2)
        self.assertTrue(BackupFile.objects.filter(pk=manual.pk).exists())


class RestoreTests(BackupBase):
    def restore(self, item=None, actor=None):
        item = item or backup.create(self.dehyar)
        return backup.restore(actor or self.dehyar, backup.load(raw(item)))

    def test_restoring_brings_back_exactly_what_was_saved(self):
        item = backup.create(self.dehyar)
        before = self.counts()
        ledger.delete_voucher(self.dehyar, self.v2)
        self.voucher(77)
        Party.objects.create(municipality=self.muni, name='تازه')
        self.assertNotEqual(self.counts(), before)
        restored = backup.restore(self.dehyar, backup.load(raw(item)))
        self.assertEqual(self.counts(), before)
        self.assertEqual(restored, sum(before.values()))
        self.assertEqual(Voucher.objects.filter(municipality=self.muni, deleted_at__isnull=True).count(), 3)
        self.assertFalse(Party.objects.filter(name='تازه').exists())

    def test_a_chart_of_accounts_with_parents_is_restored(self):
        group = Account.objects.create(municipality=self.muni, code='501', title='منابع', kind='budget_resource', nature='credit',
                                       is_postable=False)
        child = Account.objects.create(municipality=self.muni, code='5010101002', title='زیرحساب', kind='budget_resource',
                                       nature='credit', parent=group)
        item = backup.create(self.dehyar)
        Account.objects.filter(pk=child.pk).update(parent=None)
        self.restore(item)
        child.refresh_from_db()
        self.assertEqual(child.parent_id, group.pk)

    def test_numbering_continues_after_a_restore(self):
        item = backup.create(self.dehyar)
        self.restore(item)
        again = self.voucher(5)
        self.assertEqual(again.number, Voucher.objects.filter(municipality=self.muni, fiscal_year=self.year).count())
        self.assertEqual(VoucherLine.objects.filter(voucher=again).count(), 2)

    def test_a_safety_backup_is_taken_first(self):
        self.restore()
        self.assertEqual(BackupFile.objects.filter(kind='before_restore').count(), 1)

    def test_other_municipalities_are_untouched(self):
        other_mayor = make_user('dehyari')
        other = make_municipality(other_mayor)
        year = ledger.open_year(other_mayor, 1404)
        theirs = Account.objects.create(municipality=other, code='9', title='دیگری', kind='asset', nature='debit')
        before = self.counts(other)
        self.restore()
        self.assertEqual(self.counts(other), before)
        self.assertTrue(Account.objects.filter(pk=theirs.pk).exists())
        self.assertTrue(FiscalYear.objects.filter(pk=year.pk).exists())

    def test_a_backup_of_another_municipality_is_refused(self):
        other_mayor = make_user('dehyari')
        other = make_municipality(other_mayor)
        ledger.open_year(other_mayor, 1404)
        foreign = backup.snapshot(other)
        before = self.counts()
        with self.assertRaises(Invalid):
            backup.restore(self.dehyar, foreign)
        self.assertEqual(self.counts(), before)

    def test_rows_that_belong_to_somebody_else_abort_the_restore_and_change_nothing(self):
        other_mayor = make_user('dehyari')
        other = make_municipality(other_mayor)
        theirs = Account.objects.create(municipality=other, code='9', title='دیگری', kind='asset', nature='debit')
        data = backup.snapshot(self.muni)
        forged = json.loads(json.dumps(data['tables']['main.Account'][0]))
        forged['pk'] = theirs.pk
        data['tables']['main.Account'].append(forged)
        before = self.counts()
        with self.assertRaises(Conflict):
            backup.restore(self.dehyar, data)
        self.assertEqual(self.counts(), before)
        theirs.refresh_from_db()
        self.assertEqual(theirs.title, 'دیگری')

    def test_a_row_claiming_another_municipality_is_refused(self):
        other_mayor = make_user('dehyari')
        other = make_municipality(other_mayor)
        data = backup.snapshot(self.muni)
        data['tables']['main.Account'][0]['fields']['municipality'] = other.id
        before = self.counts()
        with self.assertRaises(Invalid):
            backup.restore(self.dehyar, data)
        self.assertEqual(self.counts(), before)

    def test_users_deleted_since_the_backup_become_empty_references(self):
        extra = make_user('accountant', city_village=self.muni.city_village)
        voucher = ledger.create_voucher(extra, self.year, self.d, 'income', 'x', [line(self.bank, debit=5), line(self.tax, credit=5)])
        item = backup.create(self.dehyar)
        User.objects.filter(pk=extra.pk).delete()
        self.restore(item)
        voucher.refresh_from_db()
        self.assertIsNone(voucher.created_by_id)

    def test_only_the_mayor_restores_or_deletes(self):
        accountant = make_user('accountant', city_village=self.muni.city_village)
        item = backup.create(accountant)                                            # an accountant may make a copy
        with self.assertRaises(Forbidden):
            backup.restore(accountant, backup.load(raw(item)))
        with self.assertRaises(Forbidden):
            backup.delete(accountant, item)
        backup.delete(self.dehyar, item)
        self.assertFalse(BackupFile.objects.filter(pk=item.pk).exists())

    def test_the_audit_trail_gets_one_summary_event_not_a_row_per_record(self):
        item = backup.create(self.dehyar)
        AuditEvent.objects.all().delete()
        self.restore(item)
        events = AuditEvent.objects.filter(municipality=self.muni)
        self.assertEqual(list(events.values_list('action', flat=True)), ['restore'])

    def test_bad_files_are_refused(self):
        for payload in (b'not a backup', gzip.compress(b'{"format": "other"}'), gzip.compress(b'[]'),
                    gzip.compress(json.dumps({'format': backup.FORMAT, 'version': 1, 'tables': {'main.Nope': []}}).encode())):
            with self.subTest(payload=payload[:12]), self.assertRaises(Invalid):
                backup.load(payload)

    def test_letter_links_survive_and_orphans_are_dropped(self):
        sender = make_user('accountant', city_village=self.muni.city_village)
        letter = Letter.objects.create(sender=sender, village=self.muni.city_village, subject='ن', body='b', status='sent',
                                       year=1404, sequence=1, sent_at=date(2025, 5, 1))
        gone = Letter.objects.create(sender=sender, village=self.muni.city_village, subject='حذف', body='b', status='sent',
                                     year=1404, sequence=2, sent_at=date(2025, 5, 1))
        LetterLink.objects.create(municipality=self.muni, letter=letter, voucher=self.v1)
        LetterLink.objects.create(municipality=self.muni, letter=gone, voucher=self.v2)
        item = backup.create(self.dehyar)
        gone.delete()
        self.restore(item)
        self.assertEqual(list(LetterLink.objects.values_list('letter_id', flat=True)), [letter.id])


class YearEndSafetyBackupTests(BackupBase):
    def test_issuing_a_year_end_voucher_and_closing_the_year_write_safety_backups(self):
        for code, title, kind, nature in (('410', 'مازاد', 'equity', 'credit'),):
            Account.objects.create(municipality=self.muni, code=code, title=title, kind=kind, nature=nature)
        yearend.issue(self.dehyar, self.year, 'temp_closing')
        self.assertEqual(BackupFile.objects.filter(kind='before_yearend').count(), 1)
        for v in Voucher.objects.filter(fiscal_year=self.year, deleted_at__isnull=True):
            ledger.finalize(self.dehyar, v)
        yearend.close_year(self.dehyar, self.year)
        self.assertEqual(BackupFile.objects.filter(kind='before_yearend').count(), 2)


class CommandTests(BackupBase):
    def test_the_command_backs_up_each_municipality_with_accounting_data(self):
        other_mayor = make_user('dehyari')
        make_municipality(other_mayor)                               # no fiscal year: skipped
        call_command('backup_accounting', stdout=open(self._media_root + '/out.txt', 'w'))
        self.assertEqual(list(BackupFile.objects.values_list('municipality_id', 'kind')), [(self.muni.id, 'auto')])
        call_command('backup_accounting', '--municipality', str(self.muni.id), '--keep', '1', stdout=open(self._media_root + '/out.txt', 'w'))
        self.assertEqual(BackupFile.objects.filter(kind='auto').count(), 1)


class BackupScreenTests(BackupBase):
    def setUp(self):
        super().setUp()
        self.client = client_for(self.dehyar)

    def test_tab_create_download_and_restore(self):
        page = self.client.get(reverse('main:acc_panel'), {'year': self.year.id, 'tab': 'backup'})
        self.assertContains(page, 'ساخت نسخه پشتیبان')
        self.assertEqual(self.client.post(reverse('main:acc_p_backup_create'), {'note': 'x'}).status_code, 204)
        item = BackupFile.objects.get()
        download = self.client.get(reverse('main:acc_p_backup_download', args=[item.id]))
        self.assertEqual(download.status_code, 200)
        self.assertEqual(b''.join(download.streaming_content)[:2], b'\x1f\x8b')
        self.voucher(1)
        wrong = self.client.post(reverse('main:acc_p_backup_restore'), {'backup_id': item.id, 'confirm': 'نه'})
        self.assertEqual(wrong.status_code, 400)
        right = self.client.post(reverse('main:acc_p_backup_restore'), {'backup_id': item.id, 'confirm': 'بازیابی'})
        self.assertEqual(right.status_code, 204)
        self.assertEqual(Voucher.objects.filter(municipality=self.muni, deleted_at__isnull=True).count(), 3)      # the extra one is gone

    def test_restore_from_an_uploaded_file_and_a_bad_upload(self):
        item = backup.create(self.dehyar)
        content = raw(item)
        ok = self.client.post(reverse('main:acc_p_backup_restore'), {'confirm': 'بازیابی', 'file': SimpleUploadedFile('b.json.gz', content)})
        self.assertEqual(ok.status_code, 204, ok.get('HX-Trigger'))
        bad = self.client.post(reverse('main:acc_p_backup_restore'), {'confirm': 'بازیابی', 'file': SimpleUploadedFile('b.json.gz', b'junk')})
        self.assertEqual(bad.status_code, 400)

    def test_other_municipalities_and_accountants_cannot_reach_them(self):
        item = backup.create(self.dehyar)
        other_mayor = make_user('dehyari')
        make_municipality(other_mayor)
        self.assertEqual(client_for(other_mayor).get(reverse('main:acc_p_backup_download', args=[item.id])).status_code, 404)
        accountant = client_for(make_user('accountant', city_village=self.muni.city_village))
        denied = accountant.post(reverse('main:acc_p_backup_restore'), {'backup_id': item.id, 'confirm': 'بازیابی'})
        self.assertEqual(denied.status_code, 403)


class LetterLinkTests(BackupBase):
    def setUp(self):
        super().setUp()
        self.accountant = make_user('accountant', city_village=self.muni.city_village)
        self.letter = Letter.objects.create(sender=self.accountant, village=self.muni.city_village, subject='درخواست پرداخت', body='b',
                                            status='sent', year=1404, sequence=1, sent_at=date(2025, 5, 1))

    def test_a_visible_letter_can_be_linked_once_and_unlinked(self):
        link = letter_links.link(self.accountant, self.letter.id, voucher=self.v1)
        self.assertEqual(list(letter_links.links_for(self.accountant, voucher=self.v1)), [link])
        with self.assertRaises(Conflict):
            letter_links.link(self.accountant, self.letter.id, voucher=self.v1)
        letter_links.unlink(self.accountant, link.id)
        self.assertEqual(list(letter_links.links_for(self.accountant, voucher=self.v1)), [])

    def test_somebody_elses_letter_and_drafts_cannot_be_attached(self):
        secret = Letter.objects.create(sender=self.dehyar, village=self.muni.city_village, subject='خصوصی', body='b', status='sent',
                                       year=1404, sequence=2, sent_at=date(2025, 5, 2))
        from main.office.errors import NotFound
        with self.assertRaises(NotFound):
            letter_links.link(self.accountant, secret.id, voucher=self.v1)
        draft = Letter.objects.create(sender=self.accountant, village=self.muni.city_village, subject='پیش‌نویس', body='b')
        with self.assertRaises(Invalid):
            letter_links.link(self.accountant, draft.id, voucher=self.v1)

    def test_records_of_another_municipality_are_refused(self):
        other_mayor = make_user('dehyari')
        other = make_municipality(other_mayor)
        other_year = ledger.open_year(other_mayor, 1404)
        foreign_bank = Account.objects.create(municipality=other, code='1', title='b', kind='asset', nature='debit')
        foreign_tax = Account.objects.create(municipality=other, code='2', title='t', kind='budget_resource', nature='credit')
        foreign = ledger.create_voucher(other_mayor, other_year, self.d, 'income', 'x', [line(foreign_bank, debit=5), line(foreign_tax, credit=5)])
        with self.assertRaises(Invalid):
            letter_links.link(self.accountant, self.letter.id, voucher=foreign)

    def test_the_modal_block_lists_and_changes_links(self):
        client = client_for(self.accountant)
        block = client.get(reverse('main:acc_p_letter_links', args=['voucher', self.v1.id]))
        self.assertContains(block, 'درخواست پرداخت')
        linked = client.post(reverse('main:acc_p_letter_link', args=['voucher', self.v1.id]), {'letter': self.letter.id})
        self.assertContains(linked, reverse('main:letter_detail', args=[self.letter.id]))
        link = LetterLink.objects.get()
        gone = client.post(reverse('main:acc_p_letter_unlink', args=[link.id]))
        self.assertEqual(gone.status_code, 200)
        self.assertFalse(LetterLink.objects.exists())
        self.assertEqual(client.get(reverse('main:acc_p_letter_links', args=['nonsense', 1])).status_code, 404)
        detail = client.get(reverse('main:acc_p_voucher_detail', args=[self.v1.id]))
        self.assertContains(detail, reverse('main:acc_p_letter_links', args=['voucher', self.v1.id]))
