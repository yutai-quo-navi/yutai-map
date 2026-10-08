import math
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'features'))
from scrape_kyoritsu_hotels import PREFECTURES
SEARCH_URL='https://shop.arclandservice.co.jp/ae-shop/'
API_URL=SEARCH_URL+'api/proxy2/shop/list'
BRANDS={'01':'かつや','27':'たれとん','04':'からやま','03':'からあげ縁','16':'からあげ・とり弁 縁','05':'Cento per Cento','07':'camp express','08':'ごちとん','10':'東京たらこスパゲティ','09':'天丼はま田','12':'スンドゥブ 中山豆腐店','17':'マンゴツリー東京','14':'マンゴツリーカフェ','23':'マンゴツリーキッチン','13':'DANCING CRAB','18':'天ぷら 魚新','19':'東京とろろそば','26':'肉めし 岡もと'}

def parse_pages(pages,today):
    total=pages[0]['count']['total']
    if not 600<=total<=1400:raise ValueError('Unexpected official directory size')
    shops=[]
    for page in pages:
        count=page['count']; items=page['items']
        if count['total']!=total or count['offset']!=len(shops) or len(items)!=min(count['limit'],total-len(shops)):
            raise ValueError('Incomplete or changing official pagination')
        shops.extend(items)
    if len(shops)!=total:raise ValueError('Missing official store pages')
    defined={d['code']:d['label'] for s in shops for g in s.get('detail_groups',[]) for f in g.get('flags',[]) for d in f.get('details',[])}
    if defined.get('00145')!='株主優待券使用不可' or defined.get('00146')!='優待券テイクアウトのみ使用可':raise ValueError('Official voucher flag schema changed')
    rows,excluded,seen=[],[],set()
    for s in shops:
        code=str(s['code'])
        if code in seen:raise ValueError('Duplicate official store')
        seen.add(code)
        if code.startswith('os'):
            excluded.append({'id':code,'reason':'海外店舗'});continue
        lat,lng=float(s['coord']['lat']),float(s['coord']['lon'])
        if not math.isfinite(lat) or not math.isfinite(lng):raise ValueError('Invalid coordinates')
        if not (20<=lat<=46 and 122<=lng<=154):
            excluded.append({'id':code,'reason':'海外店舗'});continue
        if s['status']!='normal' or (s.get('from_date') and datetime.fromisoformat(s['from_date']).date()>today) or (s.get('to_date') and datetime.fromisoformat(s['to_date']).date()<today):
            excluded.append({'id':code,'reason':'閉店・休業・開店前'});continue
        flags={d['code']:d for g in s['detail_groups'] for f in g.get('flags',[]) for d in f.get('details',[])}
        for fid,label in [('00145','株主優待券使用不可'),('00146','優待券テイクアウトのみ使用可')]:
            if fid in flags and (flags[fid]['label']!=label or not isinstance(flags[fid]['value'],bool)):raise ValueError('Invalid official voucher eligibility flags')
        takeout=flags.get('00146',{}).get('value',False)
        if flags.get('00145',{}).get('value',False) or (flags.get('00027',{}).get('value',False) and not takeout):
            excluded.append({'id':code,'reason':'株主優待券使用不可'});continue
        brand_codes=[b['code'] for b in s['categories']]
        if not brand_codes or any(b not in BRANDS for b in brand_codes):raise ValueError('Unknown restaurant brand')
        # Co-branded stores appear only once; directory's first category is the main brand.
        brand=BRANDS[brand_codes[0]]
        address=s['address_name'].strip();pref=next((p for p in PREFECTURES if address.startswith(p)),None)
        if not pref or not s['name']:raise ValueError('Incomplete domestic identity')
        rows.append(dict(store_id='official:code:'+code,official_id=code,name=s['name']+('（優待は持帰りのみ）' if takeout else ''),address=address,prefecture=pref,phone=s.get('phone',''),brand_name=brand,category='cafe' if brand=='Cento per Cento' else 'restaurant',lat=lat,lng=lng,official_url=SEARCH_URL+'spot/detail?code='+quote(code,safe=''),coordinate_source=API_URL,benefit_status='official_eligible',benefit_note='テイクアウトのみ優待券利用可' if takeout else ''))
    return rows,excluded,total
