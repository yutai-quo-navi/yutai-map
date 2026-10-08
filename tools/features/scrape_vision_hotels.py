#!/usr/bin/env python3
"""Verify Vision's lodging-voucher destinations and official property locations."""
import argparse
import hashlib
import html
import json
import math
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from scrape_kyoritsu_hotels import ROOT, Document, fetch as live_fetch, validate_previous, write_sql
from scrape_seibu_hotels import official_coordinates

FEATURE = 'vision-hotels'
IR = 'https://www.vision-net.co.jp/stocks'
FAQ = 'https://www.vision-net.co.jp/ir/benefit_faq.html'
PROPERTIES = {
 'https://vision-glamping.com/yamanakako': ('ビジョングランピングリゾート山中湖','山梨県南都留郡山中湖村山中字栗木林1385-43','https://vision-glamping.com/yamanakako/access'),
 'https://koshikano-onsen.com/': ('美肌の湯 こしかの温泉','鹿児島県霧島市隼人町松永2625','https://koshikano-onsen.com/access'),
}
CONDITIONS = '株主様専用ダイヤル0120-390-388（9:00～18:00）での電話予約が必要です。一般の公式ウェブ予約・外部予約サイト経由は対象外。案内の2次元コードから取得したクーポンコードを用意してください。1室1泊あたり宿泊費を最大29,000円分割引。同年中に発行された優待券のみ併用可。他の割引サービス・金券との併用不可。食事などのオプション・入湯税は対象外で、差額は別途支払いが必要です。申込期限と宿泊期限は別です。予約時に券の発行回・期限・利用条件をご確認ください。'


def fetch(url):
    cache = os.environ.get('VISION_SOURCE_DIR')
    path = Path(cache)/hashlib.sha256(url.encode()).hexdigest() if cache else None
    if path and path.exists():return path.read_text()
    document = live_fetch(url)
    if path:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(document)
    return document


def normalized(text):
    return re.sub(r'\s+','',html.unescape(text)).translate(str.maketrans('０１２３４５６７８９','0123456789'))


def parse_hotels(document):
    doc = Document(document)
    areas = [n for n in doc.root.find('div') if n.attrs.get('id')=='vision_glamping_container']
    lists = doc.root.find('div','stockWrapContent06')
    lists = [n for n in lists if n.text().startswith('利用可能施設')]
    if len(areas)!=1 or len(lists)!=1:raise ValueError('Missing unique eligible lodging section')
    names = re.findall(r'(ビジョングランピングリゾート[^()]+|美肌の湯[^()]+)\(',normalized(lists[0].text()))
    if names != [normalized(row[0]) for row in PROPERTIES.values()]:raise ValueError('Vision eligible hotel names changed')
    links = areas[0].find('a');hotels={}
    for a in links:
        url=a.attrs.get('href','')
        if url not in PROPERTIES or url in hotels:raise ValueError('Unreviewed or duplicate eligible hotel link')
        name=PROPERTIES[url][0]
        if normalized(name).removeprefix('美肌の湯') not in normalized(a.text()):raise ValueError('Changed eligible hotel label')
        hotels[url]={'id':'vision-'+hashlib.sha256(url.encode()).hexdigest()[:14],'name':name,'sourceUrl':url,'eligibilitySourceUrl':IR}
    if set(hotels)!=set(PROPERTIES):raise ValueError('Vision eligible property set changed; manual review required')
    return list(hotels.values())


def verify_policy(document):
    text=normalized(Document(document).root.text())
    required=['宿泊費のみ割引対象','入湯税などもご利用いただけません','1泊あたり最大29,000円分（1部屋ごと）',
              '株主専用ダイヤルからのご予約のみ適用可能','0120-390-388','受付時間9:00-18:00',
              '同年中に発行された株主優待券（クーポンコード）のみ併用可能',
              '他の割引特典や金券、その他割引サービスとの併用はできません']
    if any(term not in text for term in required):raise ValueError('Vision voucher reservation conditions changed; manual review required')


def lodging_data(document,url,identity):
    matches=[]
    for script in Document(document).root.find('script'):
        if script.attrs.get('type')!='application/ld+json':continue
        data=json.loads(script.text())
        for obj in data.get('@graph',[data]):
            types=obj.get('@type',[]);types=[types] if isinstance(types,str) else types
            if 'LodgingBusiness' in types and obj.get('url')==url and normalized(obj.get('name',''))==normalized(identity):matches.append(obj)
    if len(matches)!=1:raise ValueError('Missing unique official lodging identity')
    return matches[0]


def verify_hotel(hotel,today,detail_fetch=fetch):
    url=hotel['sourceUrl'];name,address,access=PROPERTIES[url]
    data=lodging_data(detail_fetch(url),url,name)
    postal=data.get('address',{});current=''.join(postal.get(k,'') for k in ['addressRegion','addressLocality','streetAddress'])
    if current!=address or postal.get('addressCountry')!='JP':raise ValueError('Reviewed official address changed')
    if 'geo' in data:
        geo=data['geo'];coords={'lat':float(geo['latitude']),'lng':float(geo['longitude']),'coordinateSource':'ホテル公式構造化データ'};source=url
    else:
        document=detail_fetch(access);doc=Document(document)
        heads=doc.root.find('head');titles=heads[0].find('title') if len(heads)==1 else []
        if len(titles)!=1 or '山中湖' not in titles[0].text() or not any(term in titles[0].text() for term in ['アクセス','交通案内']):raise ValueError('Wrong official access page')
        coords=official_coordinates(document);source=access
    if not(math.isfinite(coords['lat']) and math.isfinite(coords['lng']) and 20<=coords['lat']<=46 and 122<=coords['lng']<=154):raise ValueError('Invalid domestic coordinates')
    return {**hotel,'address':address,**coords,'addressSourceUrl':url,'coordinateSourceUrl':source,'coordinateCheckedOn':today,'verified':True,'conditions':CONDITIONS}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--previous-counts',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'cloudflare/generated/sync_vision_hotels.sql')
    args=parser.parse_args();today=datetime.now(ZoneInfo('Asia/Tokyo')).date().isoformat()
    verify_policy(fetch(FAQ));hotels=parse_hotels(fetch(IR));stores=[];errors=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks={pool.submit(verify_hotel,hotel,today):hotel for hotel in hotels}
        for task in as_completed(tasks):
            try:store=task.result();stores.append(store);print('Verified:',store['name'],flush=True)
            except Exception as error:errors.append(str(error)+' '+tasks[task]['name']);print('Failed:',errors[-1],flush=True)
    if errors:raise ValueError('; '.join(errors))
    stores.sort(key=lambda store:store['name']);snapshot={'id':FEATURE,'checkedOn':today,'stores':stores}
    if args.previous_counts:
        groups=json.loads(args.previous_counts.read_text());previous={r['feature_id']:r['count'] for group in groups for r in group.get('results',[])}
        validate_previous([snapshot],previous)
    write_sql([snapshot],args.output,batch_id=FEATURE)
    Path('/tmp/vision-snapshot.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2))
    print('Verified',len(stores),'Vision hotels',flush=True)

if __name__=='__main__':main()
