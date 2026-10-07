#!/usr/bin/env python3
"""Verify Daiwa House hotel voucher locations; never infer voucher expiry."""
import argparse
import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
from scrape_kyoritsu_hotels import (Document, PREFECTURES, ROOT, fetch,
    future_opening, parse_coordinates, validate_previous, write_sql)

IR = 'https://www.daiwahouse.co.jp/ir/yutai/'
ROY = 'https://www.daiwaroynet.jp/hotelist/'
LAGENT = 'https://lagent.jp/'
RELEASE = 'https://www.daiwahouse.co.jp/about/release/house/pdf/release_20260213-3.pdf'
RELEASE_SHA256 = '7d19f09b4e07c26973cc39e066e349898f5c77bf3853ad54dc2d7668c3958967'
FEATURE = 'daiwa-house-hotels'
EXCLUDED_LAGENT = {'sapporo-odori', 'hakodate-ekimae'}
CONDITIONS = '株主優待の共通商品券を宿泊代の支払いに利用できます。現地払いを選び、支払い時に券をお渡しください。1,000円単位・おつりは出ません。券面額を超える分は別途支払いが必要です。ホテル内の入居店舗は対象外。予約時に利用条件をご確認ください。'


def verify_policy(document, release_digest):
    text = Document(document).root.text()
    required = ['共通商品券', 'ダイワロイネットホテルズでの宿泊', 'ラ・ジェント・ホテルでの宿泊',
                'ラ・ジェント・ステイ札幌大通', 'ラ・ジェント・ステイ函館駅前',
                'ご利用対象外', '1,000円単位', 'おつりは返金いたしません']
    if any(term not in text for term in required) or RELEASE not in document or release_digest != RELEASE_SHA256:
        raise ValueError('Daiwa voucher policy changed; keeping previous verified dataset')


def domestic(address):
    return bool(re.match(r'〒\s*\d{3}-\d{4}\s*(?:' + '|'.join(PREFECTURES) + '|大阪市|京都市)', address))


def parse_roy(document, today):
    hotels = {}
    for card in Document(document).root.find('div', 'wrp_hotel'):
        names, addresses = card.find(cls='n'), card.find('address')
        links = [a.attrs.get('href', '') for a in card.find('a') if a.text() == 'ホテルサイトはこちら']
        if not names or not addresses or len(links) != 1:
            continue
        address = addresses[0].text()
        if not domestic(address):
            continue  # Overseas properties are not part of this domestic feature.
        if future_opening(card.text(), today) or re.search(r'休業中|閉館|営業終了', card.text()):
            continue
        url = urljoin(ROY, links[0]); alias = urlparse(url).path.strip('/')
        if urlparse(url).hostname != 'www.daiwaroynet.jp' or not re.fullmatch(r'[a-z0-9-]+', alias):
            raise ValueError('Unexpected Roynet hotel URL')
        hotel = {'id':'roy-'+alias, 'name':names[0].text(), 'address':address,
                 'sourceUrl':url, 'hotelGroup':'ダイワロイネットホテルズ'}
        maps = [a.attrs.get('href','') for a in card.find('a') if a.text() == 'マップで場所を確認']
        if len(maps) == 1 and urlparse(maps[0]).hostname == 'www.google.com':
            ll = parse_qs(urlparse(maps[0]).query).get('ll', [])
            if ll and re.fullmatch(r'[0-9.]+,[0-9.]+', ll[0]):
                lat, lng = map(float, ll[0].split(','))
                hotel['listingCoordinates'] = {'lat':lat,'lng':lng,'coordinateSource':'公式ホテル一覧のアクセス地図',
                    'coordinateSourceUrl':maps[0], 'coordinateNote':'距離は公式アクセス地図の中心位置を使った目安です。'}
        if url in hotels and hotels[url] != hotel:
            raise ValueError('Conflicting repeated hotel card')
        hotels[url] = hotel
    if not hotels:
        raise ValueError('No domestic Roynet hotel cards')
    return list(hotels.values())


def parse_lagent(document, today):
    hotels = {}
    exclusions = set()
    for group in Document(document).root.find('ul', 'hotellist'):
        for card in group.find('li'):
            names = card.find(cls='c-txt-l')
            links = [a.attrs.get('href', '') for a in card.find('a') if a.text() == 'ホテルサイト']
            if not names or len(links) != 1:
                continue
            url = links[0]; alias = urlparse(url).path.strip('/')
            if urlparse(url).hostname != 'lagent.jp' or not re.fullmatch(r'[a-z0-9-]+', alias):
                raise ValueError('Unexpected Lagent hotel URL')
            if alias in EXCLUDED_LAGENT:
                exclusions.add(alias); continue
            if future_opening(card.text(), today) or re.search(r'休業中|閉館|営業終了', card.text()):
                continue
            hotel = {'id':'lagent-'+alias, 'name':names[0].text(), 'sourceUrl':url, 'hotelGroup':'ラ・ジェント'}
            if url in hotels and hotels[url] != hotel:
                raise ValueError('Conflicting Lagent hotel card')
            hotels[url] = hotel
    if exclusions != EXCLUDED_LAGENT or not hotels:
        raise ValueError('Lagent eligibility listing changed')
    return list(hotels.values())


