import csv
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from build_expiry import COLUMNS, ROOT, candidates, load_master, public_document, x_draft
from edit_expiry import select_record
import edit_expiry


class ExpiryTests(unittest.TestCase):
    def test_manual_feature_issuer_can_use_shared_expiry_ledger(self):
        rows = self.load([self.row(code='9616', issuer_id='kyoritsu', company_name='共立メンテナンス')])
        self.assertEqual(rows[0]['issuer_id'], 'kyoritsu')
        with self.assertRaises(ValueError):
            self.load([self.row(code='9615', issuer_id='kyoritsu')])

    def row(self, **changes):
        r = dict.fromkeys(COLUMNS, '')
        r.update(id='skylark-2026-a', code='3197', company_name='すかいらーく', benefit_name='食事券',
                 issue='2025年12月権利分', expiry_date='2026-09-30', research_month='2026-09',
                 expiry_type='利用期限', category='dining', source_url='https://example.com/official',
                 checked_on='2026-09-01', status='confirmed', issuer_id='skylark', verification_method='official')
        r.update(changes)
        return r

    def load(self, rows):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'master.csv'
            with p.open('w', encoding='utf-8-sig', newline='') as f:
                w = csv.DictWriter(f, fieldnames=COLUMNS); w.writeheader(); w.writerows(rows)
            return load_master(p)

    def test_filter_preserves_history_without_publishing_candidates(self):
        rows = self.load([self.row(), self.row(id='candidate', code='7412', issuer_id='', expiry_date='', research_month='2026-12', status='checking')])
        self.assertEqual([r['id'] for r in public_document(rows)['entries']], ['skylark-2026-a'])

    def test_confirmed_needs_date_source_issue_and_check(self):
        for field in ['expiry_date', 'source_url', 'issue', 'checked_on']:
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.load([self.row(**{field:''})])

    def test_reject_invalid_date_duplicate_and_wrong_issuer(self):
        for rows in [[self.row(expiry_date='2026-09-31')], [self.row(), self.row(id='another')], [self.row(issuer_id='colowide')], [self.row(source_url='javascript:alert(1)')], [self.row(research_month='2026-08')]]:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.load(rows)

    def test_normalization_and_csv_quoting(self):
        rows = self.load([self.row(code='３１９７', brands='ガスト|ガスト|バーミヤン', notes='説明,補足\n改行')])
        self.assertEqual(rows[0]['code'], '3197')
        self.assertEqual(rows[0]['brands'], ['ガスト', 'バーミヤン'])
        self.assertEqual(rows[0]['notes'], '説明,補足\n改行')

    def test_x_draft_has_date_type_issue_and_only_confirmed(self):
        rows = self.load([self.row(), self.row(id='catalog',code='3003',issuer_id='',benefit_name='カタログ',category='catalog',expiry_type='申込期限',expiry_date='2026-09-27'), self.row(id='hidden',code='7412',issuer_id='',status='checking')])
        draft = x_draft(rows, '2026-09')
        self.assertIn('9/27 申込期限', draft)
        self.assertIn('2025年12月権利分', draft)
        self.assertNotIn('7412', draft)
        end = x_draft(rows, '2026-09', month_end=True)
        self.assertIn('3197', end); self.assertNotIn('3003', end)

    def test_previous_year_candidates_not_inferred_current_facts(self):
        rows = self.load([self.row(), self.row(id='unverified', code='7412', issuer_id='', status='checking')])
        previous = candidates(rows, '2027-09')
        self.assertIn('3197', previous); self.assertIn('checking', previous)
        self.assertNotIn('3197', x_draft(rows, '2027-09'))

    def test_user_approval_can_confirm_month_without_fabricating_day(self):
        rows = self.load([self.row(verification_method='user', expiry_date='', source_url='', issue='')])
        self.assertEqual(len(public_document(rows)['entries']), 1)
        self.assertIn('9月（日付未登録）', x_draft(rows, '2026-09'))
        self.assertNotIn('3197', x_draft(rows, '2026-09', month_end=True))

    def test_legacy_baseline_is_readable_after_schema_extension(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'baseline.csv'
            with p.open('w', encoding='utf-8', newline='') as f:
                w = csv.DictWriter(f, fieldnames=COLUMNS[:-1]); w.writeheader()
                row = self.row(); row.pop('verification_method'); w.writerow(row)
            self.assertEqual(load_master(p, allow_legacy=True)[0]['verification_method'], 'official')

    def test_corrections_stay_in_same_year_and_next_year_is_new(self):
        rows = self.load([self.row()])
        self.assertEqual(select_record(rows, '3197', '2026-11')['id'], 'skylark-2026-a')
        self.assertIsNone(select_record(rows, '3197', '2027-11'))
        with self.assertRaises(ValueError):
            select_record(rows, '3197', '2027-11', 'skylark-2026-a')
        self.assertEqual(public_document(rows)['entries'][0]['expiry_year'], 2026)

    def test_easy_edit_regenerates_json_and_preserves_brands_and_previous_year(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root / 'data/issuers').mkdir(parents=True)
            (root / 'data/issuers/index.json').write_text((ROOT / 'data/issuers/index.json').read_text())
            master = root / 'data/expiry_master.csv'
            with master.open('w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=COLUMNS); writer.writeheader(); writer.writerow(self.row(brands='ガスト|バーミヤン'))
            with patch.object(edit_expiry, 'ROOT', root), patch.object(sys, 'argv', ['edit', '--code','3197','--month','2026-11']):
                edit_expiry.main()
            rows = load_master(master)
            self.assertEqual(rows[0]['id'], 'skylark-2026-a')
            self.assertEqual(rows[0]['brands'], ['ガスト','バーミヤン'])
            self.assertEqual(rows[0]['expiry_date'], '')
            with patch.object(edit_expiry, 'ROOT', root), patch.object(sys, 'argv', ['edit','--code','3197','--date','2027-11-30']):
                edit_expiry.main()
            rows = load_master(master)
            self.assertEqual([r['research_month'] for r in rows], ['2026-11','2027-11'])
            self.assertEqual(json.loads((root / 'data/expiry.json').read_text()), public_document(rows))

    def test_committed_json_matches_master_and_atom_correction(self):
        rows = load_master(ROOT / 'data/expiry_master.csv')
        self.assertEqual(json.loads((ROOT / 'data/expiry.json').read_text()), public_document(rows))
        atom = [r for r in rows if r['code'] == '7412']
        self.assertEqual([r['research_month'] for r in atom], ['2026-12'])


if __name__ == '__main__':
    unittest.main()
