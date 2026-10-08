import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/features'))
from scrape_wakita_hotels import PROPERTIES, parse_hotels, verify_eligibility, verify_policy, verify_hotel, resolved_coordinates

POLICY = 'ホテル公式ホームページ予約および電話予約のみとなります。但し「現地決済」予約に限ります。航空券及び新幹線とのセット予約にご利用いただけません。食事のみでは利用できません。キャンセル料、フロント販売、宅配代、ランドリー代には利用不可。'


def directory():
    return ''.join(f'<li class="estate-hotel-card"><h3 class="estate-hotel-card__name">{name}</h3><a class="estate-hotel-card__site" href="{url}">公式</a>{address}</li>' for url,(name,address,_) in PROPERTIES.items())


class WakitaHotelsTests(unittest.TestCase):
    def test_only_explicitly_eligible_properties_publish(self):
        text='株主優待電子チケットはどこの店舗で利用できますか？ホテルコルディア大阪、ホテルコルディア大阪本町で利用可能です。ホテル公式ホームページでの予約および直接電話での予約に限定'
        verify_eligibility(text)
        with self.assertRaises(ValueError):verify_eligibility(text.replace('大阪本町','他のホテル'))
        self.assertEqual(len(parse_hotels(directory())),2)
        for bad in [directory()+directory(),directory().replace('江戸堀1-3-25','江戸堀9-9-9'),directory().replace('/hommachi/','/other/')]:
            with self.assertRaises(ValueError):parse_hotels(bad)

    def test_official_web_booking_requires_on_site_payment(self):
        verify_policy(POLICY)
        for term in ['「現地決済」予約に限ります','電話予約のみ','航空券及び新幹線とのセット予約にご利用いただけません']:
            with self.assertRaises(ValueError):verify_policy(POLICY.replace(term,''))

    def test_map_marker_and_exact_property_identity(self):
        url='https://www.google.com/maps/place/ホテルコルディア大阪/@35,136/data=!3d34.691425!4d135.4968979'
        p=resolved_coordinates(url,'ホテルコルディア大阪')
        self.assertEqual((p['lat'],p['lng']),(34.691425,135.4968979))
        for bad in [url.replace('大阪/','大阪本町/'),url.replace('www.google.com','example.com'),url.replace('!3d34.691425','!3d99'),url.split('/data=')[0],url+'!3d34.7!4d135.5']:
            with self.assertRaises(ValueError):resolved_coordinates(bad,'ホテルコルディア大阪')

    def test_property_address_and_map_link_checked_before_publication(self):
        hotel=parse_hotels(directory())[0];name,address,link=PROPERTIES[hotel['sourceUrl']]
        doc=f'<html><head><title>{name}</title></head><body>{address}<a href="{link}">地図</a></body></html>'
        resolve=lambda _:f'https://www.google.com/maps/place/{name}/data=!3d34.69!4d135.49'
        fetch=lambda url:POLICY if url.endswith('/faq/') else doc
        self.assertTrue(verify_hotel(hotel,'2026-10-09',fetch,resolve)['verified'])
        for bad in [doc.replace(address,'別の住所'),doc.replace(link,'https://example.com/'),doc.replace(name,'別ホテル')]:
            with self.assertRaises(ValueError):verify_hotel(hotel,'2026-10-09',lambda url:POLICY if url.endswith('/faq/') else bad,resolve)

if __name__=='__main__':unittest.main()
