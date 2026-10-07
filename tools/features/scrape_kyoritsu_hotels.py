#!/usr/bin/env python3
"""Build two hotel-only feature snapshots from Kyoritsu's public directories."""
import argparse
import gzip
import html
import json
import math
import re
import time
from datetime import date, datetime
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
IR = 'https://www.kyoritsugroup.co.jp/ir/stock/benefits/'
RESORT = 'https://dormy-hotels.com/resort/hotels/'
DORMY = 'https://dormy-hotels.com/dormyinn/hotels/list/'
DISCOUNT = 'kyoritsu-hotel-discount'
PLAN = 'kyoritsu-resort-plan'
PREFECTURES = '北海道 青森県 岩手県 宮城県 秋田県 山形県 福島県 茨城県 栃木県 群馬県 埼玉県 千葉県 東京都 神奈川県 新潟県 富山県 石川県 福井県 山梨県 長野県 岐阜県 静岡県 愛知県 三重県 滋賀県 京都府 大阪府 兵庫県 奈良県 和歌山県 鳥取県 島根県 岡山県 広島県 山口県 徳島県 香川県 愛媛県 高知県 福岡県 佐賀県 長崎県 熊本県 大分県 宮崎県 鹿児島県 沖縄県'.split()
PARTNERS = {'www.tenger.jp': 'https://www.tenger.jp/access/',
            'dormy-karuizawa.jp': 'https://www.dormy-karuizawa.jp/access/'}


class Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def find(self, tag=None, cls=None):
        found = []
        for child in self.children:
            if isinstance(child, Node):
                if (tag is None or child.tag == tag) and (cls is None or cls in child.attrs.get('class', '').split()):
                    found.append(child)
                found.extend(child.find(tag, cls))
        return found

    def text(self):
        return re.sub(r'\s+', ' ', ' '.join(c.text() if isinstance(c, Node) else c for c in self.children)).strip()


class Document(HTMLParser):
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self, value):
        super().__init__()
        self.root = Node()
        self.stack = [self.root]
        self.feed(value)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def fetch(url):
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={'User-Agent': 'YutaiMap/1.0 (monthly official hotel directory check)', 'Accept-Language':'ja-JP,ja;q=0.9'}), timeout=30) as response:
                payload = response.read()
                if payload.startswith(b'\x1f\x8b'):
                    payload = gzip.decompress(payload)
                return decode_document(payload)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def decode_document(payload):
    charset = re.search(rb'charset=["\s]*([a-zA-Z0-9_-]+)', payload[:3000], re.I)
    encoding = charset[1].decode('ascii') if charset else 'utf-8-sig'
    return payload.decode(encoding)


def verify_policy(document):
    text = Document(document).root.text()
    required = ['株主様ご優待割引', '株主様リゾートホテルご優待', '現地払い', '事前決済', 'ドーミーイン、御宿 野乃は対象外']
    if not all(term in text for term in required):
        raise ValueError('Official voucher policy changed; retain previous snapshots for review')


def future_opening(summary, today):
    dated = re.search(r'(\d{4})\.(\d{2})\.(\d{2})\s+(?:NEW|RENEWAL)', summary)
    if dated:
        return date(*map(int, dated.groups())) > today
    match = re.search(r'(\d{4})年\s*(\d{1,2})月(?:\s*(\d{1,2})日)?\s*オープン', summary)
    if not match:
        return False
    year, month, day = match.groups()
    # A month-only future opening is not listed until the following month.
    return (int(year), int(month), int(day or 32)) > (today.year, today.month, today.day)


def parse_resorts(document, today):
    stores = []
    for item in Document(document).root.find('li'):
        names, addresses = item.find(cls='name'), item.find('address')
        if not names or not addresses:
            continue
        links = [a.attrs.get('href', '') for a in item.find('a') if a.text() == '施設サイト']
        if not links:
            continue  # Announced hotels without an operating facility page.
        if len(links) != 1:
            raise ValueError('Ambiguous resort facility link')
        url = links[0]
        host = urlparse(url).hostname
        partner = 'partner' in item.attrs.get('class', '').split()
        if partner and host not in PARTNERS:
            raise ValueError('New partner needs voucher eligibility verification: ' + url)
        if not partner and (host != 'dormy-hotels.com' or not urlparse(url).path.startswith('/resort/hotels/')):
            raise ValueError('Unexpected resort facility URL')
        summary = item.text()
        if future_opening(summary, today) or re.search(r'休業中|閉館|営業終了', summary):
            continue
        stores.append({'id': 'partner-' + host if partner else 'resort-' + urlparse(url).path.strip('/').split('/')[-1],
                       'name': names[0].text(), 'address': addresses[0].text(),
                       'sourceUrl': url, 'coordinateUrl': PARTNERS[host] if partner else url.rstrip('/') + '/access/',
                       'hotelGroup': '提携ホテル' if partner else '共立リゾート', 'resortPlan': not partner})
    if not stores or len({s['id'] for s in stores}) != len(stores):
        raise ValueError('Missing or duplicate resort hotels')
    return stores


