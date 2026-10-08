import sys
import copy
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/issuers/kineya'))
from kineya_parser import parse_stores,COMPANIES,brand_for,own_coordinates

class KineyaTests(unittest.TestCase):
    def data(self):
        companies=sorted(COMPANIES)
        shops=[dict(id=i,name='杵屋 札幌アピア店',address='北海道札幌市中央区北5条西4',company=companies[i%4],telephone=str(i)) for i in range(500)]
        return dict(list=shops,count=500,offset=1)
    def test_portal_limits_scope_and_excludes_railway(self):
        d=self.data();d['list'][0]['name']='水間鉄道フリー乗車証'
        rows,excluded=parse_stores(d,[])
        self.assertEqual(len(rows),499);self.assertEqual(len(excluded),1)
        self.assertTrue(all('gmo:' in r['store_id'] for r in rows))
    def test_incomplete_or_duplicate_directory_fails(self):
        d=self.data();d['count']=501
        with self.assertRaises(ValueError):parse_stores(d,[])
        d=self.data();d['list'][1]['id']=d['list'][0]['id']
        with self.assertRaises(ValueError):parse_stores(d,[])
    def test_unexpected_partner_or_brand_requires_review(self):
        d=self.data();d['list'][0]['company']='Unknown'
        with self.assertRaises(ValueError):parse_stores(d,[])
        with self.assertRaises(ValueError):brand_for('新しい対象業態 札幌店')
        self.assertEqual(brand_for('杵屋麦丸 新宿店'),'杵屋麦丸')
        self.assertEqual(brand_for('フジヤマ５５ 東海店'),'フジヤマ55')
    def test_telephone_joins_only_unique_current_official_locations(self):
        d=self.data();r=next(s for s in d['list'] if s['company']=='株式会社グルメ杵屋レストラン')
        location=dict(phone=r['telephone'],address=r['address'],lat=43.067012,lng=141.3490745,url='https://gourmet-kineya.co.jp/search/376')
        rows,_=parse_stores(d,[location]);self.assertEqual(sum('lat' in s for s in rows),1)
        rows,_=parse_stores(d,[location,copy.deepcopy(location)]);self.assertEqual(sum('lat' in s for s in rows),0)
    def test_official_coordinates_require_identity(self):
        card=dict(name='杵屋 札幌店',address='北海道札幌市',url='https://gourmet-kineya.co.jp/search/376')
        html='株主優待 <a href="tel:011-209-3437"></a> destination=43.06701200,141.34907450'
        self.assertEqual(own_coordinates(card,html)['lat'],43.067012)
        with self.assertRaises(ValueError):own_coordinates(card,html.replace('43.06701200','0.000'))
