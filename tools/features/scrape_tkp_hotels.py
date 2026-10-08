#!/usr/bin/env python3
"""Check TKP's explicit lodging-voucher destinations and official maps monthly."""
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
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
from scrape_kyoritsu_hotels import ROOT, Document, fetch as live_fetch, validate_previous, write_sql
from scrape_seibu_hotels import official_coordinates

FEATURE = 'tkp-hotels'
IR = 'https://www.tkp.jp/ir/stock/benefit.html'
# Only destinations explicitly tagged 宿泊 on the issuer's voucher page.
# The two Lectore locations use TKP's own facility directory because the hotel
# sites render their access information in JavaScript.
PROPERTIES = {
 'https://www.tkp-resort.net/lectore/hanyu/': ('レクトーレ 羽生TERRACE', '埼玉県羽生市川崎2丁目281-3', None),
 'https://www.tkp-resort.net/lectore/yugawara/': ('グランレクトーレ 湯河原', '神奈川県足柄下郡湯河原町鍛冶屋572-1', 'https://www.tkp-resort.net/lectore/yugawara/access/'),
 'https://www.hotel-azur.com/': ('ベイサイドホテル アジュール竹芝', '東京都港区海岸1-11-2', 'https://www.hotel-azur.com/access/'),
 'https://www.ishinoya.jp/izunagaoka/': ('石のや 伊豆長岡', '静岡県伊豆の国市長岡192', None),
 'https://www.ishinoya.jp/atami/': ('ISHINOYA 熱海', '静岡県熱海市熱海1739-35 パサニアホテル棟27階', None),
 'https://lectore-atami-momoyama.jp/': ('レクトーレ 熱海桃山', '静岡県熱海市桃山町11-44', 'https://www.kashikaigishitsu.net/facilitys/lectore-atami-momoyama/access/'),
 'https://lectore-atami-koarashi.jp/': ('レクトーレ 熱海小嵐', '静岡県熱海市小嵐町15-9', 'https://www.kashikaigishitsu.net/facilitys/lectore-atami-koarashi/access/'),
 'https://slh.jp/': ('TKPサンライフホテル', '福岡県福岡市博多区博多駅東1-12-3', 'https://slh.jp/access'),
 'https://www.shoninpark.jp/guide/ishinoya/': ('ISHINOYA 別府', '大分県別府市上人ケ浜町795-1', 'https://www.shoninpark.jp/guide/ishinoya/access/'),
}
CONDITIONS = 'ご優待宿泊券を宿泊料金に利用できます。公式サイトまたは電話で直接予約し、優待券利用をお伝えください。公式サイトでは現地精算を選択してください。外部予約サイト・旅行代理店経由は対象外。券の裏面に氏名を記入し、精算時に提出してください。複数枚同時利用可、おつりは出ません。他キャンペーン・クーポン券との併用不可。予約状況により利用できない場合があります。アジュール竹芝の宴会場は対象外。施設ごとの条件・券面を予約前にご確認ください。'


def fetch(url):
    cache = os.environ.get('TKP_SOURCE_DIR')
    path = Path(cache)/hashlib.sha256(url.encode()).hexdigest() if cache else None
    if path and path.exists():return path.read_text()
    document = live_fetch(url)
    if path:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(document)
    return document


def normalized(text):
    return re.sub(r'\s+', '', html.unescape(text)).replace('＆', '&')


def verify_policy(document):
    text = normalized(Document(document).root.text())
    required = ['現地精算', '公式サイト、または施設へ直接お電話にてご予約',
                '他の旅行予約サイト、旅行代理店、グルメサイト経由',
                'ご優待券の裏面に「氏名」をご記入', 'つり銭のお支払はいたしかねます',
                'ご優待券は、複数同時にご利用いただけます',
                '他キャンペーン・クーポン券との併用はできません',
                'ご優待券の権利譲渡、売買、現金との引き換えはできません']
    if any(term not in text for term in required):raise ValueError('TKP voucher conditions changed; manual review required')


