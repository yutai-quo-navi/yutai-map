import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/features'))
from scrape_greens_hotels import CHOICE, ORIGINAL, hotel_record, parse_choice, parse_original, resolved_hotel_map, verify_hotel, verify_policy

class GreensHotelsTest(unittest.TestCase):
    def test_directory_scope_and_duplicate_guard(self):
        def card(i):
            return f'<section class="p-all__hotel"><span class="p-all__hotel__title__name"><span>コンフォートイン</span><span>ホテル{i}</span></span><p class="p-all__hotel__address">〒111-0032 東京都台東区浅草1-1-1</p><a class="c-text-link__link" href="https://www.choice-hotels.jp/inn/h{i}/">公式サイト</a></section>'
        directory=''.join(card(i) for i in range(85))
        hotels=parse_choice(directory+card(99).replace('ホテル99','ホテル99 開業予定'))
        self.assertEqual(len(hotels),85)
        self.assertEqual(hotels[0]['name'],'コンフォートインホテル0')
        for invalid in [directory+card(0),directory.replace('www.choice-hotels.jp','wrong.example')]:
            with self.assertRaises(ValueError):parse_choice(invalid)

    def test_original_only_property_cards(self):
        html='<ul class="wrp-list">'+''.join(f'<li><span class="n">グリーンホテル{i}</span><span class="add">〒111-0032 東京都台東区浅草1-1-1</span><a href="https://www.greens.co.jp/h{i}/">ホテル情報</a></li>' for i in range(15))+'</ul>'
        self.assertEqual(len(parse_original(html+'<a href="https://unrelated.example/">観光情報</a>')),15)
        with self.assertRaises(ValueError):parse_original(html+html)

    def test_access_without_address_uses_official_directory(self):
        hotel=hotel_record('コンフォートインホテル','〒111-0032 東京都台東区浅草1-1-1','https://www.choice-hotels.jp/inn/hotel/',CHOICE)
        html='<title>アクセス【公式】コンフォートインホテル</title><p>観光施設 〒101-0000 東京都別の場所</p><iframe src="https://www.google.com/maps/embed?pb=!3d35.7!4d139.8"></iframe>'
        result=verify_hotel(hotel,'2026-10-09',lambda _:html)
        self.assertEqual(result['address'],hotel['address'])
        self.assertEqual(result['lat'],35.7)
        with self.assertRaises(ValueError):verify_hotel(hotel,'2026-10-09',lambda _:html.replace('<title>アクセス【公式】コンフォートインホテル</title>','<title>別ホテル</title><nav>コンフォートインホテル</nav>'))

    def test_map_marker_not_viewport_or_attraction(self):
        url='https://www.google.com/maps/place/コンフォートスイーツ東京ベイ/@35.64,139.92,16z/data=!3d35.6385373!4d139.9274263'
        self.assertEqual(resolved_hotel_map(url,'コンフォートスイーツ東京ベイ')['lat'],35.6385373)
        for bad in [url.replace('東京ベイ','東京ディズニーランド'),url.replace('www.google.com','wrong.example'),url.split('/data=')[0]]:
            with self.assertRaises(ValueError):resolved_hotel_map(bad,'コンフォートスイーツ東京ベイ')

    def test_policy_fails_closed_on_limit_change(self):
        terms=['株主様ご優待割引券','1,000円券','発行翌年3月末まで','当社運営のホテル全店','1室1泊当たり5,000円分','1室1泊あたり5,000円分が上限','連泊分の合算金額に対する利用はできません','事前決済の場合はご利用いただけません','お釣りはお出しいたしません','当社以外へお支払いただく場合はご利用いただけません']
        html='<p>'+' '.join(terms)+'</p><a href="https://www.choice-hotels.jp/"></a><a href="https://www.greens.co.jp/"></a>'
        verify_policy(html)
        with self.assertRaises(ValueError):verify_policy(html.replace('5,000','3,000'))

if __name__=='__main__':unittest.main()
