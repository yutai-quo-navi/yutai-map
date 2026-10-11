"""Official store sources and validated incremental snapshots for the three issuers."""
import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

NOW=datetime.now(ZoneInfo('Asia/Tokyo'))
DATE=NOW.date().isoformat()
CACHE=Path(os.environ['OFFICIAL_SOURCE_CACHE']) if os.environ.get('OFFICIAL_SOURCE_CACHE') else None

def fetch(url):
    path=CACHE/(hashlib.sha256(url.encode()).hexdigest()+'.json') if CACHE else None
    if path and path.exists():return json.loads(path.read_text())
    for attempt in range(3):
        try:
            request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 yutai-map/1.0','Accept':'application/json','Referer':url.split('/api/')[0]+'/'})
            with urllib.request.urlopen(request,timeout=35) as response:data=json.load(response)
            if path:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,ensure_ascii=False))
            return data
        except (OSError,ValueError):
            if attempt==2:raise
            time.sleep(attempt+1)

def store(sid,brand,name,address,phone,lat,lng,url,category='cafe',allow_partial_address=False):
    lat,lng=float(lat),float(lng)
    if not 20<=lat<=46 or not 122<=lng<=154:raise ValueError('Invalid Japanese coordinates')
    pref=re.match(r'(北海道|東京都|大阪府|京都府|.{2,3}県)',address)
    if (not pref and not allow_partial_address) or not address or not name or not sid:raise ValueError('Invalid official store fields')
    return {'store_id':sid,'official_id':sid.split(':')[-1],'brand_name':brand,'category':category,'name':name,'address':address,'prefecture':pref[0] if pref else '','phone':phone or '', 'lat':lat,'lng':lng,'official_url':url,'benefit_status':'official_eligible'}

KBRANDS={1:'コメダ珈琲店',2:'おかげ庵',5:'KOMEDA is □',6:'BAKERY ADEMOK',7:'大餡吉日',10:'ジェリコ堂',11:'米屋の太郎'}

def komeda_detail(item,data):
    row=data['shop'];brand=KBRANDS[int(item['brand_type'])]
    if row['name']!=item['name'] or row['address']!=item['address'] or int(row['brand_type'])!=int(item['brand_type']):raise ValueError('Komeda list/detail mismatch')
    # Public locator ID differs from the internal shop.id; preserve the locator ID.
    payments=[d for d in row['details'] if d['id']=='207-4']
    if len(payments)>1:raise ValueError('Komeda payment structure changed')
    if not payments or 19 not in payments[0]['values']:return None
    # Announced future openings are present in the official list; do not expose yet.
    if re.search(r'\bOPEN\b|オープン予定',row['name'],re.I):return None
    sid=str(item['id'])
    return store('official:komeda:'+sid,brand,brand+' '+row['name'],row['address'],row.get('tel'),row['shop_latitude'],row['shop_longitude'],'https://www.komeda.co.jp/shop/detail.html?id='+sid,'bakery' if int(item['brand_type'])==6 else 'restaurant' if int(item['brand_type'])==11 else 'cafe')

def collect_komeda():
    base='https://eu.komeda.co.jp/v1/hp/shop'
    items=[]
    for b in KBRANDS:
        d=fetch(base+'?'+urllib.parse.urlencode({'brand_type':b,'all':'true'}))
        if len(d['items'])!=d['total'] or any(int(x['brand_type'])!=b for x in d['items']):raise ValueError('Incomplete Komeda brand list')
        items.extend(d['items'])
    def detail(item):
        time.sleep(.15)
        return komeda_detail(item,fetch(base+'/'+str(item['id'])))
    result=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for i,s in enumerate(pool.map(detail,items),1):
            if s:result.append(s)
            if i%100==0:print(f'Komeda details: {i}/{len(items)}',flush=True)
    return result,{'source':'https://www.komeda.co.jp/shop/','api_source':base,'official_store_universe_count':len(items),'eligible_filter':'official payment 207-4 includes KOMECA 19; domestic brands; announced openings excluded'}

