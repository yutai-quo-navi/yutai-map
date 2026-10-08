#!/usr/bin/env python3
"""Verify Wakita's eligible hotels, direct-booking policy and official map markers."""
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
from urllib.parse import unquote_plus, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
from scrape_kyoritsu_hotels import ROOT, Document, fetch as live_fetch, validate_previous, write_sql

FEATURE = 'wakita-hotels'
IR = 'https://www.wakita.co.jp/ir/share_information/return/'
DIRECTORY = 'https://www.wakita.co.jp/business/estate/'
PROPERTIES = {
 'https://cordia-osaka.com/': ('ホテルコルディア大阪','大阪府大阪市西区江戸堀1-3-25','https://maps.app.goo.gl/YVt8zCQU8t7YPssF9'),
 'https://cordia-osaka.com/hommachi/': ('ホテルコルディア大阪本町','大阪府大阪市中央区本町4-6-14','https://goo.gl/maps/dfFXvzFx3MxoTuxNA'),
}
CONDITIONS = 'ホテル公式サイトでのウェブ予約、またはホテルへの直接電話予約が利用可能です。必ず「現地払い（現地決済）」を選択し、ホテルで電子優待券を提示して精算してください。事前のクレジットカード決済では優待券を利用できません。外部の宿泊予約サイト・旅行会社経由、航空券・新幹線とのセット予約は対象外。期限は予約日ではなく実際の宿泊日が基準です。食事のみ・併設レストラン単独、キャンセル料等には利用できません。電子チケットのスクリーンショット・写真・コピーは不可。利用前に券面と公式の条件をご確認ください。'


def fetch(url):
    cache = os.environ.get('WAKITA_SOURCE_DIR')
    path = Path(cache)/hashlib.sha256(url.encode()).hexdigest() if cache else None
    if path and path.exists():return path.read_text()
    document = live_fetch(url)
    if path:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(document)
    return document


def normalized(text):
    return re.sub(r'\s+','',html.unescape(text)).translate(str.maketrans('０１２３４５６７８９－','0123456789-'))


def verify_eligibility(document):
    text = normalized(Document(document).root.text())
    match = re.search('株主優待電子チケットはどこの店舗で利用できますか？(.*?)で利用可能です。',text)
    expected = '、'.join(row[0] for row in PROPERTIES.values())
    if not match or match[1] != expected:raise ValueError('Wakita eligible hotel set changed; manual review required')
    if 'ホテル公式ホームページでの予約および直接電話での予約に限定' not in text:
        raise ValueError('Wakita booking policy changed')


def parse_hotels(document):
    hotels = {}
    for card in Document(document).root.find('li','estate-hotel-card'):
        links = card.find('a','estate-hotel-card__site');names = card.find('h3','estate-hotel-card__name')
        if len(links) != 1 or len(names) != 1:raise ValueError('Changed issuer hotel card')
        url = links[0].attrs.get('href','');name = names[0].text()
        if url not in PROPERTIES or normalized(name) != normalized(PROPERTIES[url][0]):raise ValueError('Unreviewed issuer hotel')
        if url in hotels:raise ValueError('Duplicate issuer hotel')
        address = PROPERTIES[url][1]
        if normalized(address) not in normalized(card.text()):raise ValueError('Hotel address changed')
        hotels[url] = {'id':'wakita-'+hashlib.sha256(url.encode()).hexdigest()[:14],'name':name,
                       'address':address,'sourceUrl':url,'eligibilitySourceUrl':IR,'addressSourceUrl':DIRECTORY}
    if set(hotels) != set(PROPERTIES):raise ValueError('Missing eligible Wakita hotel')
    return list(hotels.values())


def verify_policy(document):
    text = normalized(Document(document).root.text())
    required = ['ホテル公式ホームページ予約および電話予約のみ','「現地決済」予約に限ります',
                '航空券及び新幹線とのセット予約にご利用いただけません',
                '食事のみでは利用できません','キャンセル料、フロント販売、宅配代、ランドリー代には利用不可']
    if any(term not in text for term in required):raise ValueError('Hotel voucher payment conditions changed; manual review required')


