import importlib.util
import json
import unittest
from datetime import date
from pathlib import Path

spec = importlib.util.spec_from_file_location('fujio_parser', Path(__file__).resolve().parents[1] / 'tools/issuers/fujio/fujio_parser.py')
parser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parser)
TODAY = date(2026, 10, 9)


def directory(names=('札幌白石食堂',), mapped=True, latitude=43.045, longitude=141.416, notice='', area='北海道', address='北海道札幌市白石区本通7丁目南6-12'):
    cards, maps = [], []
    for i, name in enumerate(names):
        url = f'https://www.fujiofood.com/shop_search/shokudo/shop_{i}.php'
        cards.append(f'<li class="prefSec-store"><p class="ttl">まいどおおきに食堂&emsp;{name}</p><table><tr><th>住所</th><td>〒003-0026 {address}</td></tr><tr><th>TEL/FAX</th><td>011-000-0000</td></tr><tr><th>営業時間</th><td>{notice}</td></tr></table><p class="detailBtn"><a href="{url}">詳細</a></p></li>')
        if mapped:
            maps.append({'link':url,'address':address,'latitude':str(latitude),'longitude':str(longitude)})
    return f'全{len(names)}店舗<h4 class="prefSec-heading">{area}</h4>' + ''.join(cards) + f'<script>$json_array = {json.dumps(maps)};</script>'


class FujioTests(unittest.TestCase):
    def test_entire_directory_including_stores_missing_from_map_array(self):
        total, rows, excluded = parser.parse_directory(directory(mapped=False), TODAY)
        self.assertEqual((total, len(rows), len(excluded)), (1, 1, 0))
        self.assertNotIn('lat', rows[0])
        self.assertEqual(rows[0]['brand_name'], 'まいどおおきに食堂')

    def test_valid_official_coordinates_and_duplicate_coordinate_typo(self):
        row = parser.parse_directory(directory(), TODAY)[1][0]
        self.assertEqual(row['lat'], 43.045)
        self.assertNotIn('lat', parser.parse_directory(directory(longitude=43.045), TODAY)[1][0])

    def test_relocated_store_does_not_inherit_old_coordinates(self):
        doc = directory().replace('"address": "', '"address": "OLD ')
        self.assertNotIn('lat', parser.parse_directory(doc, TODAY)[1][0])

    def test_holidays_are_kept_but_indefinite_closure_and_ineligible_stores_are_excluded(self):
        for notice in ['2025年1月1日は休業致します', '年末年始のみ休業']:
            self.assertEqual(len(parser.parse_directory(directory(notice=notice), TODAY)[1]), 1)
        for notice in ['2026/5/16よりしばらくの間休業致します', '臨時休業とさせていただきます', '当社発行の金券等はご利用いただけません']:
            self.assertFalse(parser.parse_directory(directory(notice=notice), TODAY)[1])

    def test_overseas_unknown_area_and_incomplete_page(self):
        self.assertFalse(parser.parse_directory(directory(area='台湾'), TODAY)[1])
        for doc in [directory(area='不明'), directory().replace('全1店舗','全5店舗')]:
            with self.assertRaises(ValueError):
                parser.parse_directory(doc, TODAY)

    def test_changed_eligibility_policy_fails_closed(self):
        with self.assertRaises(ValueError):
            parser.verify_policy('お食事券は全店で使えません')


if __name__ == '__main__':
    unittest.main()