def doutor_row(row):
    flags=[f for d in row.get('details',[]) for f in d.get('flags',[]) if f['code']=='00022']
    if len(flags)!=1 or flags[0]['value'] is not True:raise ValueError('Doutor official card filter changed')
    if row['status']!='normal':raise ValueError('Doutor inactive store in list')
    brands=[c['name'] for c in row['categories'] if c['level']=='large']
    if len(brands)!=1:raise ValueError('Doutor brand structure changed')
    brand=brands[0]
    if brand=='ドトール珈琲農園・珈琲店':
        brand='ドトール珈琲農園' if '農園' in row['name'] else 'ドトール珈琲店'
    code=str(row['code'])
    return store('official:dnh:'+code,brand,row['name'],row['address_name'],row.get('phone'),row['coord']['lat'],row['coord']['lon'],'https://shop.doutor.co.jp/doutor/spot/detail?code='+code)

def collect_dnh():
    base='https://shop.doutor.co.jp/doutor/api/proxy2/shop/list'
    result=[];total=None
    offset=0
    while total is None or offset<total:
        d=fetch(base+'?'+urllib.parse.urlencode({'offset':offset,'limit':200,'c_d22':1,'add':'detail'}))
        if total is None:total=int(d['count']['total'])
        if int(d['count']['total'])!=total or int(d['count']['offset'])!=offset or len(d['items'])!=min(200,total-offset):raise ValueError('Incomplete Doutor pagination')
        result.extend(doutor_row(row) for row in d['items']);offset+=200;time.sleep(.3)
    return result,{'source':'https://shop.doutor.co.jp/doutor/spot/list?c_d22=1','api_source':base,'official_store_universe_count':total,'eligible_filter':'official DOUTOR VALUE CARD flag 00022=true'}

MBRANDS={'MOS_GREEN':'モスバーガー','MOS_RED':'モスバーガー','MOS_CF':'モスバーガー','MOS_PR':'モスプレミアム','MOSDO':'モスド','MLEAF':'マザーリーフ','MLEAF_TS':'マザーリーフティースタイル','YAMAUMITAIYO':'カフェ 山と海と太陽','AEN':'あえん','MOS_SH':'モッシュ バーガー & バル'}

def mos_row(row):
    brand=MBRANDS[row['bus_cd']]
    if str(row['openingday'])>DATE or str(row['closingday'])<=DATE:return None
    if not str(row['pref_cd']).isdigit() or not 1<=int(row['pref_cd'])<=47:raise ValueError('MOS non-domestic store')
    if row['bus_cd']=='AEN' and '玄米食堂' in row['name']:brand='玄米食堂あえん'
    code=row['shop_cd']
    return store('official:mos:'+code,brand,row['name'],row['addr_all'],'-'.join(str(row[k]) for k in ['tel1','tel2','tel3'] if row.get(k)),row['lat'],row['lon'],'https://www.mos.jp/shop/detail/?shop_cd='+code,'cafe' if row['bus_cd'] in ('MLEAF','MLEAF_TS','YAMAUMITAIYO') else 'restaurant')

def snapshot(issuer,stores,meta):
    cfg=json.loads(Path(f'data/issuers/{issuer}/config.json').read_text());health=cfg['health']
    if not health['minStores']<=len(stores)<=health['maxStores']:raise ValueError('Official store count outside expected range')
    by_id={s['store_id']:s for s in stores}
    if len(by_id)!=len(stores):raise ValueError('Duplicate official IDs')
    base=Path(f'data/issuers/{issuer}/stores');p=base/'current.json'
    previous=json.loads(p.read_text()) if p.exists() else {'stores':[]};old={s['store_id']:s for s in previous['stores']}
    def comparable(s):return {k:v for k,v in s.items() if k not in ('first_seen','last_seen','status','missing_count')}
    added=sorted(by_id.keys()-old.keys());removed=sorted(old.keys()-by_id.keys());changed=sorted(sid for sid in by_id.keys()&old.keys() if comparable(by_id[sid])!=comparable(old[sid]))
    if old:
        if max(len(added),len(removed))>health['maxAdded'] or len(changed)>health['maxChanged'] or len(removed)>len(old)*.15:raise ValueError('Unexpected official store changes; preserve existing D1')
        for field in ('brand_name','prefecture'):
            counts=Counter(s[field] for s in old.values());fresh=Counter(s[field] for s in stores)
            if any(count>=10 and fresh[key]<count*.5 for key,count in counts.items()):raise ValueError('Official brand/prefecture coverage dropped')
    for sid,s in by_id.items():s.update(first_seen=old.get(sid,{}).get('first_seen') or DATE,last_seen=DATE,status='active')
    stamp=NOW.isoformat(timespec='seconds')
    counts={'previous':len(old),'current':len(stores),'added':len(added),'removed':len(removed),'changed':len(changed)}
    current={**meta,'generated_at':stamp,'eligible_count':len(stores),'brand_counts':dict(Counter(s['brand_name'] for s in stores)),'stores':sorted(stores,key=lambda s:s['store_id'])}
    diff={'source':meta['source'],'generated_at':stamp,'run_date':DATE,'previous_generated_at':previous.get('generated_at'),'counts':counts,'added':[by_id[s] for s in added],'removed':[old[s] for s in removed],'changed':[{'store_id':s,'before':old[s],'after':by_id[s]} for s in changed]}
    for path,obj in [(p,current),(base/'diffs'/f'{DATE}.json',diff)]:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    (base/'last_diff.md').write_text(f'# {cfg["name"]}店舗DB 差分 {DATE}\n\n'+''.join(f'- {k}: {v}\n' for k,v in counts.items()))
    print(json.dumps({'issuer':issuer,**counts,'brands':current['brand_counts']},ensure_ascii=False),flush=True)

