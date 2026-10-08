#!/usr/bin/env python3
"""Verify GREENS voucher rules and both live hotel directories monthly."""
import argparse
import hashlib
import json
import math
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, unquote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
from scrape_kyoritsu_hotels import ROOT, Document, Node, fetch as live_fetch, validate_previous, write_sql
from scrape_daiwa_hotels import address_from_detail, domestic
from scrape_seibu_hotels import official_coordinates

FEATURE = 'greens-hotels'
IR = 'https://kk-greens.jp/ir/stock-info/dividend_benefit/'
CHOICE = 'https://www.choice-hotels.jp/hotellist/'
ORIGINAL = 'https://www.greens.co.jp/list/'
CONDITIONS = '株主様ご優待割引券（1枚1,000円）を宿泊代に利用できます。1室1泊あたり5,000円分まで（同室の株主の人数にかかわらず）。ホテルでの現地決済を選んでください。事前決済や、旅行会社・予約サイト側に代金を支払う予約は対象外。おつりは出ません。不足額は別途支払い。連泊分を合算しての利用はできません。利用条件は予約前にホテルへご確認ください。'


def fetch(url):
    cache = os.environ.get('GREENS_SOURCE_DIR')
    path = Path(cache)/hashlib.sha256(url.encode()).hexdigest() if cache else None
    if path and path.exists():return path.read_text()
    document = live_fetch(url)
    if path:
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(document)
    return document


def normalized(text):
    return re.sub(r'\s+','',text).replace('＆','&')


def verify_policy(document):
    text = normalized(Document(document).root.text())
    required = ['株主様ご優待割引券','1,000円券','発行翌年3月末まで','当社運営のホテル全店',
                '1室1泊当たり5,000円分','1室1泊あたり5,000円分が上限','連泊分の合算金額に対する利用はできません',
                '事前決済の場合はご利用いただけません','お釣りはお出しいたしません',
                '当社以外へお支払いただく場合はご利用いただけません']
    if any(term not in text for term in required):raise ValueError('GREENS voucher rules changed; manual review required')
    links = {a.attrs.get('href') for a in Document(document).root.find('a')}
    if not {'https://www.choice-hotels.jp/','https://www.greens.co.jp/'}.issubset(links):
        raise ValueError('GREENS eligible hotel brands changed')


def hotel_record(name,address,url,listing):
    parsed = urlparse(url)
    pattern = r'/(?:hotel|era|inn|suites|ascend)/[a-z0-9-]+/' if listing == CHOICE else r'/[a-z0-9-]+/'
    host = 'www.choice-hotels.jp' if listing == CHOICE else 'www.greens.co.jp'
    if parsed.scheme != 'https' or parsed.hostname != host or not re.fullmatch(pattern,parsed.path) or parsed.query or parsed.fragment:
        raise ValueError('Unverified official GREENS property URL')
    if not name or not domestic(address):raise ValueError('Missing domestic GREENS property identity')
    return {'id':'greens-'+hashlib.sha256(url.encode()).hexdigest()[:14],'name':name,'address':address,
            'sourceUrl':url,'eligibilitySourceUrl':IR,'listingSourceUrl':listing}


def parse_choice(document):
    hotels = {}
    for card in Document(document).root.find('section','p-all__hotel'):
        if re.search(r'開業予定|休業中|閉館|営業終了',card.text()):continue
        names = card.find(cls='p-all__hotel__title__name'); addresses = card.find('p','p-all__hotel__address')
        links = [a.attrs.get('href','') for a in card.find('a','c-text-link__link')]
        if len(names) != 1 or len(addresses) != 1 or len(links) != 1:raise ValueError('Changed Choice hotel card')
        name = ''.join(child.text() if isinstance(child,Node) else child for child in names[0].children).strip()
        hotel = hotel_record(name,addresses[0].text(),links[0],CHOICE)
        if hotel['sourceUrl'] in hotels:raise ValueError('Duplicate Choice hotel card')
        hotels[hotel['sourceUrl']] = hotel
    if not 85 <= len(hotels) <= 150:raise ValueError('Abnormal Choice hotel count')
    return list(hotels.values())


def parse_original(document):
    hotels = {}
    for group in Document(document).root.find('ul','wrp-list'):
        for card in [child for child in group.children if isinstance(child,Node) and child.tag == 'li']:
            if re.search(r'開業予定|休業中|閉館|営業終了',card.text()):continue
            names = card.find('span','n'); addresses = card.find('span','add')
            links = [a.attrs.get('href','') for a in card.find('a') if a.text() == 'ホテル情報']
            if len(names) != 1 or len(addresses) != 1 or len(links) != 1:raise ValueError('Changed original hotel card')
            hotel = hotel_record(names[0].text(),addresses[0].text(),links[0],ORIGINAL)
            if hotel['sourceUrl'] in hotels:raise ValueError('Duplicate original hotel card')
            hotels[hotel['sourceUrl']] = hotel
    if not 15 <= len(hotels) <= 40:raise ValueError('Abnormal original hotel count')
    return list(hotels.values())