def parse_dormy(document, today):
    marker = 'var jsonData = '
    if marker not in document:
        raise ValueError('Official Dormy directory structure changed')
    rows, _ = json.JSONDecoder().raw_decode(document.split(marker, 1)[1].lstrip())
    cards = {}
    for item in Document(document).root.find('li'):
        for link in item.find('a'):
            path = urlparse(link.attrs.get('href', '')).path
            if re.fullmatch(r'/dormyinn/hotels/[a-z0-9_-]+/?', path):
                cards[path.strip('/').split('/')[-1]] = item.text()
    stores = []
    for row in rows:
        state = row.get('r.state')
        if state is None:  # Overseas hotels are outside this domestic feature.
            continue
        if not isinstance(state, int) or not 1 <= state <= 47:
            raise ValueError('Unexpected hotel prefecture')
        alias = row.get('r.url_alias', '')
        if not re.fullmatch('[a-z0-9_-]+', alias) or alias not in cards:
            raise ValueError('Hotel record missing from official listing: ' + alias)
        if future_opening(cards[alias], today) or re.search(r'休業中|閉館|営業終了', cards[alias]):
            continue
        address = row.get('r.address', '')
        if not address.startswith(PREFECTURES[state - 1]):
            address = PREFECTURES[state - 1] + address
        name = row.get('r.hotel_name', '')
        if not name or not row.get('r.address'):
            raise ValueError('Missing Dormy name/address')
        url = 'https://dormy-hotels.com/dormyinn/hotels/' + alias + '/'
        stores.append({'id': 'dormy-' + alias, 'name': name, 'address': address,
                       'sourceUrl': url, 'coordinateUrl': url,
                       'hotelGroup': '御宿 野乃' if '野乃' in name else 'ドーミーイン', 'resortPlan': False})
    if not stores or len({s['id'] for s in stores}) != len(stores):
        raise ValueError('Missing or duplicate Dormy hotels')
    return stores


def parse_coordinates(document):
    for frame in Document(document).root.find('iframe'):
        src = html.unescape(frame.attrs.get('src') or frame.attrs.get('data-src') or '')
        if urlparse(src).hostname not in {'www.google.com', 'maps.google.com'}:
            continue
        match = re.search(r'!3d(-?[\d.]+)!4d(-?[\d.]+)', src)
        note = ''
        if match:
            lat, lng = map(float, match.groups())
        else:
            match = re.search(r'!2d(-?[\d.]+)!3d(-?[\d.]+)', src)
            if not match:
                continue
            lng, lat = map(float, match.groups())
            note = '距離は公式アクセス地図の中心位置を使った目安です。'
        if not (math.isfinite(lat) and math.isfinite(lng) and 20 <= lat <= 46 and 122 <= lng <= 154):
            raise ValueError('Invalid domestic hotel coordinates')
        return {'lat': lat, 'lng': lng, 'coordinateSource': '公式アクセス地図', 'coordinateNote': note}
    raise ValueError('Hotel has no verified official map coordinates')


def hotel_coordinates(hotel, detail_fetch=fetch, supplements=None):
    row = (supplements or {}).get(hotel['id'])
    matched = bool(row and row['name'] == hotel['name'] and row['address'] == hotel['address'])
    def supplement():
        lat, lng = row['lat'], row['lng']
        if not (math.isfinite(lat) and math.isfinite(lng) and 20 <= lat <= 46 and 122 <= lng <= 154):
            raise ValueError('Invalid supplemental coordinates')
        return {k: v for k, v in row.items() if k not in {'name', 'address', 'preferSupplement'}}
    # Some official embeds share a viewport across different hotels. Explicit,
    # reviewed name/address matches can override those imprecise map centers.
    if matched and row.get('preferSupplement'):
        return supplement()
    try:
        document = detail_fetch(hotel['coordinateUrl'])
    except HTTPError as error:
        if error.code != 404:
            raise
        document = ''
    try:
        return parse_coordinates(document)
    except ValueError:
        if hotel['coordinateUrl'] != hotel['sourceUrl']:
            document = detail_fetch(hotel['sourceUrl'])
            try:
                return parse_coordinates(document)
            except ValueError:
                pass
        # Manually verified OpenPOI supplements are valid only for this exact
        # official name/address, so a move or renamed hotel requires review.
        if matched:
            return supplement()
        raise ValueError('Unverified hotel coordinates: ' + hotel['id'])


