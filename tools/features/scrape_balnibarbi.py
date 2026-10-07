#!/usr/bin/env python3
"""Refresh the private feature snapshot from the official directory and map."""
import argparse
import html
import gzip
import json
import math
import re
import time
from datetime import date, datetime
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

BASE = 'https://brands.balnibarbi.com'
FEATURE_ID = 'balnibarbi-dining'
ROOT = Path(__file__).resolve().parents[2]
ELIGIBLE = {'対応', 'レストラン・ホテル共に対応'}


def text(value):
    value = re.sub(r'<!--.*?-->', '', str(value or ''), flags=re.S)
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]*>', ' ', value))).strip()


def jp_date(value):
    match = re.search(r'(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日', text(value))
    return date(*map(int, match.groups())) if match else None


def fetch(url):
    # Serial requests, with bounded retries. A failed fetch never replaces D1 state.
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={'User-Agent':'YutaiMap/1.0 (official directory sync)'}), timeout=45) as response:
                payload = response.read()
                if response.headers.get('Content-Encoding') == 'gzip' or payload.startswith(b'\x1f\x8b'):
                    payload = gzip.decompress(payload)
                return payload.decode('utf-8-sig')
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def parse_listing(document):
    shops = {}
    for item in re.findall(r'<li\s+class="shop-item"[^>]*>(.*?)</li>', document, re.S):
        link = re.search(r'href="(/brands/(restaurants|hotels|shops|facilities|complexes)/[a-zA-Z0-9_-]+)"', item)
        if link:
            shops[link[1]] = text(item)
    if not shops:
        raise ValueError('Official listing structure changed')
    return shops


def parse_map(document):
    marker = 'window.brandsMapData = '
    if marker not in document:
        raise ValueError('Official map structure changed')
    data, _ = json.JSONDecoder().raw_decode(document.split(marker, 1)[1].lstrip())
    if not isinstance(data.get('shopdata'), dict) or not data['shopdata']:
        raise ValueError('Missing official map shops')
    return data['shopdata']


def inactive(value, today):
    value = text(value)
    opening = jp_date(value)
    return bool(re.search(r'休業中|閉店|営業終了', value) or (opening and opening > today))


def store_record(path, name, address, lat, lng, shareholder):
    lat, lng = float(lat), float(lng)
    if not (math.isfinite(lat) and math.isfinite(lng) and 20 <= lat <= 46 and 122 <= lng <= 154):
        raise ValueError('Missing or invalid official coordinates: ' + path)
    if not text(name) or not text(address):
        raise ValueError('Missing official name/address: ' + path)
    return {'id':path.removeprefix('/brands/').replace('/', '-'),
            'name':text(name), 'address':text(address), 'lat':lat, 'lng':lng,
            'verified':True, 'sourceUrl':BASE + path,
            'conditions':'公式の株主優待表示：' + shareholder + '。対象商品・支払い方法などの条件は店舗と券面をご確認ください。'}


def parse_detail(document, path, today):
    fields = {text(k):text(v) for k,v in re.findall(r'<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>', document, re.S)}
    if '株主優待' not in fields:
        raise ValueError('Missing shareholder field: ' + path)
    if fields['株主優待'] not in ELIGIBLE:
        return None
    opening = jp_date(fields.get('オープン日'))
    if opening and opening > today:
        return None
    heading = re.search(r'<span\s+class="main[^"]*"[^>]*>(.*?)</span>', document, re.S) or re.search(r'<h1\b[^>]*>(.*?)</h1>', document, re.S)
    # The embed's viewport center is offset from the pin. Prefer its explicit
    # marker coordinates (!3d latitude !4d longitude), falling back to viewport.
    iframe = re.search(r'<iframe\b[^>]*(?:data-src|src)="([^"]*google\.com/maps/embed[^"]*)"', document)
    coords = re.search(r'!3d(-?[\d.]+)!4d(-?[\d.]+)', html.unescape(iframe[1])) if iframe else None
    if coords:
        lat, lng = coords.groups()
    else:
        coords = re.search(r'!2d(-?[\d.]+)!3d(-?[\d.]+)', html.unescape(iframe[1])) if iframe else None
        if not coords:
            print('Skipping eligible facility without official coordinates: ' + path)
            return None
        lng, lat = coords.groups()
    return store_record(path, text(heading[1]) if heading else '', fields.get('住所'), lat, lng, fields['株主優待'])


def build_snapshot(listing_html, map_html, detail_fetch=fetch, today=None):
    today = today or datetime.now(ZoneInfo('Asia/Tokyo')).date()
    listing, mapped = parse_listing(listing_html), parse_map(map_html)
    by_path = {}
    for row in mapped.values():
        path = '/brands/' + row['_typeKey'] + '/' + row['basename']
        if path in by_path:
            raise ValueError('Duplicate official path: ' + path)
        by_path[path] = row
    stores = []
    for path, summary in listing.items():
        if '/complexes/' in path or inactive(summary, today):
            continue
        row = by_path.get(path)
        if row is None:
            time.sleep(0.5)
            store = parse_detail(detail_fetch(BASE + path), path, today)
            if store:
                stores.append(store)
            continue
        if str(row.get('hide', '0')) != '0' or row.get('shareholder') not in ELIGIBLE:
            continue
        opening, closing = jp_date(row.get('open')), jp_date(row.get('close'))
        if row.get('openstatus') == '休業中' or (opening and opening > today) or (closing and closing <= today):
            continue
        stores.append(store_record(path, row['title'], row['address'], row['latitude'], row['longitude'], row['shareholder']))
    if len({store['id'] for store in stores}) != len(stores):
        raise ValueError('Duplicate feature stores')
    if not (80 <= len(stores) <= 250) or len(stores) < len(listing) * .6:
        raise ValueError(f'Abnormal eligible count: {len(stores)} of {len(listing)}')
    return {'id':FEATURE_ID, 'checkedOn':today.isoformat(), 'stores':stores}


def write_sql(snapshot, output):
    payload = json.dumps(snapshot, ensure_ascii=False, separators=(',', ':'))
    quote = lambda value: "'" + value.replace("'", "''") + "'"
    sql = 'CREATE TABLE IF NOT EXISTS feature_snapshots (feature_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, checked_on TEXT NOT NULL);\n'
    sql += 'INSERT INTO feature_snapshots (feature_id,payload_json,checked_on) VALUES (' + ','.join(map(quote, [FEATURE_ID, payload, snapshot['checkedOn']])) + ') ON CONFLICT(feature_id) DO UPDATE SET payload_json=excluded.payload_json, checked_on=excluded.checked_on;\n'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(sql, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'cloudflare/generated/sync_balnibarbi_feature.sql')
    parser.add_argument('--previous-count', type=int, default=0)
    args = parser.parse_args()
    snapshot = build_snapshot(fetch(BASE + '/brands/all/'), fetch(BASE + '/brands/map.php'))
    count = len(snapshot['stores'])
    if args.previous_count and count < args.previous_count * .8:
        raise ValueError('Eligible count fell over 20%; keeping previous snapshot')
    write_sql(snapshot, args.output)
    print(f'{FEATURE_ID}: {count} eligible stores, checked {snapshot["checkedOn"]}')


if __name__ == '__main__':
    main()