def address_from_detail(document):
    doc = Document(document)
    for node in doc.root.find('address') + doc.root.find('p') + [doc.root]:
        match = re.search(r'〒\s*\d{3}-\d{4}\s*(?:' + '|'.join(PREFECTURES) + r'|大阪市|京都市)[^〒]{1,150}', node.text())
        if match:
            address = re.split(r'【|TEL|電話|FAX', match.group())[0].strip()
            return address
    raise ValueError('Missing official domestic hotel address')


def verify_hotel(hotel, detail_fetch, supplements, today):
    time.sleep(.35)
    document = detail_fetch(hotel['sourceUrl'])
    access_document = None
    if 'address' not in hotel:
        try:
            hotel['address'] = address_from_detail(document)
        except ValueError:
            access_document = detail_fetch(hotel['sourceUrl']+'access/')
            try:
                hotel['address'] = address_from_detail(access_document)
                hotel['addressSourceUrl'] = hotel['sourceUrl']+'access/'
            except ValueError as error:
                raise ValueError('Missing official address: '+hotel['sourceUrl']) from error
    if not domestic(hotel['address']):
        raise ValueError('Unverified domestic address')
    extra = supplements.get(hotel['id'])
    matched = extra and extra['name'] == hotel['name'] and extra['address'] == hotel['address']
    if matched and extra.get('preferSupplement'):
        coords = {k:v for k,v in extra.items() if k not in {'name','address','preferSupplement'}}
    else:
        try:
            coords = parse_coordinates(document)
        except ValueError:
            try:
                coords = parse_coordinates(access_document if access_document is not None else detail_fetch(hotel['sourceUrl']+'access/'))
            except Exception:
                if matched:
                    coords = {k:v for k,v in extra.items() if k not in {'name','address','preferSupplement'}}
                elif hotel.get('listingCoordinates'):
                    coords = hotel['listingCoordinates']
                else:
                    raise ValueError('Unverified coordinates: '+hotel['id'])
    import math
    if not (math.isfinite(coords['lat']) and math.isfinite(coords['lng']) and 20 <= coords['lat'] <= 46 and 122 <= coords['lng'] <= 154):
        raise ValueError('Invalid hotel coordinates')
    hotel = {k:v for k,v in hotel.items() if k != 'listingCoordinates'}
    return {**hotel, **coords, 'verified':True, 'coordinateCheckedOn':today.isoformat(),
            'conditions':CONDITIONS,
            'eligibilitySourceUrl':RELEASE if hotel['id']=='nikko-oita' else IR}


def build_snapshot(ir, roy, lagent, digest, detail_fetch=fetch, today=None, supplements=None, reviewed_policy=None):
    today = today or datetime.now(ZoneInfo('Asia/Tokyo')).date()
    if reviewed_policy is None:
        verify_policy(ir, digest)
    elif (reviewed_policy.get('sourceUrl') != IR or reviewed_policy.get('releaseUrl') != RELEASE
          or reviewed_policy.get('releaseSha256') != RELEASE_SHA256
          or set(reviewed_policy.get('excludedLagent', [])) != EXCLUDED_LAGENT
          or reviewed_policy.get('checkedOn') != '2026-10-08'):
        raise ValueError('Reviewed eligibility policy changed; manual review required')
    hotels = parse_roy(roy, today) + parse_lagent(lagent, today)
    hotels.append({'id':'nikko-oita','name':'ホテル日航大分 オアシスタワー',
                   'sourceUrl':'https://www.nikko-oita.oasistower.co.jp/',
                   'hotelGroup':'ホテル日航大分 オアシスタワー'})
    with ThreadPoolExecutor(max_workers=2) as pool:
        stores = list(pool.map(lambda h: verify_hotel(h, detail_fetch, supplements or {}, today), hotels))
    if not 75 <= len(stores) <= 120 or len({s['id'] for s in stores}) != len(stores):
        raise ValueError('Abnormal or duplicate hotel count')
    return {'id':FEATURE, 'checkedOn':today.isoformat(), 'stores':stores}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT/'cloudflare/generated/sync_daiwa_hotels.sql')
    parser.add_argument('--previous-counts', type=Path)
    args = parser.parse_args()
    # Eligibility was reviewed against the official IR, guide and release.
    # Its host rejects CI downloads; monthly checks cover live hotel directories.
    policy = json.loads((ROOT/'data/features/daiwa-hotel-policy.json').read_text())
    supplements = json.loads((ROOT/'data/features/daiwa-hotel-coordinates.json').read_text())
    snapshot = build_snapshot('', fetch(ROY), fetch(LAGENT), '', supplements=supplements, reviewed_policy=policy)
    if args.previous_counts:
        groups = json.loads(args.previous_counts.read_text())
        previous = {r['feature_id']:r['count'] for group in groups for r in group.get('results', [])}
        validate_previous([snapshot], previous)
    write_sql([snapshot], args.output, batch_id='daiwa-hotels')
    print(FEATURE, len(snapshot['stores']), 'hotels, checked', snapshot['checkedOn'])


if __name__ == '__main__':
    main()
