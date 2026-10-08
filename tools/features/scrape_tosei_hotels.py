#!/usr/bin/env python3
"""Verify TOSEI voucher eligibility and official hotel access information monthly."""
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

FEATURE = 'tosei-hotels'
IR = 'https://www.toseicorp.co.jp/ir/individual/incentive/'
CONDITIONS = 'ホテル宿泊割引券（1枚3,000円）を宿泊代に利用できます。公式サイトまたは電話で直接予約し、現地決済を選んでください。利用前にホテルへお問い合わせください。他社予約サイトや他の優待券・割引券との併用は対象外。使用枚数の制限はありませんが、おつりは出ません。不足額は別途支払い。株主以外の方も利用できます。千葉中央は対象外。'


def fetch(url):
    cache = os.environ.get('TOSEI_SOURCE_DIR')
    path = Path(cache)/hashlib.sha256(url.encode()).hexdigest() if cache else None
    if path and path.exists():return path.read_text()
    document = live_fetch(url)
    if path:
        path.parent.mkdir(parents=True,exist_ok=True); path.write_text(document)
    return document


def normalized(text):
    return re.sub(r'\s+','',text).replace('&','＆')


def verify_policy(document):
    text = normalized(Document(document).root.text())
    required = ['ホテル宿泊割引券', '3,000円分', '発行年の3月1日から翌年の2月末日',
                '予約日でなく実際のご利用日', 'ココネ千葉中央ではご利用いただけません',
                '他の優待券、割引券との併用はできません', '旅行会社', '適用できません',
                'ご宿泊のみ', '株主様以外の方のご利用も可能', '公式サイト、もしくはお電話にて直接',
                '使用枚数に制限はございません', '釣銭のお返しはできません', '現地決済のみ']
    if any(term not in text for term in required):
        raise ValueError('TOSEI voucher rules changed; manual review required')


def parse_hotels(document):
    hotels = {}
    for link in Document(document).root.find('a','m-panel'):
        names = link.find('b')
        if not names or not names[0].text().startswith('トーセイホテル'):continue
        if len(names) != 1:raise ValueError('Unexpected TOSEI eligibility card')
        name = names[0].text()
        if '千葉中央' in name:raise ValueError('Excluded hotel entered eligibility list; review required')
        if re.search(r'開業予定|休業中|閉館|営業終了',link.text()):continue
        url = link.attrs.get('href',''); parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.hostname not in {'tosei-hotel.co.jp','tosei-hotelseminar.co.jp'} or not re.fullmatch(r'/[a-z0-9-]+/',parsed.path) or parsed.query or parsed.fragment:
            raise ValueError('Unverified TOSEI hotel URL')
        if url in hotels:raise ValueError('Duplicate TOSEI eligibility card')
        hotels[url] = {'id':'tosei-'+hashlib.sha256(url.encode()).hexdigest()[:14],
                       'name':name,'sourceUrl':url,'eligibilitySourceUrl':IR}
    if not 7 <= len(hotels) <= 20:raise ValueError('Abnormal TOSEI eligible hotel count')
    return list(hotels.values())


def verify_hotel(hotel, today, detail_fetch=fetch):
    url = hotel['sourceUrl'].rstrip('/')+'/access/'
    document = detail_fetch(url)
    if normalized(hotel['name']) not in normalized(Document(document).root.text()):
        raise ValueError('Official access page does not identify eligible hotel')
    # The IR list repeats Asakusa's address for Kuramae and has an old Kanda
    # postal code. Each property's own access page is the address authority.
    address = address_from_detail(document)
    coordinates = official_coordinates(document)
    if not(math.isfinite(coordinates['lat']) and math.isfinite(coordinates['lng'])
           and 20 <= coordinates['lat'] <= 46 and 122 <= coordinates['lng'] <= 154):
        raise ValueError('Invalid official TOSEI hotel coordinates')
    return {**hotel,'address':address,**coordinates,'addressSourceUrl':url,
            'coordinateSourceUrl':coordinates.get('coordinateSourceUrl',url),
            'verified':True,'coordinateCheckedOn':today,'conditions':CONDITIONS}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--previous-counts',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'cloudflare/generated/sync_tosei_hotels.sql')
    args = parser.parse_args(); today = datetime.now(ZoneInfo('Asia/Tokyo')).date().isoformat()
    document = fetch(IR); verify_policy(document); hotels = parse_hotels(document)
    stores = []; errors = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = {pool.submit(verify_hotel,hotel,today):hotel for hotel in hotels}
        for task in as_completed(tasks):
            try:
                store = task.result(); stores.append(store); print('Verified:',store['name'],flush=True)
            except Exception as error:
                errors.append(str(error)+' '+tasks[task]['name']); print('Failed:',errors[-1],flush=True)
    if errors:raise ValueError('; '.join(errors))
    stores.sort(key=lambda store:store['name'])
    snapshot = {'id':FEATURE,'checkedOn':today,'stores':stores}
    if args.previous_counts:
        groups = json.loads(args.previous_counts.read_text())
        previous = {r['feature_id']:r['count'] for group in groups for r in group.get('results',[])}
        validate_previous([snapshot],previous)
    write_sql([snapshot],args.output,batch_id=FEATURE)
    Path('/tmp/tosei-snapshot.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2))
    print('Verified',len(stores),'TOSEI hotels',flush=True)


if __name__=='__main__':main()
