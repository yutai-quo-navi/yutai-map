import sys
import unittest
from datetime import date
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/features'))
from scrape_sunfrontier_hotels import parse_hotels,pending_opening,verify_hotel,verify_policy,hotel_address,hotel_coordinates

class SunFrontierTests(unittest.TestCase):
    def test_planned_openings_respect_exact_dates_and_unknown_days(self):
        today=date(2026,10,8)
        self.assertTrue(pending_opening('ホテル（2026.11.15 開業予定）',today))
        self.assertTrue(pending_opening('ホテル（2027.1 開業予定）',today))
        self.assertTrue(pending_opening('ホテル（2026.10 開業予定）',today))
        self.assertFalse(pending_opening('ホテル（2026.10.1 開業予定）',today))
        with self.assertRaises(ValueError):pending_opening('ホテル（来春 開業予定）',today)

    def test_lodging_eligibility_excludes_future_properties_before_url_validation(self):
        row='<tr><td><a href="https://seifutei.jp/">静楓亭</a></td><td>0242-62-5600</td><td>〇</td><td>×</td></tr>'
        # Distinct approved property paths keep this fixture independent of live hotel counts.
        rows=''.join(row.replace('https://seifutei.jp/','https://seifutei.jp/h'+str(i)+'/') for i in range(25))
        rows+='<tr><td><a href="">ホテル（2027.1 開業予定）</a></td><td>03-0000-0000</td><td>〇</td></tr>'
        rows+='<tr><td><a href="https://evil.example/">レストランのみ</a></td><td>03</td><td>×</td><td>〇</td></tr>'
        document='<table><tr><th>ホテル名 電話番号 ご宿泊 お食事</th></tr>'+rows+'</table>'
        self.assertEqual(len(parse_hotels(document,date(2026,10,8))),25)
        with self.assertRaises(ValueError):parse_hotels(document.replace('https://seifutei.jp/','https://evil.example/'),date(2026,10,8))

    def test_official_structured_lodging_coordinates_match_hotel_identity(self):
        import json
        hotel={'name':'七重八重','sourceUrl':'https://www.7e8e.jp/'}
        item={'@type':'LodgingBusiness','name':'七重八重','geo':{'latitude':36.82659,'longitude':139.717117}}
        document='<script type="application/ld+json">'+json.dumps({'@graph':[item]},ensure_ascii=False)+'</script>'
        self.assertEqual(hotel_coordinates(document,hotel)['lat'],36.82659)
        with self.assertRaises(ValueError):hotel_coordinates(document.replace('七重八重','近隣ホテル'),hotel)

    def test_official_lazy_map_and_address_normalization(self):
        doc='<iframe data-src="https://www.google.com/maps/embed?pb=!2d141.307445!3d43.165702"></iframe>'
        hotel={'name':'たびのホテル石狩'}
        self.assertEqual(hotel_coordinates(doc,hotel)['lat'],43.165702)
        self.assertEqual(hotel_address('<address>〒061-3213 石狩市花川北3条1丁目7 TEL: 0133-77-7607</address>'),
                         '〒061-3213 北海道石狩市花川北3条1丁目7')
        self.assertEqual(hotel_address('<address>〒039-3212 青森県上北郡六ヶ所村 <ruby>尾駮<rt>おぶち</rt></ruby> <ruby>家ノ前<rt>いえのまえ</rt></ruby> 58-9 0175-73-7855 お問い合わせ</address>'),
                         '〒039-3212 青森県上北郡六ヶ所村 尾駮 家ノ前 58-9')
        self.assertEqual(hotel_address('<address>〒952-0003 新潟県佐渡市椿697 [ google map ]</address>'),
                         '〒952-0003 新潟県佐渡市椿697')

    def test_unverified_location_or_changed_rules_cannot_replace_snapshot(self):
        hotel={'id':'test','name':'静楓亭','sourceUrl':'https://seifutei.jp/'}
        with self.assertRaises(ValueError):verify_hotel(hotel,date(2026,10,8),lambda _: '<p>〒969-3101 福島県耶麻郡猪苗代町1</p>')
        with self.assertRaises(ValueError):verify_policy('株主様ご優待割引券')

    def test_villa_uses_own_contact_address_instead_of_checkin_hotel(self):
        hotel={'name':'たびのホテルVilla宮古島','sourceUrl':'https://villa-miyakojima.tabino-hotel.jp/'}
        document='<p>〒906-0012 沖縄県宮古島市平良西里596 たびのホテルlit宮古島</p><footer>たびのホテル Villa 宮古島<p>〒906-0015 沖縄県宮古島市平良久貝244-1 Phone: 0980-75-3100</p></footer>'
        self.assertEqual(hotel_address(document,hotel),'〒906-0015 沖縄県宮古島市平良久貝244-1')
        with self.assertRaises(ValueError):hotel_address(document.replace('Villa','lit'),hotel)

if __name__=='__main__':unittest.main()
