import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools/issuers'))
from ohsho_joyfull import ohsho_page, ohsho_detail, joyfull_page


def ohsho_list(count=1, page=1, name='餃子の王将 テスト店'):
    return f'<div class="searchResult"><span class="number">{count}件</span></div><div class="hitCount">{20*(page-1)+1}～{min(20*page,count)}件を表示</div><div class="shopBlockList"><div class="shopBlock"><h3 class="shopName"><a href="/b/ohsho/info/1/">{name}</a></h3></div></div>'


def ohsho_html(sid='1'):
    fields={'code':sid+'_ohsho','name':'テスト店','fullAddress':'東京都千代田区1-1','telephone':'03-1234-5678','latitude':'35.68','longitude':'139.76','latitudeTky':'35.67','longitudeTky':'139.77'}
    metas=''.join(f'<meta itemprop="{k}" content="{v}">' for k,v in fields.items())
    data={'id':sid,'name':'テスト店','poi_status':'1','print_start_date':'2020-01-01'}
    return '<div itemtype="https://schema.org/LocalBusiness">'+metas+'</div><script>window.infoJSON = '+json.dumps(data)+';</script>'


def joyfull_html(count=1, sid='1', lat='35.68'):
    return f'<div id="shop-result">{count} 件の店舗があります<a data-shop-item id="shop_{sid}" href="https://www.joyfull.co.jp/shop/{sid}" data-shop-name="テスト店" data-shop-address="東京都千代田区1-1" data-latitude="{lat}" data-longitude="139.76"><span class="rs-name">テスト店</span></a></div>'


class OfficialLocatorTests(unittest.TestCase):
    def test_ohsho_world_datum_not_tokyo_datum(self):
        items,_=ohsho_page(ohsho_list())
        row=ohsho_detail(items[0],ohsho_html())
        self.assertEqual((row['lat'],row['lng']),(35.68,139.76))

    def test_ohsho_incomplete_or_wrong_page(self):
        for html,page,total in [(ohsho_list(21),1,21),(ohsho_list(),2,1),(ohsho_list(),1,2)]:
            with self.assertRaises(ValueError): ohsho_page(html,page,total)

    def test_ohsho_detail_identity(self):
        items,_=ohsho_page(ohsho_list())
        with self.assertRaises(ValueError): ohsho_detail(items[0],ohsho_html('2'))

    def test_ohsho_javascript_escape_in_unrelated_field(self):
        items,_=ohsho_page(ohsho_list())
        html=ohsho_html().replace('"poi_status":', '"memo":"shop\\\'s menu", "poi_status":')
        self.assertEqual(ohsho_detail(items[0],html)['official_id'],'1')

    def test_ohsho_optional_publication_date(self):
        items,_=ohsho_page(ohsho_list())
        html=ohsho_html().replace(', "print_start_date": "2020-01-01"','')
        self.assertEqual(ohsho_detail(items[0],html)['official_id'],'1')

    def test_other_ohsho_is_not_eligible(self):
        with self.assertRaises(ValueError): ohsho_page(ohsho_list(name='大阪王将 テスト店'))

    def test_joyfull_official_coordinate_and_id(self):
        rows,count=joyfull_page(joyfull_html())
        self.assertEqual(count,1)
        self.assertEqual(rows[0]['store_id'],'official:joyfull:1')
        self.assertEqual(rows[0]['lat'],35.68)

    def test_joyfull_incomplete_duplicate_bad_coordinates(self):
        for html in [joyfull_html(2),joyfull_html(lat='0'),joyfull_html().replace('shop/1','shop/2')]:
            with self.assertRaises(ValueError): joyfull_page(html)

    def test_joyfull_zero_requires_explicit_empty_result(self):
        self.assertEqual(joyfull_page('<div id="shop-result">検索条件に一致する店舗が見つかりませんでした</div>'),([],0))
        with self.assertRaises(ValueError): joyfull_page('<div id="shop-result"></div>')


if __name__ == '__main__': unittest.main()
