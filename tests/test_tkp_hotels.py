import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/features'))
from scrape_tkp_hotels import PROPERTIES, parse_hotels, verify_hotel, hotel_coordinates, verify_policy


def directory():
    return ''.join(f'<div class="column{1+i%3}" data-category="宿泊・その他"><div class="external-link-area"><a href="{url}">{row[0]}</a></div>公式サイトまたは電話で予約した場合のみ利用可能</div>' for i,(url,row) in enumerate(PROPERTIES.items()))


class TkpHotelsTests(unittest.TestCase):
    def test_lodging_tags_exclude_restaurants_and_other_chain_hotels(self):
        document = directory()+'<div data-category="飲食"><div class="external-link-area"><a href="https://example.com/">ホテル内レストラン</a></div></div><a href="https://example.com/other-hotel">系列ホテル</a>'
        self.assertEqual(len(parse_hotels(document)),9)
        for bad in [document.replace('宿泊・その他','その他',1), document+directory(), document.replace('https://slh.jp/','https://example.com/new-hotel/',1), document.replace('電話で予約した場合のみ利用可能','外部サイトでも利用可能',1)]:
            with self.assertRaises(ValueError):parse_hotels(bad)

    def test_exact_property_identity_and_address_required(self):
        hotel = parse_hotels(directory())[0]
        name,address,_ = PROPERTIES[hotel['sourceUrl']]
        document = f'<html><head><title>{name}</title></head><body>{address}<iframe src="https://www.google.com/maps/embed?pb=!2d139.537!3d36.144"></iframe></body></html>'
        result = verify_hotel(hotel,'2026-10-09',lambda url:document)
        self.assertEqual(result['lat'],36.144)
        for bad in [document.replace(address,'埼玉県羽生市別の場所'), document.replace(name,'系列ホテル'),document.replace('!3d36.144','!3d99')]:
            with self.assertRaises(ValueError):verify_hotel(hotel,'2026-10-09',lambda url:bad)

    def test_marker_over_viewport_and_ambiguous_markers_fail(self):
        link = '<a href="https://www.google.com/maps/place/@35.1,139.0/data=!3d35.105!4d139.077">地図</a>'
        result = hotel_coordinates(link)
        self.assertEqual((result['lat'],result['lng']),(35.105,139.077))
        with self.assertRaises(ValueError):hotel_coordinates(link+link.replace('!3d35.105','!3d35.2'))
        with self.assertRaises(ValueError):hotel_coordinates('<a href="https://example.com/maps/place/!3d35.1!4d139.1">地図</a>')

    def test_policy_changes_require_review(self):
        terms=['現地精算','公式サイト、または施設へ直接お電話にてご予約','他の旅行予約サイト、旅行代理店、グルメサイト経由','ご優待券の裏面に「氏名」をご記入','つり銭のお支払はいたしかねます','ご優待券は、複数同時にご利用いただけます','他キャンペーン・クーポン券との併用はできません','ご優待券の権利譲渡、売買、現金との引き換えはできません']
        verify_policy(' '.join(terms))
        with self.assertRaises(ValueError):verify_policy(' '.join(terms).replace('複数同時','1枚のみ'))

if __name__=='__main__':unittest.main()