def map_destination(link):
    cache = os.environ.get('WAKITA_SOURCE_DIR')
    path = Path(cache)/hashlib.sha256(link.encode()).hexdigest() if cache else None
    if path and path.exists():return path.read_text()
    with urlopen(Request(link,headers={'User-Agent':'YutaiMap/1.0 monthly official hotel check'}),timeout=30) as response:
        return response.url


def resolved_coordinates(destination,identity):
    parsed = urlparse(destination)
    if parsed.hostname not in {'www.google.com','www.google.co.jp'} or not parsed.path.startswith('/maps/place/'):
        raise ValueError('Unexpected official map destination')
    name = normalized(unquote_plus(parsed.path.split('/')[3]))
    # 大阪 is a prefix of 大阪本町: exact property identity is required.
    if name != identity and not (identity=='ホテルコルディア大阪' and name=='ホテルコルディア大阪（HOTELCORDIAOSAKA）'):
        raise ValueError('Map identifies another property')
    points = re.findall(r'!3d(-?[\d.]+)!4d(-?[\d.]+)',destination)
    if len(set(points)) != 1:raise ValueError('Missing or ambiguous official hotel marker')
    lat,lng = map(float,points[0])
    if not(math.isfinite(lat) and math.isfinite(lng) and 20<=lat<=46 and 122<=lng<=154):raise ValueError('Invalid domestic coordinates')
    return {'lat':lat,'lng':lng,'coordinateSource':'ホテル公式アクセス地図'}


def verify_hotel(hotel,today,detail_fetch=fetch,resolve=map_destination):
    url = hotel['sourceUrl'];identity,address,link = PROPERTIES[url]
    access = url+'access';doc = Document(detail_fetch(access))
    heads = doc.root.find('head');titles = heads[0].find('title') if len(heads)==1 else []
    if len(titles)!=1 or normalized(identity) not in normalized(titles[0].text()):raise ValueError('Wrong official access page')
    # 本町's footer uses 4丁目6－14 and omits 大阪府.
    match_address = address.removeprefix('大阪府').replace('4-6-14','4丁目6-14') if url.endswith('/hommachi/') else address
    if normalized(match_address) not in normalized(doc.root.text()):raise ValueError('Official hotel address changed')
    if link not in {a.attrs.get('href') for a in doc.root.find('a')}:raise ValueError('Official map link changed')
    verify_policy(detail_fetch(url+'faq/'))
    coords = resolved_coordinates(resolve(link),identity)
    return {**hotel,**coords,'coordinateSourceUrl':access,'coordinateCheckedOn':today,'verified':True,'conditions':CONDITIONS}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--previous-counts',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'cloudflare/generated/sync_wakita_hotels.sql')
    args=parser.parse_args();today=datetime.now(ZoneInfo('Asia/Tokyo')).date().isoformat()
    verify_eligibility(fetch(IR));hotels=parse_hotels(fetch(DIRECTORY));stores=[];errors=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks={pool.submit(verify_hotel,hotel,today):hotel for hotel in hotels}
        for task in as_completed(tasks):
            try:store=task.result();stores.append(store);print('Verified:',store['name'],flush=True)
            except Exception as error:errors.append(str(error)+' '+tasks[task]['name']);print('Failed:',errors[-1],flush=True)
    if errors:raise ValueError('; '.join(errors))
    stores.sort(key=lambda store:store['name']);snapshot={'id':FEATURE,'checkedOn':today,'stores':stores}
    if args.previous_counts:
        groups=json.loads(args.previous_counts.read_text())
        previous={r['feature_id']:r['count'] for group in groups for r in group.get('results',[])}
        validate_previous([snapshot],previous)
    write_sql([snapshot],args.output,batch_id=FEATURE)
    Path('/tmp/wakita-snapshot.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2))
    print('Verified',len(stores),'Wakita hotels',flush=True)

if __name__=='__main__':main()
