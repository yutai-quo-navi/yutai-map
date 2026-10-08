#!/usr/bin/env python3
"""Verify Wealth Management's explicit voucher hotel list and property locations."""
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
from urllib.parse import urlparse, parse_qs, unquote_plus
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from zoneinfo import ZoneInfo
from scrape_kyoritsu_hotels import ROOT, Document, PREFECTURES, fetch as live_fetch, validate_previous, write_sql
from scrape_seibu_hotels import official_coordinates

FEATURE = 'wealth-hotels'
IR = 'https://www.wealth-mngt.com/ir/return.html'
FAQ = 'https://www.wealth-mngt.com/ir/faq.html'
SUPPLEMENTS = ROOT/'data/features/wealth-hotel-coordinates.json'
# Exact issuer-listed properties. New destinations require a reviewed location
# adapter before publishing; unknown rows never silently disappear.
PROPERTIES = {
 'https://www.hotel-emisia.com/sapporo/':('ホテルエミシア札幌','https://www.hotel-emisia.com/sapporo/access/'),
 'https://www.ihg.com/holidayinn/hotels/jp/ja/sapporo/ctsop/hoteldetail':('ホリデイ・イン&スイーツ札幌大通公園',None),
 'https://www.garrya.com/ja/destinations/kyoto':('ギャリア・二条城京都',None),
 'https://www.sixsenses.com/jp/hotels-resorts/asia-the-pacific/japan/kyoto/':('シックスセンシズ京都','https://www.sixsenses.com/jp/hotels-resorts/asia-the-pacific/japan/kyoto/destination/how-to-get-there/'),
 'https://www.dhawa.com/japan/dhawa-yura-kyoto':('Dhawa Yura Kyoto',None),
 'https://www.banyantree.com/japan/kyoto':('Banyan Tree Higashiyama Kyoto',None),
 'https://hotelfauchonkyoto.com/':('フォションホテル京都','https://hotelfauchonkyoto.com/ja/access/'),
 'https://ibisosakaumeda.com/':('イビス大阪梅田','https://ibisosakaumeda.com/access'),
}
CONDITIONS = '株主様ご優待券を宿泊代に利用できます。公式サイト・電話・Eメールから直接予約し、優待利用の旨を事前にお伝えください。現地決済が必要です。現地決済を選べない場合はホテルへ直接電話・Eメールで予約してください。事前決済、旅行代理店・外部予約サイト経由、他の割引券・特典との併用は対象外。有効期間内の優待券は複数枚同時に利用できます。残額は現金またはクレジットカードでお支払いください。他の商品券・金券は併用不可。株主本人または家族の利用を想定し、転売・譲渡目的の行為は禁止されています。利用前に券面とホテルの条件をご確認ください。'


def fetch(url):
    cache = os.environ.get('WEALTH_SOURCE_DIR')
    path = Path(cache)/hashlib.sha256(url.encode()).hexdigest() if cache else None
    if path and path.exists():return path.read_text()
    document = live_fetch(url)
    if path:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(document)
    return document


def normalized(text):
    return re.sub(r'\s+','',html.unescape(text)).replace('＆','&')


def verify_policy(document):
    text = normalized(Document(document).root.text())
    required = ['ホテル宿泊のほか','株主ご本人様またはご家族様','転売や譲渡を目的とした行為は禁止',
                '複数枚同時にお使いいただけます','有効期間内であれば同時','現金またはクレジットカード',
                '他の商品券、金券などは併用できません','適用除外日はございません',
                '必ず「現地決済」をお選びください','事前決済でご予約された場合、株主優待は適用対象外',
                '他の割引券・特典との併用','旅行代理店や外部予約サイトを経由したご予約ではご利用いただけません']
    if any(term not in text for term in required):raise ValueError('Wealth voucher conditions changed; manual review required')


