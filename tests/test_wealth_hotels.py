import sys
import unittest
import json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/features'))
from scrape_wealth_hotels import PROPERTIES, parse_hotels, embedded_coordinates, resolved_map_coordinates, verify_hotel, verify_policy

class WealthHotelsTest(unittest.TestCase):
    def listing(self):
        return '<table><tr><th>株主優待利用可能ホテル（随時更新）</th></tr>'+''.join(f'<tr><td><a href="{url}">{name}</a> 北海道札幌市中央区南2条西8-6-1</td></tr>' for url,(name,_) in PROPERTIES.items())+'</table>'

    def test_explicit_eligibility_table_only(self):
        hotels=parse_hotels(self.listing()+'<a href="https://unrelated.example/">開発予定ホテル</a>')
        self.assertEqual(len(hotels),8)
        self.assertEqual(hotels[0]['address'],'北海道札幌市中央区南2条西8-6-1')
        for invalid in [self.listing()*2,self.listing().replace('https://www.hotel-emisia.com/sapporo/','https://wrong.example/'),self.listing().replace('北海道札幌市','海外')]:
            with self.assertRaises(ValueError):parse_hotels(invalid)

    def test_schema_coordinates_require_exact_property_url(self):
        url='https://www.banyantree.com/japan/kyoto'
        def schema(source):return '<script type="application/ld+json">'+json.dumps({'@type':'Resort','url':source,'geo':{'latitude':34.998,'longitude':135.783}})+'</script>'
        self.assertEqual(embedded_coordinates(schema(url),{'sourceUrl':url})['lat'],34.998)
        with self.assertRaises(ValueError):embedded_coordinates(schema(url+'/other'),{'sourceUrl':url})

    def test_current_hotel_map_ignores_other_hotels(self):
        url='https://www.dhawa.com/japan/dhawa-yura-kyoto'
        attrs={'title':'Dhawa Yura Kyoto','path':{'alias':'/japan/dhawa-yura-kyoto'},'field_geolocation':{'lat':35.009,'lng':135.774}}
        def document():return '<script id="__NEXT_DATA__" type="application/json">'+json.dumps({'props':{'pageProps':{'initialReduxState':{'currentHotel':{'data':{'attributes':attrs}},'suggestedHotels':[{'field_geolocation':{'lat':1,'lng':2}}]}}}})+'</script>'
        self.assertEqual(embedded_coordinates(document(),{'sourceUrl':url})['lng'],135.774)
        attrs['path']['alias']='/japan/other'
        with self.assertRaises(ValueError):embedded_coordinates(document(),{'sourceUrl':url})

    def test_svg_title_does_not_replace_document_identity(self):
        hotel={'sourceUrl':'https://www.hotel-emisia.com/sapporo/','name':'ホテルエミシア札幌'}
        html='<head><title>アクセス ホテルエミシア札幌</title></head><body><svg><title>別施設</title></svg><iframe src="https://www.google.com/maps/embed?pb=!3d43.04!4d141.47"></iframe></body>'
        self.assertEqual(verify_hotel(hotel,'2026-10-09',lambda _:html)['lat'],43.04)
        with self.assertRaises(ValueError):verify_hotel(hotel,'2026-10-09',lambda _:html.replace('<title>アクセス ホテルエミシア札幌</title>','<title>別ホテル</title>'))

    def test_map_marker_not_attraction_or_viewport(self):
        url='https://www.google.com/maps/place/Six+Senses+Kyoto/@35.0,135.8,15z/data=!3d34.991!4d135.774'
        self.assertEqual(resolved_map_coordinates(url)['lat'],34.991)
        for invalid in [url.replace('Six+Senses+Kyoto','Kyoto+Station'),url.split('/data=')[0],url.replace('www.google.com','wrong.example')]:
            with self.assertRaises(ValueError):resolved_map_coordinates(invalid)

    def test_booking_policy_changes_fail_closed(self):
        terms=['ホテル宿泊のほか','株主ご本人様またはご家族様','転売や譲渡を目的とした行為は禁止','複数枚同時にお使いいただけます','有効期間内であれば同時','現金またはクレジットカード','他の商品券、金券などは併用できません','適用除外日はございません','必ず「現地決済」をお選びください','事前決済でご予約された場合、株主優待は適用対象外','他の割引券・特典との併用','旅行代理店や外部予約サイトを経由したご予約ではご利用いただけません']
        html='<p>'+' '.join(terms)+'</p>';verify_policy(html)
        with self.assertRaises(ValueError):verify_policy(html.replace('有効期間内であれば同時',''))

if __name__=='__main__':unittest.main()