def verify_hotel(hotel,today,detail_fetch=fetch):
    url = hotel['sourceUrl'].rstrip('/')+'/access/'
    document = detail_fetch(url)
    titles = Document(document).root.find('title')
    japanese_names = {
        'https://www.choice-hotels.jp/ascend/aroundtakayama/':'ホテルアラウンド高山',
        'https://www.choice-hotels.jp/ascend/hotelgeometiqosakaumeda/':'ホテルジオメティック大阪梅田',
        'https://www.greens.co.jp/hmpkobe/':'ホテルメリケンポート神戸元町',
    }
    expected = japanese_names.get(hotel['sourceUrl'],hotel['name'])
    if len(titles) != 1 or normalized(expected) not in normalized(titles[0].text()):
        raise ValueError('Official access page does not identify listed hotel')
    # The Inn access pages omit street addresses; use the live official
    # directory's property-specific address rather than nearby attractions.
    address = hotel['address']
    try:
        coordinates = official_coordinates(document)
    except ValueError:
        # This hotel's access page also links to Disney parks. Only resolve
        # the reviewed hotel link, and require its destination hotel identity.
        if hotel['sourceUrl'] != 'https://www.choice-hotels.jp/suites/tokyobay/':raise
        homepage = detail_fetch(hotel['sourceUrl'])
        link = 'https://goo.gl/maps/zKnWSRUL51P2'
        if link not in {a.attrs.get('href') for a in Document(homepage).root.find('a')}:
            raise ValueError('Tokyo Bay official hotel map link changed')
        with urlopen(Request(link,headers={'User-Agent':'YutaiMap/1.0 monthly official hotel check'}),timeout=30) as response:
            destination = response.url
        coordinates = resolved_hotel_map(destination,hotel['name'])
        coordinates['coordinateSourceUrl'] = link
    if not(math.isfinite(coordinates['lat']) and math.isfinite(coordinates['lng'])
           and 20 <= coordinates['lat'] <= 46 and 122 <= coordinates['lng'] <= 154):
        raise ValueError('Invalid official GREENS hotel coordinates')
    return {**hotel,'address':address,**coordinates,'addressSourceUrl':hotel['listingSourceUrl'],
            'coordinateSourceUrl':coordinates.get('coordinateSourceUrl',url),
            'verified':True,'coordinateCheckedOn':today,'conditions':CONDITIONS}


def resolved_hotel_map(destination,name):
    parsed = urlparse(destination)
    if parsed.hostname not in {'www.google.com','www.google.co.jp'} or not parsed.path.startswith('/maps/place/'):
        raise ValueError('Unexpected official hotel map destination')
    if normalized(name) not in normalized(unquote(parsed.path.split('/')[3])):
        raise ValueError('Map points to a different property')
    point = re.search(r'!3d(-?[\d.]+)!4d(-?[\d.]+)',destination)
    if not point:raise ValueError('Missing hotel map marker')
    lat,lng = map(float,point.groups())
    return {'lat':lat,'lng':lng,'coordinateSource':'公式アクセス地図'}


def main():
    parser = argparse.ArgumentParser();parser.add_argument('--previous-counts',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'cloudflare/generated/sync_greens_hotels.sql')
    args = parser.parse_args();today = datetime.now(ZoneInfo('Asia/Tokyo')).date().isoformat()
    verify_policy(fetch(IR));hotels = parse_choice(fetch(CHOICE))+parse_original(fetch(ORIGINAL))
    if len({hotel['id'] for hotel in hotels}) != len(hotels):raise ValueError('Hotel appears in both GREENS directories')
    stores = [];errors = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = {pool.submit(verify_hotel,hotel,today):hotel for hotel in hotels}
        for task in as_completed(tasks):
            try:
                store = task.result();stores.append(store);print('Verified:',store['name'],flush=True)
            except Exception as error:
                errors.append(str(error)+' '+tasks[task]['name']);print('Failed:',errors[-1],flush=True)
    if errors:raise ValueError('; '.join(errors))
    stores.sort(key=lambda store:store['name']);snapshot = {'id':FEATURE,'checkedOn':today,'stores':stores}
    if args.previous_counts:
        groups = json.loads(args.previous_counts.read_text())
        previous = {r['feature_id']:r['count'] for group in groups for r in group.get('results',[])}
        validate_previous([snapshot],previous)
    write_sql([snapshot],args.output,batch_id=FEATURE)
    Path('/tmp/greens-snapshot.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2))
    print('Verified',len(stores),'GREENS hotels',flush=True)


if __name__=='__main__':main()
