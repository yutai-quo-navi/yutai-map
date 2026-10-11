import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('official_api',Path(__file__).resolve().parents[1]/'tools/issuers/official_api.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class OfficialSources(unittest.TestCase):
    def test_komeda_eligibility_and_locator_id(self):
        item={'id':1,'brand_type':1,'name':'サンプル店','address':'東京都千代田区丸の内1'}
        detail={'shop':{'id':2,'brand_type':1,'name':'サンプル店','address':item['address'],'tel':'03-0000-0000','shop_latitude':35.68,'shop_longitude':139.76,'details':[{'id':'207-4','values':[19]}]}}
        self.assertEqual(m.komeda_detail(item,detail)['store_id'],'official:komeda:1')
        detail['shop']['details'][0]['values']=[20]
        self.assertIsNone(m.komeda_detail(item,detail))
        detail['shop']['details']=[]
        self.assertIsNone(m.komeda_detail(item,detail))
        detail['shop']['name']='別店舗'
        with self.assertRaises(ValueError):m.komeda_detail(item,detail)
    def test_doutor_requires_official_card_flag_including_other_formats(self):
        row={'code':'123','status':'normal','name':'神乃珈琲 サンプル店','address_name':'東京都千代田区丸の内1','categories':[{'level':'large','name':'神乃珈琲'}],'coord':{'lat':35.68,'lon':139.76},'details':[{'flags':[{'code':'00022','value':True}]}]}
        self.assertEqual(m.doutor_row(row)['brand_name'],'神乃珈琲')
        row['details'][0]['flags'][0]['value']=False
        with self.assertRaises(ValueError):m.doutor_row(row)
    def test_mos_closures_and_openings_are_not_searchable(self):
        row={'bus_cd':'AEN','name':'玄米食堂あえん サンプル店','shop_cd':'123','openingday':'2000-01-01','closingday':'9999-12-31','pref_cd':'13','addr_all':'東京都千代田区丸の内1','lat':'35.68','lon':'139.76'}
        self.assertEqual(m.mos_row(row)['brand_name'],'玄米食堂あえん')
        row['closingday']='2001-01-01';self.assertIsNone(m.mos_row(row))
        row['closingday']='9999-12-31';row['openingday']='2099-01-01';self.assertIsNone(m.mos_row(row))
    def test_misdo_uses_official_decimal_coordinates_and_ignores_legend(self):
        text='<li class="list-item"><a href="/b/misterdonut/info/0012/"><h2 class="list-content-name">サンプル ショップ</h2><div data-lat="35.68" data-lng="139.76"></div><div class="list-content-text">東京都千代田区丸の内1</div></a></li><li class="list-item">凡例</li>'
        rows=m.misdo_rows(text);self.assertEqual(len(rows),1);self.assertEqual(rows[0]['lat'],35.68)
        with self.assertRaises(ValueError):m.misdo_rows(text.replace('data-lat','invalid-lat'))
    def test_snapshot_second_import_does_not_rewrite_unchanged_stores(self):
        import os
        original=Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory);p=Path('data/issuers/sample');p.mkdir(parents=True)
                (p/'config.json').write_text(json.dumps({'name':'sample','health':{'minStores':1,'maxStores':10,'maxAdded':3,'maxChanged':3}}))
                rows=[m.store('official:id:1','sample','sample','東京都千代田区1','',35.68,139.76,'https://example.com')]
                m.snapshot('sample',copy.deepcopy(rows),{'source':'https://example.com'})
                m.snapshot('sample',copy.deepcopy(rows),{'source':'https://example.com'})
                d=json.loads((p/'stores/diffs'/f'{m.DATE}.json').read_text())
                self.assertEqual(d['counts'],{'previous':1,'current':1,'added':0,'removed':0,'changed':0})
            finally:os.chdir(original)
