import importlib.util
import json
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('scraper', Path(__file__).resolve().parents[1] / 'tools/features/scrape_balnibarbi.py')
scraper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scraper)
TODAY = date(2026, 10, 7)


class BalnibarbiFeatureTests(unittest.TestCase):
    def fixture(self, changes=None):
        rows = {str(i):dict(_typeKey='restaurants', basename=f'shop_{i}', title=f"店'{i}",
            address='東京都千代田区1-1', latitude='35.68', longitude='139.76', shareholder='対応',
            hide='0', openstatus='オープン', open='2020年1月1日', close='') for i in range(100)}
        for i, change in (changes or {}).items():
            rows[str(i)].update(change)
        listing = ''.join(f'<li class="shop-item"><a href="/brands/restaurants/shop_{i}">店{i}</a></li>' for i in range(100))
        return listing, 'window.brandsMapData = ' + json.dumps({'shopdata':rows}) + ';'

    def test_eligibility_closure_future_opening_and_hidden(self):
        listing, mapped = self.fixture({0:{'shareholder':'対応しておりません'},
            1:{'shareholder':'店舗により対応'}, 2:{'shareholder':''}, 3:{'openstatus':'休業中'},
            4:{'close':'2026年9月30日'}, 5:{'open':'2026年11月20日'}, 6:{'hide':'1'}})
        snapshot = scraper.build_snapshot(listing, mapped, today=TODAY)
        self.assertEqual(len(snapshot['stores']), 93)
        self.assertEqual(snapshot['checkedOn'], '2026-10-07')

    def test_missing_map_shop_uses_detail_and_pin_coordinate(self):
        listing, mapped = self.fixture()
        listing += '<li class="shop-item"><a href="/brands/restaurants/new_shop">新店</a></li>'
        detail = '<h1>新店</h1><dt>株主優待</dt><dd>対応</dd><dt>住所</dt><dd>東京都1-1</dd><iframe src="https://www.google.com/maps/embed?pb=!2d139.7!3d35.6!3d35.61!4d139.71"></iframe>'
        with patch.object(scraper.time, 'sleep'):
            snapshot = scraper.build_snapshot(listing, mapped, lambda _:detail, TODAY)
        self.assertEqual(len(snapshot['stores']), 101)
        self.assertEqual(snapshot['stores'][-1]['lat'], 35.61)
        self.assertEqual(snapshot['stores'][-1]['lng'], 139.71)

    def test_structure_change_and_invalid_geo_fail_closed(self):
        with self.assertRaises(ValueError):
            scraper.parse_map('<html>No data</html>')
        listing, mapped = self.fixture({0:{'latitude':'nan'}})
        with self.assertRaises(ValueError):
            scraper.build_snapshot(listing, mapped, today=TODAY)
        with self.assertRaises(ValueError):
            scraper.parse_detail('<h1>Unknown</h1>', '/brands/restaurants/unknown', TODAY)

    def test_large_drop_and_listing_closure(self):
        listing, mapped = self.fixture({i:{'shareholder':'対応しておりません'} for i in range(30)})
        with self.assertRaises(ValueError):
            scraper.build_snapshot(listing, mapped, today=TODAY)
        self.assertTrue(scraper.inactive('5/6にて営業終了', TODAY))
        self.assertTrue(scraper.inactive('2026年12月1日オープン', TODAY))
        self.assertFalse(scraper.inactive('2026年6月18日オープン', TODAY))

    def test_normal_dining_sync_excludes_hotels_and_preserves_other_issuers(self):
        snapshot = scraper.build_snapshot(*self.fixture(), today=TODAY)
        snapshot['stores'] += [{**snapshot['stores'][0], 'id':kind+'-extra'} for kind in ['hotels','facilities','shops']]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'snapshot.sql'
            scraper.write_sql(snapshot, output)
            db = sqlite3.connect(':memory:')
            db.executescript(output.read_text())
            self.assertEqual(db.execute("SELECT COUNT(*) FROM stores WHERE issuer_id='balnibarbi'").fetchone()[0], 101)
            db.execute("INSERT INTO stores (issuer_id,store_id,name,lat,lng,updated_at) VALUES ('royal','keep','keep',35,139,'today')")
            snapshot['stores'] = snapshot['stores'][1:]
            scraper.write_sql(snapshot, output)
            db.executescript(output.read_text())
            self.assertEqual(db.execute("SELECT COUNT(*) FROM stores WHERE issuer_id='balnibarbi'").fetchone()[0], 100)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM stores WHERE issuer_id='royal'").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM stores WHERE store_id LIKE 'hotels-%' OR store_id LIKE 'facilities-%'").fetchone()[0], 0)

    def test_upsert_sql_handles_apostrophe_and_replaces_only_feature(self):
        snapshot = scraper.build_snapshot(*self.fixture(), today=TODAY)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'snapshot.sql'
            scraper.write_sql(snapshot, output)
            db = sqlite3.connect(':memory:')
            db.executescript(output.read_text())
            db.executescript(output.read_text())
            self.assertEqual(db.execute('SELECT COUNT(*) FROM feature_snapshots').fetchone()[0], 1)
            payload = json.loads(db.execute('SELECT payload_json FROM feature_snapshots').fetchone()[0])
            self.assertEqual(payload['stores'][0]['name'], "店'0")


if __name__ == '__main__':
    unittest.main()
