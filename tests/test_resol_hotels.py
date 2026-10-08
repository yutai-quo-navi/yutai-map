import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/features'))
from scrape_resol_hotels import parse_hotels, verify_policy, verify_hotel

class ResolTests(unittest.TestCase):
    def test_only_lodging_column_controls_eligibility(self):
        rows=''.join(f'<tr><td><a href="https://www.resol-hotel.jp/h{i}/">ホテル{i}（東京都）</a></td><td>○</td><td>×</td></tr>' for i in range(24))
        rows+='<tr><td><a href="https://www.resol-hotel.jp/closed/">閉館</a></td><td>×</td><td>○</td></tr>'
        rows+='<tr><td><a href="https://www.mannacc.com/">真名コース</a></td><td>○</td><td>○</td></tr>'
        html='<table><tr><th>施設名</th><th>宿泊プラン</th><th>レストラン</th></tr>'+rows+'</table><table><tr><th>施設名 ゴルフプレー</th></tr><tr><td>ゴルフのみ</td><td>○</td></tr></table>'
        hotels=parse_hotels(html)
        self.assertEqual(len(hotels),24)
        self.assertTrue(all(h['name'].startswith('ホテル') for h in hotels))
        self.assertNotIn('closed',str(hotels))

    def test_empty_or_changed_policy_fails_closed(self):
        with self.assertRaises(ValueError): verify_policy('RESOLファミリー商品券')
        with self.assertRaises(ValueError): parse_hotels('<table><tr><th>ゴルフプレー</th></tr></table>')

    def test_resort_requires_its_named_marker_not_a_nearby_attraction(self):
        hotel={'id':'mori','name':'Sport & Do Resort リソルの森','sourceUrl':'https://www.resol-no-mori.com/'}
        html="<p>〒297-0201 千葉県長生郡長柄町上野521-4 TEL 0475-35-3333</p><script>maker1=new google.maps.Marker({ position: new google.maps.LatLng(35.4792,140.2491), map: map, title: 'リソルの森', draggable: false });</script>"
        store=verify_hotel(hotel,'2026-10-08',lambda _:html)
        self.assertEqual(store['lat'],35.4792)
        self.assertIn('受付場所',store['coordinateNote'])
        for changed in [html.replace('リソルの森','飯高寺'),html.replace('35.4792','0.1')]:
            with self.assertRaises(ValueError):verify_hotel(hotel,'2026-10-08',lambda _:changed)

    def test_unverified_location_does_not_enter_database(self):
        hotel={'id':'test','name':'テスト','sourceUrl':'https://www.resol-hotel.jp/test/'}
        with self.assertRaises(ValueError):verify_hotel(hotel,'2026-10-08',lambda _: '<p>〒100-0001 東京都千代田区千代田1</p>')

if __name__=='__main__':unittest.main()
