import math
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'features'))
from scrape_kyoritsu_hotels import Document, PREFECTURES

BENEFIT_URL = 'https://srsholdings.com/pages/ir-shareholder-program'
SEARCH_PAGE = 'https://store.srsholdings.com/'
API_URL = 'https://api.site.can-ly.com/v2/directories/8/shops/search?sort=alphabetical'
POLICY_BRANDS = {'和食さと', '天丼・天ぷら本舗 さん天', '法善寺夫婦善哉', 'にぎり長次郎', 'CHOJIRO',
                 '宅配にぎり長次郎', '家族亭', '得得うどん', '得得', '花旬庵', '三宝庵', '家族庵', 'うどんの詩',
                 '蕎旬', 'うどんのう', '蕎菜', 'とくとく', '海鮮丼家族庵', 'うまい鮨勘', 'うまい鮨勘ゆとろぎ',
                 '鮨正', 'まるくに', 'まるかん', '玉子焼・お出汁ひまわり', 'すし弁慶', '回転すし北海道',
                 'ビフテキ牛ノ福', '勝福惣店', 'きらりCUCINA'}
# Map the directory's stable brand IDs to the official voucher names.
BRANDS = {395:'和食さと',396:'さん天',397:'法善寺夫婦善哉',389:'にぎり長次郎',426:'CHOJIRO',427:'宅配にぎり長次郎',
          400:'家族亭',401:'得得',404:'花旬庵',405:'三宝庵',409:'家族庵',402:'うどんの詩',407:'蕎旬',408:'うどんのう',
          406:'蕎菜',403:'とくとく',458:'海鮮丼家族庵',410:'うまい鮨勘',428:'うまい鮨勘ゆとろぎ',
          411:'鮨正',412:'鮨正',413:'まるくに',429:'まるかん',419:'玉子焼・お出汁ひまわり',423:'すし弁慶',
          422:'回転すし北海道',421:'ビフテキ牛ノ福',430:'勝福惣店',431:'きらりCUCINA'}


def verify_policy(html):
    text = Document(html).root.text()
    if '「かつや」「からやま」' not in text or 'ご利用いただけません' not in text:
        raise ValueError('Missing franchise voucher exclusion')
    section = text.split('※以下の国内店舗でご利用いただけます。', 1)
    if len(section) != 2 or set(re.findall('「([^」]+)」', section[1].split('掲載されている内容', 1)[0])) != POLICY_BRANDS:
        raise ValueError('SRS eligible brand policy changed; preserve D1')


def parse_stores(data, page, today):
    shops = data.get('shops')
    total = page.get('totalCount')
    if not isinstance(shops, list) or not isinstance(total, int) or total != len(shops) or not 700 <= total <= 1800:
        raise ValueError('Incomplete official SRS directory')
    first = page.get('shops', [])
    if not first or [s['id'] for s in first] != [s['id'] for s in shops[:len(first)]]:
        raise ValueError('Directory changed between coverage checks')
    rows, exclusions, seen = [], [], set()
    for s in shops:
        sid = str(s['id'])
        if sid in seen:
            raise ValueError('Duplicate official store')
        seen.add(sid)
        brand_id = (s.get('brand') or {}).get('id')
        if brand_id not in BRANDS:
            exclusions.append({'id':sid,'reason':'公式優待案内の対象外ブランド'})
            continue
        if s.get('openStatus') != 'IS_ALREADY_OPEN':
            if s.get('openStatus') not in {'IS_CLOSED','IS_PERMANENTLY_CLOSED','IS_NOT_YET_OPEN'}:
                raise ValueError('Unknown official opening status')
            exclusions.append({'id':sid,'reason':'休業・閉店・開店前'})
            continue
        if s.get('establishmentDate') and date.fromisoformat(s['establishmentDate'][:10]) > today:
            exclusions.append({'id':sid,'reason':'開店前'})
            continue
        lat, lng = float(s['latitude']), float(s['longitude'])
        if not (20 <= lat <= 46 and 122 <= lng <= 154):
            exclusions.append({'id':sid,'reason':'海外店舗'})
            continue
        address = re.sub(r'\s+', ' ', str(s.get('address') or '')).strip()
        pref = next((p for p in PREFECTURES if address.startswith(p)), None)
        if not pref or not s.get('nameKanji') or not s.get('storeCode'):
            raise ValueError('Incomplete domestic store identity')
        lat, lng = float(s['latitude']), float(s['longitude'])
        if not (math.isfinite(lat) and math.isfinite(lng) and 20 <= lat <= 46 and 122 <= lng <= 154):
            raise ValueError('Invalid official domestic coordinates')
        rows.append({'store_id':'official:id:'+sid,'official_id':sid,'name':s['nameKanji'],'address':address,
                     'prefecture':pref,'phone':s.get('tel',''),'brand_name':BRANDS[brand_id],'category':'restaurant',
                     'lat':lat,'lng':lng,'official_url':SEARCH_PAGE+'detail/'+quote(str(s['storeCode']),safe='')+'/',
                     'coordinate_source':API_URL,'benefit_status':'official_eligible'})
    return rows, exclusions
