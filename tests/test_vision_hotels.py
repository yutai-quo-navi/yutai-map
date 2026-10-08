import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/features'))
from scrape_vision_hotels import PROPERTIES, parse_hotels, verify_hotel, verify_policy

POLICY = '宿泊費のみ割引対象 入湯税などもご利用いただけません 1泊あたり最大29,000円分（1部屋ごと） 株主専用ダイヤルからのご予約のみ適用可能 0120-390-388 受付時間9:00-18:00 同年中に発行された株主優待券（クーポンコード）のみ併用可能 他の割引特典や金券、その他割引サービスとの併用はできません'

def directory():
    links=''.join(f'<a href="{url}">{name}</a>' for url,(name,_,_) in PROPERTIES.items())
    names=''.join(f'{name}(県)' for name,_,_ in PROPERTIES.values())
    return f'<div id="vision_glamping_container">{links}</div><div class="stockWrapContent06">利用可能施設{names}</div>'

def property_html(source_url, **changes):
    name,address,_=PROPERTIES[source_url]
    obj={'@type':'LodgingBusiness','name':name,'url':source_url,
         'address':{'addressCountry':'JP','addressRegion':address,'addressLocality':'','streetAddress':''},
         'geo':{'latitude':31.799435,'longitude':130.776244}}
    obj.update(changes)
    return '<script type="application/ld+json">'+json.dumps({'@graph':[obj]})+'</script>'

class VisionHotelsTests(unittest.TestCase):
    def test_only_explicitly_eligible_named_hotels_publish(self):
        self.assertEqual(len(parse_hotels(directory())),2)
        for bad in [directory().replace('https://koshikano-onsen.com/','https://example.com/'), directory().replace('山中湖(県)','別ホテル(県)'), directory()+directory(),directory().replace('</div>','<a href="https://example.com/">追加ホテル</a></div>',1)]:
            with self.assertRaises(ValueError):parse_hotels(bad)

    def test_phone_reservation_and_payment_cap_are_required(self):
        verify_policy(POLICY)
        for term in ['株主専用ダイヤルからのご予約のみ適用可能','1泊あたり最大29,000円分（1部屋ごと）','入湯税などもご利用いただけません','同年中に発行された株主優待券（クーポンコード）のみ併用可能']:
            with self.assertRaises(ValueError):verify_policy(POLICY.replace(term,''))

    def test_official_identity_address_and_coordinates_checked(self):
        hotel=parse_hotels(directory())[1];url=hotel['sourceUrl']
        checked=verify_hotel(hotel,'2026-10-09',lambda _:property_html(url))
        self.assertTrue(checked['verified']);self.assertEqual(checked['coordinateSourceUrl'],url)
        for changes in [{'name':'別ホテル'}, {'url':'https://example.com/'},{'address':{'addressCountry':'JP','addressRegion':'別の住所'}}, {'geo':{'latitude':float('nan'),'longitude':130}}, {'geo':{'latitude':90,'longitude':130}}]:
            with self.assertRaises(ValueError):verify_hotel(hotel,'2026-10-09',lambda _:property_html(url,**changes))

    def test_missing_geo_uses_official_access_map_with_approximation_note(self):
        hotel=parse_hotels(directory())[0];url=hotel['sourceUrl']
        page=property_html(url);data=json.loads(page.split('>',1)[1].split('</script>')[0]);del data['@graph'][0]['geo']
        home='<script type="application/ld+json">'+json.dumps(data)+'</script>'
        access='<head><title>山中湖 交通案内</title></head><iframe src="https://www.google.com/maps/embed?pb=!2d138.8492139!3d35.4361151"></iframe>'
        checked=verify_hotel(hotel,'2026-10-09',lambda u:home if u==url else access)
        self.assertIn('目安',checked['coordinateNote'])
        self.assertEqual(checked['coordinateSourceUrl'],PROPERTIES[url][2])
        with self.assertRaises(ValueError):verify_hotel(hotel,'2026-10-09',lambda u:home if u==url else access.replace('山中湖','別ホテル'))

if __name__=='__main__':unittest.main()
