import sys,json,sqlite3,tempfile,unittest
from pathlib import Path
from datetime import date
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/features'))
import scrape_daiwa_hotels as s
TODAY=date(2026,10,8)
POLICY='共通商品券 ダイワロイネットホテルズでの宿泊 ラ・ジェント・ホテルでの宿泊 ラ・ジェント・ステイ札幌大通 ラ・ジェント・ステイ函館駅前 ご利用対象外 1,000円単位 おつりは返金いたしません '+s.RELEASE
MAP='<iframe src="https://www.google.com/maps/embed?pb=!3d35.61!4d139.71"></iframe>'
def roy(alias,address='〒100-0001 東京都千代田区1-1',extra=''):
    return f'<div class="wrp_hotel"><p class="n">ホテル{alias}</p><address>{address}</address><p>{extra}</p><a href="/{alias}/">ホテルサイトはこちら</a><a href="https://www.google.com/maps/d/viewer?ll=35.6%2C139.7">マップで場所を確認</a></div>'
def lagent(alias):
    return f'<li><p class="c-txt-l">ホテル{alias}</p><a href="https://lagent.jp/{alias}/">ホテルサイト</a></li>'
class DaiwaTests(unittest.TestCase):
    def test_policy_changes_fail_closed(self):
        s.verify_policy(POLICY,s.RELEASE_SHA256)
        for policy,digest in [(POLICY,'changed'),(POLICY.replace('ご利用対象外',''),'')]:
            with self.assertRaises(ValueError):s.verify_policy(policy,digest)
    def test_domestic_dedup_future_and_explicit_exclusions(self):
        result=s.parse_roy(roy('one')*2+roy('overseas','〒04157 Korea')+roy('future',extra='2026年11月オープン'),TODAY)
        self.assertEqual(len(result),1)
        result=s.parse_lagent('<ul class="hotellist">'+''.join(lagent(a) for a in ['one','sapporo-odori','hakodate-ekimae'])+'</ul>',TODAY)
        self.assertEqual([x['id'] for x in result],['lagent-one'])
    def test_coordinates_fallback_comes_from_same_official_listing(self):
        hotel=s.parse_roy(roy('one'),TODAY)[0]
        with patch.object(s.time,'sleep'):
            result=s.verify_hotel(hotel,lambda _: '',{},TODAY)
        self.assertEqual(result['lat'],35.6)
        self.assertIn('目安',result['coordinateNote'])
        self.assertNotIn('listingCoordinates',result)
    def test_complete_snapshot_and_staging_batches_are_isolated(self):
        royhtml=''.join(roy('hotel-'+str(i)) for i in range(75))
        lagenthtml='<ul class="hotellist">'+''.join(lagent(a) for a in ['one','sapporo-odori','hakodate-ekimae'])+'</ul>'
        with patch.object(s.time,'sleep'):
            snapshot=s.build_snapshot(POLICY,royhtml,lagenthtml,s.RELEASE_SHA256,lambda _: '<address>〒100-0001 東京都千代田区1-1 TEL 00</address>'+MAP,TODAY)
        self.assertEqual(len(snapshot['stores']),77)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'sync.sql';s.write_sql([snapshot],p,batch_id='daiwa-hotels')
            db=sqlite3.connect(':memory:');db.executescript(p.read_text())
            db.execute("INSERT INTO feature_snapshot_staging VALUES ('kyoritsu-hotels','other','2026-10-08',0,'{}')")
            db.commit();db.executescript(p.read_text())
            self.assertEqual(db.execute('SELECT COUNT(*) FROM feature_snapshots').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM feature_snapshot_staging').fetchone()[0],1)
if __name__=='__main__':unittest.main()
