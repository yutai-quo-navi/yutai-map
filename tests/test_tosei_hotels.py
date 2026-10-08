import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/features'))
from scrape_tosei_hotels import parse_hotels,verify_hotel,verify_policy


class ToseiTests(unittest.TestCase):
    def listing(self):
        return ''.join(f'<a class="m-panel" href="https://tosei-hotel.co.jp/h{i}/"><b>トーセイホテル ココネ{i}</b><p>〒111-0032 東京都台東区浅草3-26-10</p></a>' for i in range(9))

    def test_only_eligible_cards_enter_dataset(self):
        html=self.listing()+'<a href="https://tosei-hotel.co.jp/chibachuo/">トーセイホテル ココネ千葉中央</a>'
        hotels=parse_hotels(html)
        self.assertEqual(len(hotels),9)
        self.assertTrue(all('address' not in hotel for hotel in hotels))
        with self.assertRaises(ValueError):parse_hotels(self.listing().replace('ココネ0','ココネ千葉中央'))

    def test_duplicate_foreign_or_missing_list_fails_closed(self):
        for html in [self.listing()*2,self.listing().replace('tosei-hotel.co.jp','other.example'),'<p>ホテル一覧はこちら</p>']:
            with self.assertRaises(ValueError):parse_hotels(html)

    def test_address_and_coordinates_come_from_property_not_ir_card(self):
        hotel={'id':'kuramae','name':'トーセイホテル ココネ浅草蔵前','sourceUrl':'https://tosei-hotel.co.jp/asakusakuramae/'}
        doc='<h1>トーセイホテル ココネ浅草蔵前</h1><address>〒111-0043 東京都台東区駒形2丁目3-3 TEL.03-3842-5541</address><iframe src="https://www.google.com/maps/embed?pb=!2d139.7932!3d35.7052"></iframe>'
        requested=[]
        def detail_fetch(url):requested.append(url);return doc
        store=verify_hotel(hotel,'2026-10-09',detail_fetch)
        self.assertEqual(store['address'],'〒111-0043 東京都台東区駒形2丁目3-3')
        self.assertEqual(store['lat'],35.7052)
        self.assertEqual(requested,['https://tosei-hotel.co.jp/asakusakuramae/access/'])
        for changed in [doc.replace('浅草蔵前','浅草'),doc.replace('35.7052','0.1'),doc.replace('<iframe','<span').replace('</iframe>','</span>')]:
            with self.assertRaises(ValueError):verify_hotel(hotel,'2026-10-09',lambda _:changed)

    def test_missing_coordinates_or_changed_policy_cannot_replace_snapshot(self):
        hotel={'name':'トーセイホテル ココネ神田','sourceUrl':'https://tosei-hotel.co.jp/kanda/'}
        with self.assertRaises(ValueError):verify_hotel(hotel,'2026-10-09',lambda _: '<h1>トーセイホテル ココネ神田</h1><p>〒101-0047 東京都千代田区内神田3-2-10</p>')
        with self.assertRaises(ValueError):verify_policy('ホテル宿泊割引券')


if __name__=='__main__':unittest.main()