def fetch_text(url):
    path=CACHE/(hashlib.sha256(url.encode()).hexdigest()+'.html') if CACHE else None
    if path and path.exists():return path.read_text()
    for attempt in range(3):
        try:
            request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 yutai-map/1.0'})
            with urllib.request.urlopen(request,timeout=35) as response:text=response.read().decode('utf-8')
            if path:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
            return text
        except OSError:
            if attempt==2:raise
            time.sleep(attempt+1)

def misdo_rows(text):
    from html import unescape
    blocks=re.split(r'<li class="list-item">',text)[1:]
    result=[]
    for block in blocks:
        if 'list-content-name' not in block:continue
        code=re.search(r'href="/b/misterdonut/info/(\d+)/"',block)
        name=re.search(r'<h2 class="list-content-name">(.*?)</h2>',block)
        coord=re.search(r'data-lat="([\d.]+)" data-lng="([\d.]+)"',block)
        address=re.search(r'<div class="list-content-text">([^<]+)</div>',block)
        if not all((code,name,coord,address)):raise ValueError('Misdo official list structure changed')
        result.append(store('official:misdo:'+code[1],'ミスタードーナツ','ミスタードーナツ '+unescape(name[1].split('<span')[0]).strip(),unescape(address[1]),'',coord[1],coord[2],'https://md.mapion.co.jp/b/misterdonut/info/'+code[1]+'/',allow_partial_address=True))
    return result

def collect_misdo():
    base='https://md.mapion.co.jp/b/misterdonut/attr/'
    first=fetch_text(base+'?srt=citycode,poi_name_yomi')
    total_match=re.search(r'(\d+)件のショップがあります',first)
    pages_match=re.search(r'endPage:\s*(\d+)',first)
    if not total_match or not pages_match:raise ValueError('Missing Misdo pagination totals')
    total,pages=int(total_match[1]),int(pages_match[1])
    if not 900<=total<=1300 or pages!=(total+19)//20:raise ValueError('Unexpected Misdo pagination')
    result=misdo_rows(first)
    if len(result)!=min(total,20):raise ValueError('Incomplete first Misdo page')
    for page in range(2,pages+1):
        time.sleep(.2)
        rows=misdo_rows(fetch_text(base+'?'+urllib.parse.urlencode({'page':'more','start':page,'srt':'citycode,poi_name_yomi'})))
        if len(rows)!=min(20,total-20*(page-1)):raise ValueError('Incomplete Misdo page')
        result.extend(rows)
        if page%10==0:print(f'Misdo pages: {page}/{pages}',flush=True)
    if len({r['store_id'] for r in result})!=total:raise ValueError('Duplicate or missing Misdo shops')
    return result

def collect_mos():
    base='https://www.mos.jp/data/shop/shop.json'
    d=fetch(base);rows=d['shops']
    if not 1200<=len(rows)<=1500 or any(r['bus_cd'] not in MBRANDS for r in rows):raise ValueError('MOS brand/source structure changed')
    result=[s for row in rows if (s:=mos_row(row))]
    result.extend(collect_misdo())
    return result,{'source':'https://www.mos.jp/shop/','api_source':base,'additional_sources':['https://md.mapion.co.jp/b/misterdonut/attr/'],'official_store_universe_count':len(rows),'eligible_filter':'official domestic MOS brands and Mister Donut locator; exceptions require in-store confirmation'}
