import csv
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from build_expiry import COLUMNS
from sync_expiry_sheet import import_values, HEADERS

class SheetImportTests(unittest.TestCase):
    def snapshot(self, day='12'):
        return [HEADERS,['new-record','9672','東京都競馬','入場券','2026','10',day,'利用期限','leisure','','','2026-10-09','confirmed','','','','','','','user']]
    def master(self,path):
        old={key:'' for key in COLUMNS}
        old.update(id='old-record',code='9672',company_name='東京都競馬',benefit_name='古い券',expiry_date='2026-10-31',research_month='2026-10',expiry_type='利用期限',category='leisure',checked_on='2026-10-05',status='confirmed',verification_method='user')
        with path.open('w',newline='') as out:
            writer=csv.DictWriter(out,fieldnames=COLUMNS);writer.writeheader();writer.writerow(old)
    def test_snapshot_is_idempotent_and_absent_history_does_not_revive(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'master.csv';self.master(path)
            import_values(self.snapshot(),path,'2026-10-09');first=path.read_bytes()
            rows={row['id']:row for row in csv.DictReader(path.read_text().splitlines())}
            self.assertEqual(rows['old-record']['status'],'checking')
            self.assertEqual(rows['new-record']['expiry_date'],'2026-10-12')
            import_values(self.snapshot(),path,'2026-10-10');self.assertEqual(path.read_bytes(),first)
    def test_invalid_date_does_not_replace_original_and_missing_day_stays_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'master.csv';self.master(path);original=path.read_bytes()
            with self.assertRaises(ValueError):import_values(self.snapshot('32'),path,'2026-10-09')
            self.assertEqual(path.read_bytes(),original)
            import_values(self.snapshot(''),path,'2026-10-09')
            rows={row['id']:row for row in csv.DictReader(path.read_text().splitlines())}
            self.assertEqual(rows['new-record']['expiry_date'],'')
