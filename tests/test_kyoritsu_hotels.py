import importlib.util
import json
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

spec = importlib.util.spec_from_file_location('kyoritsu', Path(__file__).resolve().parents[1] / 'tools/features/scrape_kyoritsu_hotels.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)
TODAY = date(2026, 10, 7)
POLICY = '株主様ご優待割引 株主様リゾートホテルご優待 現地払い 事前決済 ドーミーイン、御宿 野乃は対象外'
MAP = '<iframe src="https://www.google.com/maps/embed?pb=!2d139.7!3d35.6!3d35.61!4d139.71"></iframe>'


def resort(alias, partner=False, summary=''):
    url = 'https://www.tenger.jp/' if partner else f'https://dormy-hotels.com/resort/hotels/{alias}/'
    return f'<li class="cate1 {"partner" if partner else ""}"><p class="name">ホテル{alias}</p><address>東京都1-1</address><p>{summary}</p><a href="{url}">施設サイト</a></li>'


def dormy(rows):
    links = ''.join(f'<li><a href="https://dormy-hotels.com/dormyinn/hotels/{r["r.url_alias"]}/">ホテル詳細</a></li>' for r in rows)
    return links + '<script>var jsonData = ' + json.dumps(rows) + ';</script>'


class KyoritsuHotelsTests(unittest.TestCase):
    def test_resort_partner_future_and_closed_are_separated(self):
        doc = resort('one') + resort('partner', True) + resort('future', summary='2026年11月オープン') + resort('closed', summary='休業中')
        rows = s.parse_resorts(doc, TODAY)
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[0]['resortPlan'])
        self.assertFalse(rows[1]['resortPlan'])
        self.assertTrue(s.future_opening('2026.11.01 NEW', TODAY))

    def test_dormy_domestic_only_and_prefecture_address(self):
        rows = [{'r.state':13, 'r.hotel_name':'御宿 野乃', 'r.address':'台東区1-1', 'r.url_alias':'nono'},
                {'r.state':None, 'r.hotel_name':'SEOUL', 'r.address':'Korea', 'r.url_alias':'seoul'}]
        result = s.parse_dormy(dormy(rows), TODAY)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['address'], '東京都台東区1-1')
        self.assertFalse(result[0]['resortPlan'])
        with self.assertRaises(ValueError):
            s.parse_dormy(dormy([{**rows[0], 'r.state':100}]), TODAY)

    def test_coordinates_prefer_pin_and_label_viewport_approximation(self):
        self.assertEqual(s.parse_coordinates(MAP)['lat'], 35.61)
        viewport = s.parse_coordinates('<iframe src="https://www.google.com/maps/embed?pb=!2d139.7!3d35.6"></iframe>')
        self.assertIn('目安', viewport['coordinateNote'])
        for source in ['', '<iframe src="https://www.google.com/maps/embed?pb=!3d-33!4d151"></iframe>']:
            with self.assertRaises(ValueError): s.parse_coordinates(source)

    def test_official_main_page_fallback_and_exact_supplement_match(self):
        hotel = {'id':'one', 'name':'Hotel', 'address':'東京都1-1', 'sourceUrl':'https://example.com/', 'coordinateUrl':'https://example.com/access/'}
        def fetch(url):
            if url.endswith('access/'): raise HTTPError(url, 404, 'missing', {}, None)
            return MAP
        self.assertEqual(s.hotel_coordinates(hotel, fetch)['lat'], 35.61)
        extra = {'one':{'name':'Hotel','address':'東京都1-1','lat':35.61,'lng':139.71,'coordinateSource':'OpenPOI API'}}
        self.assertEqual(s.hotel_coordinates(hotel, lambda _: '', extra)['coordinateSource'], 'OpenPOI API')
        extra['one']['preferSupplement'] = True
        self.assertEqual(s.hotel_coordinates(hotel, lambda _: MAP, extra)['coordinateSource'], 'OpenPOI API')
        with self.assertRaises(ValueError): s.hotel_coordinates({**hotel,'address':'新住所'}, lambda _: '', extra)
        self.assertIn('ホテル', s.decode_document('<meta charset="euc-jp">ホテル'.encode('euc-jp')))

    def test_complete_snapshots_use_different_eligibility_and_atomic_sql(self):
        resort_html = ''.join(resort(f'r{i}') for i in range(40)) + resort('partner', True)
        rows = [{'r.state':13,'r.hotel_name':f"ホテル'{i}",'r.address':'千代田区1-1','r.url_alias':f'd{i}'} for i in range(100)]
        with patch.object(s.time, 'sleep'):
            result = s.build_snapshots(POLICY, resort_html, dormy(rows), lambda _:MAP, TODAY)
        self.assertEqual([len(x['stores']) for x in result], [141,40])
        self.assertTrue(all(x['hotelGroup']=='共立リゾート' for x in result[1]['stores']))
        self.assertIn('現地払い',result[0]['stores'][0]['conditions'])
        self.assertIn('事前予約',result[1]['stores'][0]['conditions'])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'sync.sql';s.write_sql(result, output)
            db = sqlite3.connect(':memory:');db.executescript(output.read_text());db.executescript(output.read_text())
            self.assertEqual(db.execute('SELECT COUNT(*) FROM feature_snapshots').fetchone()[0],2)
            self.assertEqual(json.loads(db.execute('SELECT payload_json FROM feature_snapshots WHERE feature_id=?',(s.DISCOUNT,)).fetchone()[0])['stores'][-1]['name'],"ホテル'99")
        with self.assertRaises(ValueError): s.validate_previous(result, {s.DISCOUNT:200})
        with self.assertRaises(ValueError): s.verify_policy('Changed policy')


if __name__ == '__main__': unittest.main()
