import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from build_expiry import COLUMNS, ROOT, candidates, load_master, public_document, x_draft


class ExpiryTests(unittest.TestCase):
    def row(self, **changes):
        r = dict.fromkeys(COLUMNS, '')
        r.update(id='skylark-2026-a', code='3197', company_name='すかいらーく', benefit_name='食事券',
                 issue='2025年12月権利分', expiry_date='2026-09-30', research_month='2026-09',
                 expiry_type='利用期限', category='dining', source_url='https://example.com/official',
                 checked_on='2026-09-01', status='confirmed', issuer_id='skylark')
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

    def test_committed_json_matches_master_and_atom_correction(self):
        rows = load_master(ROOT / 'data/expiry_master.csv')
        self.assertEqual(json.loads((ROOT / 'data/expiry.json').read_text()), public_document(rows))
        atom = [r for r in rows if r['code'] == '7412']
        self.assertEqual([r['research_month'] for r in atom], ['2026-12'])


if __name__ == '__main__':
    unittest.main()