def parse_hotels(document):
    tables = [t for t in Document(document).root.find('table') if '株主優待利用可能ホテル' in t.text()]
    if len(tables) != 1:raise ValueError('Missing unique eligible-hotel table')
    hotels = {}
    for row in tables[0].find('tr'):
        if row.find('th'):continue
        cells = row.find('td');links = row.find('a')
        if len(cells) != 1 or len(links) != 1:raise ValueError('Changed eligible-hotel row')
        name = links[0].text();url = links[0].attrs.get('href','')
        text = cells[0].text()
        if not text.startswith(name):raise ValueError('Changed hotel address placement')
        address = text[len(name):].strip()
        if url not in PROPERTIES or not name or not any(address.startswith(p) for p in PREFECTURES):raise ValueError('Unreviewed Wealth hotel identity')
        if url in hotels:raise ValueError('Duplicate eligible hotel')
        hotels[url] = {'id':'wealth-'+hashlib.sha256(url.encode()).hexdigest()[:14],
                       'name':name,'address':address,'sourceUrl':url,'eligibilitySourceUrl':IR,'addressSourceUrl':IR}
    if set(hotels) != set(PROPERTIES):raise ValueError('Wealth eligible hotel set changed; manual review required')
    return list(hotels.values())


def embedded_coordinates(document,hotel):
    doc = Document(document);url = hotel['sourceUrl'];host = urlparse(url).hostname
    # Schema.org coordinates must belong to this exact hotel URL, not a
    # suggested resort, breadcrumb, organization, or surrounding attraction.
    for script in doc.root.find('script'):
        if script.attrs.get('type') != 'application/ld+json':continue
        obj = json.loads(script.text())
        if isinstance(obj,dict) and obj.get('@type') in {'Hotel','Resort'} and obj.get('url') == url:
            geo = obj.get('geo',{})
            if 'latitude' in geo and 'longitude' in geo:
                return {'lat':float(geo['latitude']),'lng':float(geo['longitude']),'coordinateSource':'ホテル公式構造化データ'}
    if host == 'www.dhawa.com':
        script = [s for s in doc.root.find('script') if s.attrs.get('id') == '__NEXT_DATA__']
        if len(script) != 1:raise ValueError('Missing current hotel data')
        attrs = json.loads(script[0].text())['props']['pageProps']['initialReduxState']['currentHotel']['data']['attributes']
        if attrs['path']['alias'] != urlparse(url).path or normalized(attrs['title']) != normalized(PROPERTIES[url][0]):
            raise ValueError('Current hotel data belongs to another property')
        geo = attrs['field_geolocation']
        return {'lat':float(geo['lat']),'lng':float(geo['lng']),'coordinateSource':'ホテル公式地図データ'}
    if host == 'www.garrya.com':
        script = [s for s in doc.root.find('script') if s.attrs.get('data-drupal-selector') == 'drupal-settings-json']
        if len(script) != 1:raise ValueError('Missing property map settings')
        settings = json.loads(script[0].text());node = settings['path']['currentPath'].removeprefix('node/')
        maps = settings['leaflet'];key = f'leaflet-map-node-property-{node}-field-geofield'
        points = maps[key]['features']
        if len(points) != 1 or points[0]['type'] != 'point' or str(points[0]['entity_id']) != node:
            raise ValueError('Ambiguous hotel map point')
        return {'lat':float(points[0]['lat']),'lng':float(points[0]['lon']),'coordinateSource':'ホテル公式地図データ'}
    if host == 'ibisosakaumeda.com':
        for frame in doc.root.find('iframe'):
            src = frame.attrs.get('src','');parsed = urlparse(src)
            if parsed.hostname != 'www.google.com' or parsed.path != '/maps/embed/v1/place':continue
            point = parse_qs(parsed.query).get('q',[''])[0]
            if not re.fullmatch(r'\d+(?:\.\d+)?,\d+(?:\.\d+)?',point):raise ValueError('Changed official hotel map target')
            lat,lng = map(float,point.split(','))
            return {'lat':lat,'lng':lng,'coordinateSource':'公式アクセス地図'}
    return official_coordinates(document)


