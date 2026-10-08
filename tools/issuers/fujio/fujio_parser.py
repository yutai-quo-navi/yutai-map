"""Read the complete official directory; the embedded map array is incomplete."""
import json
import math
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'features'))
from scrape_kyoritsu_hotels import Document, PREFECTURES

SEARCH_PAGE = 'https://www.fujiofood.com/shop_search/'
BENEFIT_URL = 'https://www.fujiogroup.com/ir/hospitality.html'
EXCLUDED = ['ドトールコーヒー堺市立総合医療センター店', '東京土山人', '馳走侘助']
AREA_PREF = {p[:-1] if p.endswith(('県', '府', '都')) else p: p for p in PREFECTURES}
AREA_PREF['北海道'] = '北海道'
FOREIGN = {'中国', '台湾', 'インドネシア', 'フィリピン', 'アメリカ', 'タイ', 'ベトナム', 'カナダ'}


def clean(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def norm(value):
    return re.sub(r'[\s・･\-‐−－ー]', '', unicodedata.normalize('NFKC', str(value or '')))


def verify_policy(html):
    text = norm(Document(html).root.text())
    if norm('お食事券は当社グループ全店でご利用いただけます') not in text or any(norm(x) not in text for x in EXCLUDED):
        raise ValueError('Official voucher eligibility changed; preserve previous database')


def parse_directory(html, today):
    map_match = re.search(r'\$json_array\s*=\s*(\[.*?\]);', html, re.S)
    html = re.sub(r'<script\b[^>]*>.*?</script>', '', html, flags=re.S | re.I)
    label = re.search(r'全\s*(\d+)\s*店舗', html)
    starts = list(re.finditer(r'<li\s+class="prefSec-store"\s*>', html))
    if not label or not 0 <= int(label[1]) - len(starts) <= 1:
        raise ValueError('Incomplete official directory')
    if not map_match:
        raise ValueError('Official map data missing')
    maps = {}
    for item in json.loads(map_match[1]):
        url = item.get('link')
        if not isinstance(url, str) or url in maps:
            raise ValueError('Duplicate/invalid official map identity')
        maps[url] = item
    rows, exclusions, seen = [], [], set()
    for start in starts:
        # Parse each card independently: malformed markup must not swallow siblings.
        card = Document('<li>' + html[start.end():].split('</li>', 1)[0] + '</li>').root
        titles = card.find('p', 'ttl')
        detail = card.find('p', 'detailBtn')
        links = detail[0].find('a') if len(detail) == 1 else []
        if len(titles) != 1 or len(links) != 1:
            raise ValueError('Missing official store identity')
        name, url = titles[0].text(), links[0].attrs.get('href', '')
        identity = re.fullmatch(r'https://www\.fujiofood\.com/shop_search/[^/]+/shop_(\d+)\.php', url)
        if not identity or url in seen:
            raise ValueError('Invalid/duplicate store URL: ' + url)
        seen.add(url)
        headings = re.findall(r'<h4 class="prefSec-heading">(.*?)</h4>', html[:start.start()], re.S)
        if not headings:
            raise ValueError('Missing directory area')
        area = clean(headings[-1])
        if area in FOREIGN:
            exclusions.append({'name': name, 'id': identity[1], 'reason': '海外店舗'})
            continue
        if area not in AREA_PREF:
            raise ValueError('Unknown directory area: ' + area)
        text = card.text()
        reason = None
        if any(norm(x) in norm(name) for x in EXCLUDED) or re.search(r'(金券|株主優待|お食事券).*ご利用いただけません', text):
            reason = '優待対象外'
        elif re.search(r'しばらくの間休業|臨時休業とさせて|閉店しました|閉店いたしました|営業終了|休業中', text):
            reason = '休業中・営業終了'
        if reason:
            exclusions.append({'name': name, 'id': identity[1], 'reason': reason})
            continue
        specs = {}
        for tr in card.find('tr'):
            th, td = tr.find('th'), tr.find('td')
            if len(th) == len(td) == 1:
                specs[th[0].text()] = td[0].text()
        address = re.sub(r'^〒\s*\d{3}[-‐－]*\d{4}\s*', '', specs.get('住所', ''))
        pref = AREA_PREF[area]
        if not address.startswith(pref):
            address = pref + address
        if len(address) < len(pref) + 5 or not name:
            raise ValueError('Incomplete store address/name: ' + url)
        raw_title = re.search(r'class="ttl">(.*?)</p>', html[start.end():].split('</li>', 1)[0], re.S)[1]
        if '&emsp;' in raw_title:
            brand = Document(raw_title.split('&emsp;', 1)[0]).root.text()
        else:
            brand = clean(name.split(' ', 1)[0])
            for prefix in ['OG CAFE', 'OIC CAFE', '鳥料理 藤よし', 'すき焼 藤尾',
                           'おきがる 串家物語', '麺乃庄 よろず庵', 'スキヤキ フジオ',
                           'キッチン フジオ軒', '大衆酒場 中津食堂']:
                if name.startswith(prefix):
                    brand = prefix
                    break
        category = 'cafe' if any(x in brand for x in ['ピノキオ', 'デリス', '珈琲', 'CAFE', 'ＣＡＦＥ', 'カフェ']) else 'bakery' if 'ドーナッツ' in brand else 'restaurant'
        row = {'store_id': 'official:id:' + identity[1], 'official_id': identity[1], 'name': name,
               'address': address, 'prefecture': pref, 'phone': specs.get('TEL/FAX', ''),
               'brand_name': brand, 'category': category, 'official_url': url, 'benefit_status': 'official_eligible'}
        mapped = maps.get(url)
        if mapped:
            opening = re.fullmatch(r'(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日', str(mapped.get('open_date', '')))
            if opening and date(*map(int, opening.groups())) > today:
                exclusions.append({'name': name, 'id': identity[1], 'reason': '開店前'})
                continue
            # A relocated store must not inherit coordinates from the old address.
            mapped_address = clean(mapped.get('address'))
            if not mapped_address.startswith(pref):
                mapped_address = pref + mapped_address
            if norm(mapped_address) == norm(address):
                lat, lng = float(mapped['latitude']), float(mapped['longitude'])
                if math.isfinite(lat) and math.isfinite(lng) and 20 <= lat <= 46 and 122 <= lng <= 154:
                    row.update(lat=lat, lng=lng, coordinate_source=SEARCH_PAGE)
        rows.append(row)
    if len(rows) + len(exclusions) != len(starts):
        raise ValueError('Incomplete eligible/excluded accounting')
    gap = int(label[1]) - len(starts)
    if gap:
        # Tokyo Dosanjin remains in the map array without a visible directory card.
        # Count it only as an exclusion when its own official note forbids vouchers.
        absent_excluded = [m for u, m in maps.items() if u not in seen and
                           re.search(r'金券.*ご利用いただけません', str(m.get('notes', '')))]
        if len(absent_excluded) != gap:
            raise ValueError('Unexplained directory count discrepancy')
        exclusions.extend({'name': clean(m.get('name')), 'id': m['link'], 'reason': '優待対象外・一覧未掲載'} for m in absent_excluded)
    return int(label[1]), rows, exclusions
