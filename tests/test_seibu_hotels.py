import sys,json,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/features'))
import scrape_seibu_hotels as s
class SeibuTests(unittest.TestCase):
    def test_official_coordinate_sources_and_invalid_maps(self):
        for doc in ['<iframe src="https://www.google.com/maps/embed?pb=!3d35.61!4d139.71"></iframe>', '<a href="http://maps.apple.com/?q=35.61,139.71">地図</a>']:
            self.assertEqual(s.official_coordinates(doc)['lat'],35.61)
        for doc in ['<a href="https://attacker.example/?q=35.61,139.71">地図</a>','<a href="https://maps.apple.com/?q=1,2">地図</a>']:
            with self.assertRaises(ValueError):s.official_coordinates(doc)
    def test_same_site_coordinates_require_unchanged_address_and_official_map(self):
        policy=json.loads(s.POLICY.read_text())
        h=next(h for h in policy['hotels'] if h['name']=='プリンス バケーション クラブ 軽井沢浅間')
        address='長野県北佐久郡軽井沢町大字発地字馬越1399番100'
        home=f'<dl><dt>住所</dt><dd>{address}</dd></dl>'
        access='<a href="https://goo.gl/maps/jFYk64DQEDKAnz4y6">Googleマップ</a>'
        def fetch(url):return access if url.endswith('access/') else home
        with patch.object(s,'fetch',side_effect=fetch),patch.object(s.time,'sleep'):
            result=s.check_hotel(h,policy,'2026-10-08')
            self.assertIn('目安',result['coordinateNote'])
        for changed in [home.replace('1399','1400'),access.replace('jFYk64DQEDKAnz4y6','changed')]:
            def bad(url):return (changed if changed.startswith('<a') else access) if url.endswith('access/') else (changed if changed.startswith('<dl') else home)
            with patch.object(s,'fetch',side_effect=bad),patch.object(s.time,'sleep'),self.assertRaises(ValueError):s.check_hotel(h,policy,'2026-10-08')
    def test_current_eligibility_keeps_room_options_and_ticket_counts(self):
        policy=json.loads(s.POLICY.read_text())
        self.assertEqual(len(policy['hotels']),50)
        self.assertEqual(len({h['sourceUrl'] for h in policy['hotels']}),50)
        self.assertEqual({o['requiredTickets'] for h in policy['hotels'] for o in h['options']},{1,2,4})
        h=policy['hotels'][0]
        doc='<p>〒100-0001 東京都千代田区1-1 TEL 00</p><a href="http://maps.apple.com/?q=35.61,139.71">地図</a>'
        with patch.object(s,'fetch',return_value=doc),patch.object(s.time,'sleep'):
            result=s.check_hotel(h,policy,'2026-10-08')
        self.assertEqual(result['voucherOptions'],h['options'])
        self.assertEqual(result['eligibilitySourceUrl'],policy['eligibilitySourceUrl'])
        self.assertTrue(result['verified'])
if __name__=='__main__':unittest.main()
