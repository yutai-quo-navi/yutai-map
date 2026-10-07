#!/usr/bin/env python3
"""Check reviewed free-pair voucher eligibility and official hotel locations monthly."""
import os
import argparse
import hashlib
import html
import json
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from urllib.request import Request,urlopen
from zoneinfo import ZoneInfo
from scrape_kyoritsu_hotels import ROOT,Document,PREFECTURES,fetch as official_fetch,parse_coordinates,validate_previous,write_sql
from scrape_daiwa_hotels import address_from_detail

def fetch(url):
    cache=os.environ.get('SEIBU_SOURCE_DIR')
    path=Path(cache)/hashlib.sha256(url.encode()).hexdigest() if cache else None
    if path and path.exists():return path.read_text()
    document=official_fetch(url)
    if path:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(document)
    return document

FEATURE='seibu-free-hotels'
POLICY=ROOT/'data/features/seibu-hotel-policy.json'
SUPPLEMENTS=ROOT/'data/features/seibu-hotel-coordinates.json'

def hotel_address(document):
    try:return address_from_detail(document)
    except ValueError:pass
    for node in Document(document).root.find('p')+[Document(document).root]:
        match=re.search(r'〒\s*\d{3}-\d{4}\s*横浜市[^〒]{1,100}',node.text())
        if match:return re.split(r'\d{2,4}-\d{2,4}-\d{3,4}|hkj-hotel|TEL|FAX|電話',match.group())[0].replace('横浜市','神奈川県横浜市',1).strip()
    raise ValueError('Missing official property address')

def official_coordinates(document):
    try: return parse_coordinates(document)
    except ValueError: pass
    for a in Document(document).root.find('a'):
        url=html.unescape(a.attrs.get('href',''));host=urlparse(url).hostname
        if host not in {'maps.apple.com','maps.google.com','www.google.com'}: continue
        query=parse_qs(urlparse(url).query)
        for key in ['ll','q','query']:
            value=query.get(key,[''])[0]
            if re.fullmatch(r'-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?',value):
                lat,lng=map(float,value.split(','))
                if not(20<=lat<=46 and 122<=lng<=154):raise ValueError('Invalid hotel coordinates')
                return {'lat':lat,'lng':lng,'coordinateSource':'公式アクセス地図','coordinateSourceUrl':url}
    raise ValueError('Missing official hotel coordinates')

def check_hotel(hotel,policy,today):
    time.sleep(.25)
    url=hotel['sourceUrl']; document=fetch(hotel.get('locationSourceUrl') or url)
    try:
        if hotel.get('locationSourceUrl'):
            nodes=[n.text().removeprefix('住所').strip() for n in Document(document).root.find('dl') if n.text().startswith('住所 ')]
            if not nodes or not any(nodes[0].startswith(pref) for pref in PREFECTURES):raise ValueError('Missing property address')
            address=nodes[0]
        else:address=hotel_address(document)
    except ValueError: address=None
    try: coords=official_coordinates(document)
    except ValueError: coords=None
    access=hotel.get('accessUrl') or url.rstrip('/')+'/access/'
    if not address or not coords:
        try:
            details=fetch(access)
            if not address: address=hotel_address(details)
            if not coords:
                try:coords=official_coordinates(details)
                except ValueError:
                    supplements=json.loads(SUPPLEMENTS.read_text()) if SUPPLEMENTS.exists() else {}
                    row=supplements.get(hotel['name'])
                    if not row or row['address']!=address or row['officialLocationUrl'] not in {url,access,hotel.get('locationSourceUrl')}:raise
                    if row.get('mapLink') and row['mapLink'] not in details:raise ValueError('Official map link changed')
                    coords={k:v for k,v in row.items() if k not in {'address','officialLocationUrl','mapLink','name'}}
                    if not(20<=coords['lat']<=46 and 122<=coords['lng']<=154):raise ValueError('Invalid supplementary coordinates')
        except Exception as e:
            raise ValueError('Unverified hotel location: '+hotel['name']) from e
    if not address or not coords: raise ValueError('Incomplete hotel location')
    options=hotel['options']
    tickets=sorted({o['requiredTickets'] for o in options})
    print('Verified location:',hotel['name'],flush=True)
    return {'id':'seibu-'+hashlib.sha256(url.encode()).hexdigest()[:14],'name':hotel['name'],
            'address':address,'sourceUrl':url,**coords,'verified':True,'coordinateCheckedOn':today,
            'conditions':f"無料ペア宿泊券（1泊）が{'・'.join(map(str,tickets))}枚必要。部屋タイプで必要枚数が異なる場合があります。適用除外日・空室制限あり。入湯税等は別途必要な場合があります。予約前に公式の対象部屋・除外日をご確認ください。",
            'voucherOptions':options,'eligibilitySourceUrl':policy['eligibilitySourceUrl']}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--previous-counts',type=Path);parser.add_argument('--output',type=Path,default=ROOT/'cloudflare/generated/sync_seibu_hotels.sql');args=parser.parse_args()
    policy=json.loads(POLICY.read_text());today=datetime.now(ZoneInfo('Asia/Tokyo')).date().isoformat()
    ir=fetch(policy['sourceUrl'])
    if policy['eligibilitySourceUrl'].split('/')[-1] not in ir:raise ValueError('Seibu eligibility PDF changed; manual review required')
    with urlopen(Request(policy['eligibilitySourceUrl'],headers={'User-Agent':'YutaiMap/1.0 monthly official hotel check'}),timeout=30) as res:digest=hashlib.sha256(res.read()).hexdigest()
    if digest!=policy['eligibilitySha256']:raise ValueError('Seibu voucher conditions changed; retaining previous snapshot')
    stores=[];errors=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks={pool.submit(check_hotel,h,policy,today):h for h in policy['hotels']}
        for task in as_completed(tasks):
            try:stores.append(task.result())
            except Exception as error:errors.append(str(error));print('Location check failed:',error,flush=True)
    if errors:raise ValueError('; '.join(errors))
    stores.sort(key=lambda s:s['name'])
    if not 45<=len(stores)<=60 or len({s['id'] for s in stores})!=len(stores):raise ValueError('Abnormal Seibu hotel count')
    snapshot={'id':FEATURE,'checkedOn':today,'stores':stores}
    if args.previous_counts:
        rows=json.loads(args.previous_counts.read_text());previous={r['feature_id']:r['count'] for group in rows for r in group.get('results',[])};validate_previous([snapshot],previous)
    write_sql([snapshot],args.output,batch_id=FEATURE)
    Path('/tmp/seibu-snapshot.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2))
    print('Verified',len(stores),'Seibu hotels',flush=True)
if __name__=='__main__':main()
