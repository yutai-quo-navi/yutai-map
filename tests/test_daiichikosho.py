import sys,unittest
from pathlib import Path
from datetime import date
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/issuers/daiichikosho'))
from store_parser import parse_page
TODAY=date(2026,10,8)
def page(name='楽蔵',address='〒100-0001 東京都千代田区1-1',lat='35.67',mapname=None):
    text='<p class="resultTxt">173件中 1〜20件を表示</p>'
    for i in range(20):
        title=name+str(i);mapped=(mapname or name)+str(i);url=f'https://rakuzo.dkdining.com/{i}/'
        text+=f'<p data-shop-id="{i}" data-latlng="{lat},139.76" data-title="{mapped}" data-shop-url="{url}"></p><div class="search-con-list-box" id="shop-list__id--{i}"><h4><a href="{url}">{title}</a></h4><div class="specBox"><span class="specTitle">住所</span><span class="specTxt">{address}</span></div></div>'
    return text
class DiningTests(unittest.TestCase):
    def test_complete_page_and_official_coordinates(self):
        total,rows,excluded=parse_page(page(),1,TODAY)
        self.assertEqual(total,173);self.assertEqual(len(rows),20);self.assertFalse(excluded)
        self.assertEqual(rows[0]['lat'],35.67)
        self.assertEqual(rows[0]['brand_name'],'楽蔵')
    def test_future_openings_are_excluded_until_open(self):
        self.assertEqual(len(parse_page(page(name='【10/27 OPEN】楽蔵'),1,TODAY)[1]),0)
        self.assertEqual(len(parse_page(page(name='【10/27 OPEN】楽蔵'),1,date(2026,10,27))[1]),20)
    def test_incomplete_map_identity_pagination_and_coordinates_fail(self):
        for doc,p in [(page(mapname='他店舗'),1),(page(lat='0'),1),(page(),2),(page().replace('173件','999件'),1)]:
            with self.assertRaises(ValueError):parse_page(doc,p,TODAY)
    def test_abbreviated_ginza_address_only_normalizes_in_ginza(self):
        rows=parse_page(page(address='中央区銀座4-2-14'),1,TODAY)[1]
        self.assertTrue(rows[0]['address'].startswith('東京都'))
        with self.assertRaises(ValueError):parse_page(page(address='中央区銀座4-2-14',lat='43.06'),1,TODAY)
if __name__=='__main__':unittest.main()