def resolved_map_coordinates(destination):
    parsed = urlparse(destination)
    if parsed.hostname not in {'www.google.com','www.google.co.jp'} or not parsed.path.startswith('/maps/place/'):
        raise ValueError('Unexpected Six Senses hotel map destination')
    name = normalized(unquote_plus(parsed.path.split('/')[3])).lower()
    if not any(normalized(alias).lower() in name for alias in ['Six Senses Kyoto','シックスセンシズ京都']):
        raise ValueError('Official map identifies another property')
    match = re.search(r'!3d(-?[\d.]+)!4d(-?[\d.]+)',destination)
    if not match:raise ValueError('Missing official hotel map marker')
    lat,lng = map(float,match.groups())
    return {'lat':lat,'lng':lng,'coordinateSource':'公式アクセス地図'}


def verify_hotel_live(hotel,today,detail_fetch):
    identity,url = PROPERTIES[hotel['sourceUrl']];url = url or hotel['sourceUrl']
    document = detail_fetch(url);heads = Document(document).root.find('head')
    titles = heads[0].find('title') if len(heads) == 1 else []
    if len(titles) != 1 or normalized(identity).lower() not in normalized(titles[0].text()).lower():
        raise ValueError('Official page does not identify eligible hotel')
    if urlparse(url).hostname == 'www.sixsenses.com':
        link = 'https://maps.app.goo.gl/pAgrjew7RzqWRdrEA'
        if link not in {a.attrs.get('href') for a in Document(document).root.find('a')}:
            raise ValueError('Six Senses official map link changed')
        with urlopen(Request(link,headers={'User-Agent':'YutaiMap/1.0 monthly official hotel check'}),timeout=30) as response:
            destination = response.url
        coords = resolved_map_coordinates(destination)
    else:coords = embedded_coordinates(document,hotel)
    if not(math.isfinite(coords['lat']) and math.isfinite(coords['lng']) and 20<=coords['lat']<=46 and 122<=coords['lng']<=154):
        raise ValueError('Invalid domestic hotel coordinates')
    return {**hotel,**coords,'coordinateSourceUrl':url,'verified':True,'coordinateCheckedOn':today,'conditions':CONDITIONS}


def verify_hotel(hotel,today,detail_fetch=fetch,supplements=None):
    try:return verify_hotel_live(hotel,today,detail_fetch)
    except HTTPError as error:
        # Some hotel chains reject the GitHub runner. Do not bypass them or
        # overwrite a previously checked location with a guessed geocode.
        if error.code != 403:raise
        rows = supplements if supplements is not None else json.loads(SUPPLEMENTS.read_text())
        row = rows.get(hotel['sourceUrl'])
        if not row or row['name'] != hotel['name'] or row['address'] != hotel['address']:raise
        if not(math.isfinite(row['lat']) and math.isfinite(row['lng']) and 20<=row['lat']<=46 and 122<=row['lng']<=154):
            raise ValueError('Invalid reviewed fallback coordinates')
        coords = {k:v for k,v in row.items() if k not in {'name','address'}}
        # Keep the actual coordinate check date, distinct from this month's
        # successful issuer eligibility/address check.
        return {**hotel,**coords,'verified':True,'conditions':CONDITIONS}


def main():
    parser = argparse.ArgumentParser();parser.add_argument('--previous-counts',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'cloudflare/generated/sync_wealth_hotels.sql')
    args = parser.parse_args();today = datetime.now(ZoneInfo('Asia/Tokyo')).date().isoformat()
    verify_policy(fetch(FAQ));hotels = parse_hotels(fetch(IR));stores = [];errors = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = {pool.submit(verify_hotel,hotel,today):hotel for hotel in hotels}
        for task in as_completed(tasks):
            try:
                store = task.result();stores.append(store);print('Verified:',store['name'],flush=True)
            except Exception as error:errors.append(str(error)+' '+tasks[task]['name']);print('Failed:',errors[-1],flush=True)
    if errors:raise ValueError('; '.join(errors))
    stores.sort(key=lambda store:store['name']);snapshot = {'id':FEATURE,'checkedOn':today,'stores':stores}
    if args.previous_counts:
        groups = json.loads(args.previous_counts.read_text())
        previous = {r['feature_id']:r['count'] for group in groups for r in group.get('results',[])}
        validate_previous([snapshot],previous)
    write_sql([snapshot],args.output,batch_id=FEATURE)
    Path('/tmp/wealth-snapshot.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2))
    print('Verified',len(stores),'Wealth hotels',flush=True)

if __name__=='__main__':main()
