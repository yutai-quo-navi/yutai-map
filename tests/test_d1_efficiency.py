import json
import pathlib
import sqlite3
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from restore_d1_issuer import read_snapshot
from sync_d1_issuer import validate


class Aggregates(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.executescript((ROOT / 'cloudflare/schema.sql').read_text())
        self.geo('a', 'old', 'brand')
        self.ref('a', 'ref', 'brand')
        self.geo('b', 'protected', 'other')
        self.db.execute("INSERT INTO store_raw VALUES('a','old','{}')")
        self.db.executescript((ROOT / 'cloudflare/migrations/0001_read_budget.sql').read_text())
        self.protected = self.db.execute("SELECT * FROM stores WHERE issuer_id='b'").fetchall()

    def tearDown(self):
        self.db.close()

    def geo(self, issuer, sid, brand):
        self.db.execute('INSERT INTO stores(issuer_id,store_id,name,brand_name,lat,lng,updated_at) VALUES(?,?,?,?,0,0,?)', (issuer,sid,'store',brand,'now'))

    def ref(self, issuer, sid, brand):
        self.db.execute('INSERT INTO reference_stores(issuer_id,store_id,name,brand_name,updated_at) VALUES(?,?,?,?,?)', (issuer,sid,'store',brand,'now'))

    def consistent(self):
        for issuer,geo,ref,raw in self.db.execute('SELECT issuer_id,geo_count,reference_count,raw_count FROM issuer_stats'):
            for table, count in [('stores',geo),('reference_stores',ref),('store_raw',raw)]:
                self.assertEqual(count, self.db.execute(f'SELECT COUNT(*) FROM {table} WHERE issuer_id=?',(issuer,)).fetchone()[0])
        actual=self.db.execute('SELECT issuer_id,brand_name,store_count FROM brand_catalog WHERE store_count>0 ORDER BY 1,2').fetchall()
        expected=self.db.execute("SELECT issuer_id,brand_name,COUNT(*) FROM (SELECT issuer_id,brand_name FROM stores UNION ALL SELECT issuer_id,brand_name FROM reference_stores) WHERE brand_name!='' GROUP BY 1,2 ORDER BY 1,2").fetchall()
        self.assertEqual(actual,expected)
        self.assertEqual(self.protected,self.db.execute("SELECT * FROM stores WHERE issuer_id='b'").fetchall())

    def test_backfill_and_insert_delete_change_representation(self):
        self.consistent()
        self.geo('a','new','newbrand');self.consistent()
        before=self.db.execute("SELECT reference_revision FROM issuer_stats WHERE issuer_id='a'").fetchone()[0]
        self.db.execute("UPDATE reference_stores SET name='changed',brand_name='newbrand' WHERE issuer_id='a'")
        self.assertGreater(self.db.execute("SELECT reference_revision FROM issuer_stats WHERE issuer_id='a'").fetchone()[0],before)
        self.consistent()
        self.db.execute("UPDATE stores SET brand_name='' WHERE issuer_id='a'");self.consistent()
        self.db.execute("DELETE FROM stores WHERE issuer_id='a' AND store_id='old'")
        self.ref('a','old','brand');self.consistent()
        self.db.execute("DELETE FROM reference_stores WHERE issuer_id='a'");self.consistent()
        self.db.execute("DELETE FROM store_raw WHERE issuer_id='a'");self.consistent()

    def test_upsert_and_move_and_rollback(self):
        self.db.execute("INSERT INTO reference_stores(issuer_id,store_id,name,brand_name,updated_at) VALUES('a','ref','changed','new','now') ON CONFLICT(issuer_id,store_id) DO UPDATE SET brand_name=excluded.brand_name")
        self.consistent()
        for table in ['stores','reference_stores','store_raw']:
            self.db.execute(f"UPDATE {table} SET issuer_id='c' WHERE issuer_id='a'")
            self.consistent()
        before=self.db.execute('SELECT * FROM issuer_stats').fetchall()
        self.db.execute('SAVEPOINT trial')
        self.geo('c','temporary','temporary')
        self.db.execute('ROLLBACK TO trial')
        self.assertEqual(before,self.db.execute('SELECT * FROM issuer_stats').fetchall())
        self.consistent()


class PaginationAndScope(unittest.TestCase):
    def test_variable_pages_no_offset_or_truncation(self):
        for size in [0,1,499,500,501,1705,5001]:
            rows=[{'store_id':f'{i:05}', 'raw_json':'{}'} for i in range(size)]
            calls=[]
            def query(sql):
                calls.append(sql)
                if 'issuer_state' in sql: return [{'results':[], 'meta':{}}]
                import re
                match=re.search("store_id>'([^']*)'",sql)
                page=[r for r in rows if not match or r['store_id']>match[1]][:500]
                return [{'results':page,'meta':{}}]
            restored,_,_=read_snapshot('a',query)
            self.assertEqual(rows,restored)
            self.assertEqual(len(calls),size//500+2)
            self.assertTrue(all("issuer_id='a'" in s and 'OFFSET' not in s for s in calls))

    def test_scope_rejects_foreign_or_broad_sql(self):
        validate("DELETE FROM stores WHERE issuer_id='a' AND store_id='o''hare;店';\nINSERT INTO issuer_state (issuer_id,current_meta_json,updated_at) VALUES ('a','{}','now') ON CONFLICT(issuer_id) DO UPDATE SET current_meta_json=excluded.current_meta_json,updated_at=excluded.updated_at;", 'a')
        for sql in ["DELETE FROM stores;", "DELETE FROM stores WHERE issuer_id='b' AND store_id='x';", "DROP TABLE stores;", "INSERT INTO issuer_state (issuer_id,current_meta_json,updated_at) VALUES ('a', (SELECT raw_json FROM store_raw),'now') ON CONFLICT(issuer_id) DO UPDATE SET updated_at=excluded.updated_at;"]:
            with self.assertRaises(ValueError): validate(sql,'a')


class DeploymentRecovery(unittest.TestCase):
    def test_quota_reset_waits_without_database_polling(self):
        import datetime as dt
        from types import SimpleNamespace
        from apply_d1_migrations import apply
        calls, waits = [], []
        def run(*args, **kwargs):
            calls.append(args)
            return SimpleNamespace(returncode=1 if len(calls)==1 else 0, stdout='', stderr='daily row read limit [code: 7500]' if len(calls)==1 else '')
        apply(run=run, sleep=waits.append, now=lambda:dt.datetime(2026,10,9,23,59,50,tzinfo=dt.timezone.utc))
        self.assertEqual(len(calls),2)
        self.assertEqual(sum(waits),30)
        self.assertTrue(all(w<=60 for w in waits))

    def test_other_failure_and_early_day_quota_fail_without_waiting(self):
        import datetime as dt
        from types import SimpleNamespace
        from apply_d1_migrations import apply
        for message in ['syntax error', 'daily row read limit [code: 7500]']:
            waits=[]
            with self.assertRaises(RuntimeError):
                apply(run=lambda *a,**k:SimpleNamespace(returncode=1,stdout='',stderr=message),sleep=waits.append,now=lambda:dt.datetime(2026,10,9,1,0,tzinfo=dt.timezone.utc))
            self.assertEqual(waits,[])
