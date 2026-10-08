import copy
import sys
import unittest
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/issuers/srs'))
from srs_parser import parse_stores

class SrsParserTests(unittest.TestCase):
    def directory(self):
        shops = [dict(id=i,brand={'id':424},openStatus='IS_ALREADY_OPEN') for i in range(700)]
        shops[0] = dict(id=0,brand={'id':400},openStatus='IS_ALREADY_OPEN',nameKanji='家族亭 札幌店',storeCode='sapporo',address='北海道札幌市中央区南一条西2丁目',latitude='43.0602442',longitude='141.3550742')
        return {'shops':shops}, {'shops':copy.deepcopy(shops[:40]),'totalCount':700}
    def test_only_eligible_domestic_open_stores(self):
        data,page=self.directory()
        data['shops'][41]=dict(data['shops'][0],id=41,openStatus='IS_CLOSED')
        data['shops'][42]=dict(data['shops'][0],id=42,latitude=3.13,longitude=101.68,address='Kuala Lumpur')
        data['shops'][43]=dict(data['shops'][0],id=43,establishmentDate='2099-01-01')
        rows,excluded=parse_stores(data,page,date(2026,10,9))
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['brand_name'],'家族亭')
        self.assertEqual(rows[0]['lat'],43.0602442)
        self.assertEqual(len(excluded),699)
    def test_incomplete_directory_fails(self):
        data,page=self.directory();data['shops'].pop()
        with self.assertRaises(ValueError):parse_stores(data,page,date.today())
    def test_invalid_domestic_identity_fails(self):
        data,page=self.directory();data['shops'][0]['address']='札幌市';page['shops'][0]=copy.deepcopy(data['shops'][0])
        with self.assertRaises(ValueError):parse_stores(data,page,date.today())
    def test_unknown_open_status_fails(self):
        data,page=self.directory();data['shops'][0]['openStatus']='NEW_UNKNOWN'
        with self.assertRaises(ValueError):parse_stores(data,page,date.today())