def parse_hotels(document):
    hotels = {}
    cards = [n for n in Document(document).root.find('div') if n.attrs.get('data-category')]
    if not cards:raise ValueError('Missing voucher destination cards')
    for card in cards:
        if '宿泊' not in card.attrs['data-category'].split('・'):continue
        links = [n for area in card.find('div', 'external-link-area') for n in area.find('a')]
        if len(links) != 1:raise ValueError('Ambiguous eligible hotel link')
        url = links[0].attrs.get('href');name = links[0].text()
        if url not in PROPERTIES or normalized(name) != normalized(PROPERTIES[url][0]):
            raise ValueError('Unreviewed eligible TKP hotel')
        if url in hotels:raise ValueError('Duplicate eligible hotel')
        if '公式サイトまたは電話で予約した場合のみ利用可能' not in normalized(card.text()):
            raise ValueError('Hotel reservation conditions changed')
        hotels[url] = {'id':'tkp-'+hashlib.sha256(url.encode()).hexdigest()[:14], 'name':name,
                       'sourceUrl':url, 'eligibilitySourceUrl':IR}
    if set(hotels) != set(PROPERTIES):raise ValueError('TKP lodging destination set changed; manual review required')
    return list(hotels.values())


def hotel_coordinates(document):
    # Prefer the property marker on an official Google Maps link over the map
    # viewport centre. Never use @lat,lng or a neighbouring route destination.
    markers = []
    for link in Document(document).root.find('a'):
        url = link.attrs.get('href','');parsed = urlparse(url)
        if parsed.hostname not in {'www.google.com','www.google.co.jp'} or not parsed.path.startswith('/maps/place/'):continue
        match = re.search(r'!3d(-?[\d.]+)!4d(-?[\d.]+)', url)
        if match:markers.append(tuple(map(float,match.groups())))
    if markers:
        if len(set(markers)) != 1:raise ValueError('Ambiguous property map markers')
        lat,lng = markers[0]
        return {'lat':lat,'lng':lng,'coordinateSource':'公式アクセス地図'}
    return official_coordinates(document)


def verify_hotel(hotel,today,detail_fetch=fetch):
    identity,address,access = PROPERTIES[hotel['sourceUrl']]
    url = access or hotel['sourceUrl'];document = detail_fetch(url);doc = Document(document)
    heads = doc.root.find('head');titles = heads[0].find('title') if len(heads) == 1 else []
    if len(titles) != 1 or normalized(identity).lower() not in normalized(titles[0].text()).lower():
        raise ValueError('Official access page identifies another property')
    text = normalized(doc.root.text())
    # Sunlife's own page omits its prefecture. Its issuer card supplies 福岡県;
    # match the full city/address rather than a nearby hotel listed on that page.
    match_address = address.removeprefix('福岡県') if hotel['sourceUrl']=='https://slh.jp/' else address
    if normalized(match_address) not in text:raise ValueError('Reviewed property address changed')
    coords = hotel_coordinates(document)
    if not(math.isfinite(coords['lat']) and math.isfinite(coords['lng']) and 20<=coords['lat']<=46 and 122<=coords['lng']<=154):
        raise ValueError('Invalid domestic hotel coordinates')
    return {**hotel,'address':address,**coords,'addressSourceUrl':url,'coordinateSourceUrl':url,
            'verified':True,'coordinateCheckedOn':today,'conditions':CONDITIONS}


def main():
    parser = argparse.ArgumentParser();parser.add_argument('--previous-counts',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'cloudflare/generated/sync_tkp_hotels.sql')
    args = parser.parse_args();today = datetime.now(ZoneInfo('Asia/Tokyo')).date().isoformat()
    document = fetch(IR);verify_policy(document);hotels = parse_hotels(document);stores = [];errors = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = {pool.submit(verify_hotel,hotel,today):hotel for hotel in hotels}
        for task in as_completed(tasks):
            try:store = task.result();stores.append(store);print('Verified:',store['name'],flush=True)
            except Exception as error:errors.append(str(error)+' '+tasks[task]['name']);print('Failed:',errors[-1],flush=True)
    if errors:raise ValueError('; '.join(errors))
    stores.sort(key=lambda store:store['name']);snapshot = {'id':FEATURE,'checkedOn':today,'stores':stores}
    if args.previous_counts:
        groups = json.loads(args.previous_counts.read_text())
        previous = {r['feature_id']:r['count'] for group in groups for r in group.get('results',[])}
        validate_previous([snapshot],previous)
    write_sql([snapshot],args.output,batch_id=FEATURE)
    Path('/tmp/tkp-snapshot.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2))
    print('Verified',len(stores),'TKP hotels',flush=True)

if __name__=='__main__':main()
