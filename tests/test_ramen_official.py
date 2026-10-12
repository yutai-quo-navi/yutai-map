import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'issuers'))
from ramen_official import yama_list, yama_detail, chikara_row, chikara_city, yext_document, chikara_page
from urllib.parse import quote

YAMA_LIST = '''<section class="shops_part"><h3>北海道 道東エリア</h3><li class="shops_item" id="s1121" data-brand="ramen_yamaokaya"><a href="/shops/1121/"><h4 class="shops_name">ラーメン山岡家 釧路店</h4></a></li><li class="shops_item" id="s99" data-brand="gyoza"><a href="/shops/99/"><h4 class="shops_name">餃子の山岡家</h4></a></li></section><script>var json_realtime = {"shops":[{"id":1121,"lat":43.01437,"lng":144.31987},{"id":99,"lat":43.1,"lng":141.3}]};</script>'''
YAMA_DETAIL = '''<html><title>ラーメン山岡家 釧路店 | ラーメン山岡家</title><body class="1121"><table><tr class="info_table_row"><th>住所</th><td>〒 084-0912<br>釧路市星が浦大通2丁目5-28<div><iframe src="https://maps.google.co.jp/maps?q=43.01437,144.31987"></iframe></div><!-- / .map --><ul><li>周辺の地図を表示</li></ul></td></tr><tr class="info_table_row"><th>電話番号</th><td>0154-53-7170</td></tr></table></body></html>'''
ROW = {'name':'一風堂 札幌狸小路店','slug':'1804','address':{'countryCode':'JP','region':'北海道','city':'札幌市','sublocality':'中央区','line1':'南3条西6-8'},'mainPhone':'+81112525505','yextDisplayCoordinate':{'latitude':43.056654,'longitude':141.349674}}

class OfficialRamenTest(unittest.TestCase):
    def test_yama_eligible_and_clean_address(self):
        rows,total=yama_list(YAMA_LIST)
        self.assertEqual((len(rows),total),(1,2))
        result=yama_detail(rows[0],YAMA_DETAIL)
        self.assertEqual(result['address'],'北海道釧路市星が浦大通2丁目5-28')
        self.assertEqual(result['store_id'],'official:yamaokaya:1121')

    def test_yama_incomplete_or_unknown_source_fails(self):
        for bad in [YAMA_LIST.replace('"id":1121','"id":1122'),YAMA_LIST.replace('ramen_yamaokaya','unknown'),YAMA_LIST.replace('s1121','s99')]:
            with self.assertRaises(ValueError): yama_list(bad)

    def test_yama_detail_identity_and_coordinate_mismatch(self):
        item=yama_list(YAMA_LIST)[0][0]
        for bad in [YAMA_DETAIL.replace('class="1121"','class="1122"'),YAMA_DETAIL.replace('43.01437,','40.0,')]:
            with self.assertRaises(ValueError):yama_detail(item,bad)

    def test_chikara_domestic_coordinate_and_brand(self):
        self.assertEqual(chikara_row(ROW)['address'],'北海道札幌市中央区南3条西6-8')
        kay={**ROW,'name':'一風堂KAY テスト店'}
        self.assertEqual(chikara_row(kay)['brand_name'],'一風堂 KAY')
        spaced={**ROW,'name':'RAMEN EXPRESS 博多 一風堂 テスト店'}
        self.assertEqual(chikara_row(spaced)['brand_name'],'RAMEN EXPRESS 博多一風堂')
        for name in ['名島亭 テスト店','北海道ラーメン楓','一蘭 テスト店']:
            with self.assertRaises(ValueError):chikara_row({**ROW,'name':name})
        bad=copy.deepcopy(ROW);bad['address']['countryCode']='US'
        with self.assertRaises(ValueError):chikara_row(bad)
        bad=copy.deepcopy(ROW);bad['yextDisplayCoordinate']['latitude']=0
        with self.assertRaises(ValueError):chikara_row(bad)

    def test_chikara_api_pagination_and_identity(self):
        data={'meta':{'errors':[]},'response':{'businessId':2196888,'resultsCount':1,'results':[{'data':{**ROW,'id':'1804','type':'location'}}]}}
        self.assertEqual(chikara_page(data,0)[1],1)
        for bad in [dict(data,meta={'errors':[{'code':1}]}),dict(data,response={**data['response'],'results':[]}),dict(data,response={**data['response'],'businessId':1})]:
            with self.assertRaises(ValueError):chikara_page(bad,0)
        with self.assertRaises(ValueError):chikara_page(data,0,2)

    def test_yext_decode_and_complete_city_coverage(self):
        city={'slug':'日本/北海道/札幌市','dm_directoryChildren':[{}]}
        doc={'slug':city['slug'],'meta':{'entityType':{'id':'ce_city'}},'dm_directoryChildren':[ROW]}
        html='<script type="module">pageProps: JSON.parse(decodeURIComponent("'+quote(json.dumps({'document':doc}))+'"))</script>'
        self.assertEqual(len(chikara_city(city,yext_document(html))),1)
        with self.assertRaises(ValueError):chikara_city(city,{**doc,'dm_directoryChildren':[]})
        with self.assertRaises(ValueError):chikara_city(city,{**doc,'slug':'日本/東京'})

if __name__=='__main__':unittest.main()
