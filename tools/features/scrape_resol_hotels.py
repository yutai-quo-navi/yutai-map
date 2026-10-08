#!/usr/bin/env python3
"""Verify RESOL voucher lodging eligibility and official map coordinates monthly."""
import argparse
import hashlib
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
from scrape_daiwa_hotels import address_from_detail
from scrape_seibu_hotels import official_coordinates

FEATURE = 'resol-hotels'
MENU = 'https://www.resol.jp/ir/kabunushi/menu/'
POLICY = 'https://www.resol.jp/ir/kabunushi/2026/'
CONDITIONS = 'RESOLファミリー商品券と有効期間内の株主カードが必要です。公式サイト・電話から直接予約し、現地で精算してください。他社予約サイトは対象外。1日1精算・最大50枚（発行枚数まで）。おつりは出ません。不足額・入湯税等は別途支払い。利用対象者・除外日等は公式でご確認ください。'


def fetch(url):
    cache = os.environ.get('RESOL_SOURCE_DIR')
    path = Path(cache)/hashlib.sha256(url.encode()).hexdigest() if cache else None
    if path and path.exists():
        return path.read_text()
    document = live_fetch(url)
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(document)
    return document


def verify_policy(document):
    text = Document(document).root.text()
    required = ['RESOLファミリー商品券', '株主カード', '1日1精算', '上限50枚',
                '公式サイト又はお電話', '他社様の予約サービス', '釣銭', '入湯税', '2親等以内']
    if any(word not in text for word in required):
        raise ValueError('RESOL voucher policy changed; manual review required')


def parse_hotels(document):
    hotels = {}
    for table in Document(document).root.find('table'):
        rows = table.find('tr')
        if not rows or '宿泊プラン' not in rows[0].text():
            continue
        for row in rows[1:]:
            cells = row.find('td')
            if len(cells) < 2 or not cells[1].text().startswith('○'):
                continue
            links = [a for a in cells[0].find('a') if a.attrs.get('href', '').startswith('https://')]
            if len(links) != 1:
                raise ValueError('Unexpected RESOL eligibility row')
            link = links[0]; url = link.attrs['href']
            if urlparse(url).hostname not in {'www.resol-hotel.jp', 'www.resol-no-mori.com', 'www.resol-golf.jp', 'www.mannacc.com'}:
                raise ValueError('Unexpected official RESOL property host')
            if urlparse(url).hostname == 'www.mannacc.com':
                continue  # Golf course inside the already listed Resol no Mori resort.
            name = re.sub(r'\s*（[^）]*）$', '', link.text()).strip()
            hotels[url] = {'id': 'resol-'+hashlib.sha256(url.encode()).hexdigest()[:14],
                           'name': name, 'sourceUrl': url, 'eligibilitySourceUrl': MENU}
    if not 20 <= len(hotels) <= 40:
        raise ValueError('Abnormal RESOL lodging eligibility count')
    return list(hotels.values())


def verify_hotel(hotel, today, detail_fetch=fetch):
    url = hotel['sourceUrl'].rstrip('/')+('/location/' if urlparse(hotel['sourceUrl']).hostname == 'www.resol-no-mori.com' else '/access/')
    document = detail_fetch(url)
    address = address_from_detail(document)
    try:
        coordinates = official_coordinates(document)
    except ValueError:
        if urlparse(url).hostname != 'www.resol-no-mori.com':
            raise
        markers = re.findall(r"new google\.maps\.Marker\(\{\s*position:\s*new google\.maps\.LatLng\(([-0-9.]+),\s*([-0-9.]+)\),\s*map:\s*map,\s*title:\s*'リソルの森'", document)
        if len(markers) != 1:
            raise ValueError('Missing named official Resol no Mori map marker')
        lat, lng = map(float, markers[0])
        coordinates = {'lat':lat, 'lng':lng, 'coordinateSource':'公式アクセス地図',
                       'coordinateSourceUrl':url, 'coordinateNote':'距離は広いリゾート敷地の代表位置を使った目安です。宿泊エリアにより受付場所が異なります。'}
    if not (math.isfinite(coordinates['lat']) and math.isfinite(coordinates['lng'])
            and 20 <= coordinates['lat'] <= 46 and 122 <= coordinates['lng'] <= 154):
        raise ValueError('Invalid official RESOL hotel coordinates')
    return {**hotel, 'address': address, **coordinates, 'addressSourceUrl': url,
            'verified': True, 'coordinateCheckedOn': today, 'conditions': CONDITIONS}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--previous-counts', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT/'cloudflare/generated/sync_resol_hotels.sql')
    args = parser.parse_args()
    today = datetime.now(ZoneInfo('Asia/Tokyo')).date().isoformat()
    verify_policy(fetch(POLICY))
    hotels = parse_hotels(fetch(MENU))
    stores = []; errors = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = {pool.submit(verify_hotel, hotel, today):hotel for hotel in hotels}
        for task in as_completed(tasks):
            try:
                store = task.result(); stores.append(store)
                print('Verified:',store['name'], flush=True)
            except Exception as error:
                errors.append(str(error)+' '+tasks[task]['name']); print('Failed:',errors[-1],flush=True)
    if errors:
        raise ValueError('; '.join(errors))
    stores.sort(key=lambda s:s['name'])
    snapshot = {'id': FEATURE, 'checkedOn': today, 'stores': stores}
    if args.previous_counts:
        groups = json.loads(args.previous_counts.read_text())
        previous = {r['feature_id']:r['count'] for group in groups for r in group.get('results',[])}
        validate_previous([snapshot],previous)
    write_sql([snapshot],args.output,batch_id=FEATURE)
    Path('/tmp/resol-snapshot.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2))
    print('Verified',len(stores),'RESOL lodging facilities',flush=True)


if __name__ == '__main__':
    main()