def build_snapshots(ir_html, resort_html, dormy_html, detail_fetch=fetch, today=None, supplements=None):
    today = today or datetime.now(ZoneInfo('Asia/Tokyo')).date()
    verify_policy(ir_html)
    hotels = parse_resorts(resort_html, today) + parse_dormy(dormy_html, today)
    def verify(hotel):
        time.sleep(.35)
        hotel.update(hotel_coordinates(hotel, detail_fetch, supplements))
        hotel['verified'] = True
        hotel.setdefault('coordinateCheckedOn', today.isoformat())
        return hotel
    # At most two simultaneous reads, with a short interval per request.
    with ThreadPoolExecutor(max_workers=2) as pool:
        hotels = list(pool.map(verify, hotels))
    print(f'Verified {len(hotels)} hotel locations', flush=True)
    discount, plans = [], []
    for hotel in hotels:
        store = {k: v for k, v in hotel.items() if k not in {'coordinateUrl', 'resortPlan'}}
        discount.append({**store, 'conditions': '株主様ご優待割引電子チケット：宿泊代の割引に利用できます。予約時に現地払い・現地決済を選択してください。事前決済の宿泊代には利用できません。'})
        if hotel['resortPlan']:
            plans.append({**store, 'conditions': '株主様リゾートホテルご優待電子チケット：専用サイトまたは株主様専用電話から優待プランの事前予約が必要です。１枚につき１泊・大人10名まで。空室・料金・利用条件は公式予約窓口でご確認ください。'})
    if not (120 <= len(discount) <= 250 and 30 <= len(plans) <= 100):
        raise ValueError(f'Abnormal hotel counts: discount={len(discount)}, plans={len(plans)}')
    return [{'id': DISCOUNT, 'checkedOn': today.isoformat(), 'stores': discount},
            {'id': PLAN, 'checkedOn': today.isoformat(), 'stores': plans}]


def validate_previous(snapshots, previous):
    counts = {s['id']: len(s['stores']) for s in snapshots}
    for feature_id, old_count in previous.items():
        if old_count and counts[feature_id] < old_count * .8:
            raise ValueError('Hotel count fell over 20%; keeping previous snapshots')


def write_sql(snapshots, output, batch_id="kyoritsu-hotels"):
    if not re.fullmatch(r"[a-z0-9-]+", batch_id):
        raise ValueError("Invalid feature staging batch")
    quote = lambda value: "'" + value.replace("'", "''") + "'"
    statements = [
        'CREATE TABLE IF NOT EXISTS feature_snapshots (feature_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, checked_on TEXT NOT NULL);',
        'CREATE TABLE IF NOT EXISTS feature_snapshot_staging (batch_id TEXT NOT NULL, feature_id TEXT NOT NULL, checked_on TEXT NOT NULL, store_order INTEGER NOT NULL, store_json TEXT NOT NULL, PRIMARY KEY(batch_id,feature_id,store_order));',
        f"DELETE FROM feature_snapshot_staging WHERE batch_id='{batch_id}';"
    ]
    # D1 limits each SQL statement to 100 KB. Stage small rows, then publish
    # both completed datasets in one short statement so readers never see half.
    prefix = 'INSERT INTO feature_snapshot_staging (batch_id,feature_id,checked_on,store_order,store_json) VALUES '
    values = []
    for snapshot in snapshots:
        for i, store in enumerate(snapshot['stores']):
            payload = json.dumps(store, ensure_ascii=False, separators=(',', ':'))
            row = '(' + ','.join([quote(batch_id), quote(snapshot['id']), quote(snapshot['checkedOn']), str(i), quote(payload)]) + ')'
            if len((prefix + ','.join(values + [row])).encode('utf-8')) > 60_000:
                statements.append(prefix + ','.join(values) + ';')
                values = []
            values.append(row)
    if values:
        statements.append(prefix + ','.join(values) + ';')
    statements.append(f"INSERT INTO feature_snapshots (feature_id,payload_json,checked_on) SELECT feature_id,json_object('id',feature_id,'checkedOn',checked_on,'stores',json_group_array(json(store_json))),checked_on FROM (SELECT * FROM feature_snapshot_staging WHERE batch_id='{batch_id}' ORDER BY feature_id,store_order) GROUP BY feature_id,checked_on ON CONFLICT(feature_id) DO UPDATE SET payload_json=excluded.payload_json,checked_on=excluded.checked_on;")
    statements.append(f"DELETE FROM feature_snapshot_staging WHERE batch_id='{batch_id}';")
    if any(len(statement.encode('utf-8')) >= 100_000 for statement in statements):
        raise ValueError('Hotel SQL exceeds D1 statement limit')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('\n'.join(statements) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'cloudflare/generated/sync_kyoritsu_hotels.sql')
    parser.add_argument('--previous-counts', type=Path)
    args = parser.parse_args()
    supplements = json.loads((ROOT / 'data/features/kyoritsu-hotel-coordinates.json').read_text())
    snapshots = build_snapshots(fetch(IR), fetch(RESORT), fetch(DORMY), supplements=supplements)
    if args.previous_counts:
        groups = json.loads(args.previous_counts.read_text())
        previous = {r['feature_id']: r['count'] for group in groups for r in group.get('results', [])}
        validate_previous(snapshots, previous)
    write_sql(snapshots, args.output)
    for snapshot in snapshots:
        print(f'{snapshot["id"]}: {len(snapshot["stores"])} hotels, checked {snapshot["checkedOn"]}')


if __name__ == '__main__':
    main()
