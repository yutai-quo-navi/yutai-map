"""Import eligible domestic stores; keep the full working dataset private in D1."""
import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

SITE = 'https://pkg.navitime.co.jp/matsuyafoods'
SEARCH_PAGE = SITE + '/spot/list'
API_BASE = SITE + '/api/proxy2/shop/list'
BENEFIT_URL = 'https://www.matsuyafoods-holdings.co.jp/ir/yutai/'
OPENINGS_URL = 'https://www.matsuyafoods.co.jp/sp/shopsearch/shop_new_close.html'
BASE = Path('data/issuers/matsuya/stores')
CURRENT = BASE / 'current.json'
HISTORY = BASE / 'history.json'
SUMMARY = BASE / 'last_diff.md'
NOW = datetime.now(timezone(timedelta(hours=9)))
RUN_DATE = NOW.strftime('%Y-%m-%d')
GENERATED_AT = NOW.isoformat(timespec='seconds')
SNAPSHOT = BASE / 'snapshots' / f'{RUN_DATE}.json'
DIFF = BASE / 'diffs' / f'{RUN_DATE}.json'
CACHE = Path(os.environ['MATSUYA_SOURCE_DIR']) if os.environ.get('MATSUYA_SOURCE_DIR') else None
ALLOWED = {'0101': '松屋', '0203': '松のや', '0601': 'マイカリー食堂'}


def load_json(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def get(url, fixture):
    if CACHE:
        return (CACHE / fixture).read_text(encoding='utf-8')
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 yutai-map/1.0', 'Accept': 'application/json,text/html'})
            with urllib.request.urlopen(req, timeout=90) as response:
                return response.read(10_000_000).decode('utf-8')
        except (OSError, ValueError):
            if attempt == 2:
                raise
            time.sleep(2 ** (attempt+1))


class Rows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.cells, self.cell, self.codes = [], None, None, []

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.cells, self.codes = [], []
        elif tag in ('td', 'th') and self.cells is not None:
            self.cell = []
        elif tag == 'a' and self.cells is not None:
            href = dict(attrs).get('href', '')
            if '/matsuyafoods/spot/detail?' in href:
                code = urllib.parse.parse_qs(urllib.parse.urlsplit(href).query).get('code', [])
                self.codes.extend(code)

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            self.cells.append(''.join(self.cell).strip())
            self.cell = None
        elif tag == 'tr' and self.cells is not None:
            self.rows.append((self.cells, self.codes))
            self.cells = None


benefit = re.sub(r'\s+', '', unescape(re.sub('<[^>]*>', '', get(BENEFIT_URL, 'benefit.html'))))
for expected in ['松屋、松のや、それらを主業態とする複合店舗', 'ご優待券のご利用は、国内店舗に限ります', '松屋・松のやを主業態とする複合店舗のみ']:
    if expected not in benefit:
        raise RuntimeError('Official benefit eligibility wording changed')
openings_html = get(OPENINGS_URL, 'closures.html')
if '新店・一時閉店一覧' not in openings_html:
    raise RuntimeError('Official openings page changed')
parser = Rows()
parser.feed(openings_html)
future_groups = set()
for cells, codes in parser.rows:
    if not codes or len(cells) != 3:
        continue
    # Temporary closures have a different third column. Only exclude future first openings.
    match = re.fullmatch(r'\s*(\d{1,2})月(\d{1,2})日(\d{1,2})時オープン\s*', cells[2])
    if not match:
        continue
    month, day, hour = map(int, match.groups())
    year = NOW.year + (1 if month < NOW.month-6 else -1 if month > NOW.month+6 else 0)
    opened = datetime(year, month, day, hour, tzinfo=NOW.tzinfo)
    if opened > NOW:
        future_groups.update(int(code) % 10000 for code in codes)
if len(future_groups) > 30:
    raise RuntimeError('Suspicious future opening count')

first = json.loads(get(API_BASE+'?offset=0&limit=200', 'page-0.json'))
universe = int(first['count']['total'])
if not 1800 <= universe <= 2800:
    raise RuntimeError(f'Unexpected official universe: {universe}')
all_rows, seen = [], set()
for offset in range(0, universe, 200):
    if offset:
        time.sleep(.3)
    data = first if offset == 0 else json.loads(get(API_BASE+'?'+urllib.parse.urlencode({'offset': offset, 'limit': 200}), f'page-{offset}.json'))
    if int(data['count']['total']) != universe or int(data['count']['offset']) != offset or len(data['items']) != min(200, universe-offset):
        raise RuntimeError('Incomplete or changing official pagination')
    for row in data['items']:
        code = str(row.get('code', ''))
        if not re.fullmatch(r'\d{10}', code) or code in seen:
            raise RuntimeError('Invalid or duplicate official id')
        seen.add(code)
        all_rows.append(row)


def branch(row):
    name = re.sub(r'^(松屋|松のや|マイカリー食堂)\s*', '', row['name'])
    return re.split('[（(]', name)[0].strip().removesuffix('店')


groups = defaultdict(list)
excluded_counts = Counter()
for row in all_rows:
    cats = [c for c in row.get('categories', []) if c.get('level') == 'middle']
    if len(cats) != 1:
        raise RuntimeError('Official brand classification changed')
    cat = cats[0]['code']
    if cat not in ALLOWED:
        excluded_counts[cats[0]['name']] += 1
        continue
    if not row.get('name') or not row.get('address_name') or row.get('status') != 'normal':
        raise RuntimeError('Eligible store missing official fields or normal status')
    coord = row.get('coord', {})
    if not 20 <= float(coord['lat']) <= 46 or not 122 <= float(coord['lon']) <= 154:
        raise RuntimeError('Invalid domestic coordinates')
    # Attached brands use 10000/20000 offsets. Never merge on this alone:
    # branch name, address district, phone and coordinate proximity are checked below.
    if int(row['code']) >= 30000:
        raise RuntimeError('Official co-location identifier scheme changed')
    groups[int(row['code']) % 10000].append((cat, row))

fresh_by_id, brand_counts = {}, Counter()
for key, entries in groups.items():
    entries.sort(key=lambda entry: int(entry[1]['code']))
    main = [(cat, row) for cat, row in entries if cat in ('0101', '0203')]
    if not main:
        raise RuntimeError('Attached MyCurry without an eligible primary store')
    primary = main[0][1]
    for _, row in entries:
        delta = math.hypot((float(row['coord']['lat'])-float(primary['coord']['lat']))*111320, (float(row['coord']['lon'])-float(primary['coord']['lon']))*111320*math.cos(float(primary['coord']['lat'])*math.pi/180))
        if branch(row) != branch(primary) or row.get('address_code') != primary.get('address_code') or re.sub(r'\D','',row.get('phone','')) != re.sub(r'\D','',primary.get('phone','')) or delta > 100:
            raise RuntimeError(f'Ambiguous attached store: {key}')
    if len({cat for cat, _ in entries}) != len(entries):
        raise RuntimeError('Multiple same-brand stores in one physical group')
    if key in future_groups:
        excluded_counts['開店前（実店舗）'] += 1
        continue
    # Explicit combination labels keep filters honest without counting attached brands twice.
    brand = '・'.join(ALLOWED[cat] for cat in ALLOWED if any(c == cat for c, _ in entries))
    address = primary['address_name']
    pref = re.match(r'(北海道|東京都|大阪府|京都府|.{2,3}県)', address)
    if not pref:
        raise RuntimeError('Unknown domestic prefecture')
    sid = 'official:id:' + primary['code']
    fresh_by_id[sid] = {'store_id': sid, 'official_id': primary['code'], 'brand_name': brand, 'category': 'restaurant', 'name': primary['name'], 'address': address, 'prefecture': pref.group(1), 'postal_code': primary.get('postal_code',''), 'phone': primary.get('phone','').strip(), 'lat': float(primary['coord']['lat']), 'lng': float(primary['coord']['lon']), 'official_url': SITE+'/spot/detail?'+urllib.parse.urlencode({'code': primary['code']}), 'benefit_status': 'official_eligible'}
    brand_counts[brand] += 1
fresh_stores = list(fresh_by_id.values())
official_total = len(fresh_stores)
if not 1200 <= official_total <= 1800 or len(Counter(s['prefecture'] for s in fresh_stores)) < 45 or not {'松屋','松のや'} <= set(brand_counts):
    raise RuntimeError('Suspicious physical store or prefecture coverage')


def comparable(store):
    return {k: v for k, v in store.items() if k not in ['first_seen','last_seen','status','missing_count']}
previous = load_json(CURRENT, {"stores": []})
history = load_json(HISTORY, {"stores": {}})
previous_by_id = {s["store_id"]: s for s in previous.get("stores", [])}

if previous_by_id:
    ratio = len(fresh_stores) / len(previous_by_id)
    if ratio < 0.80 or ratio > 1.50:
        raise RuntimeError(
            f"Store count changed too much: previous={len(previous_by_id)} current={len(fresh_stores)} ratio={ratio:.3f}"
        )

added_ids = sorted(set(fresh_by_id) - set(previous_by_id))
removed_ids = sorted(set(previous_by_id) - set(fresh_by_id))
common_ids = sorted(set(fresh_by_id) & set(previous_by_id))
changed_ids = [
    sid for sid in common_ids
    if comparable(fresh_by_id[sid]) != comparable(previous_by_id[sid])
]

if previous_by_id:
    if len(added_ids)>150 or len(removed_ids)>150 or len(changed_ids)>300:
        raise RuntimeError('Too many added/removed/changed stores; preserving existing D1')
    for field in ['brand_name','prefecture']:
        old=Counter(s.get(field) for s in previous_by_id.values())
        new=Counter(s.get(field) for s in fresh_stores)
        for group,count in old.items():
            if count>=10 and new[group]<count*0.5:
                raise RuntimeError(f'Group coverage dropped too much: {field} {group}')

for sid, store in fresh_by_id.items():
    old_hist = history["stores"].get(sid, {})
    first_seen = old_hist.get("first_seen") or previous_by_id.get(sid, {}).get("first_seen") or RUN_DATE
    store["first_seen"] = first_seen
    store["last_seen"] = RUN_DATE
    store["status"] = "active"
    history["stores"][sid] = {
        "store_id": sid,
        "shop_code": store.get("shop_code"),
        "brand_name": store.get("brand_name"),
        "name": store.get("name"),
        "address": store.get("address"),
        "first_seen": first_seen,
        "last_seen": RUN_DATE,
        "missing_count": 0,
        "status": "active",
    }

for sid in removed_ids:
    prior = previous_by_id[sid]
    old_hist = history["stores"].get(sid, {})
    missing_count = int(old_hist.get("missing_count", 0)) + 1
    history["stores"][sid] = {
        "store_id": sid,
        "shop_code": prior.get("shop_code"),
        "brand_name": prior.get("brand_name"),
        "name": prior.get("name"),
        "address": prior.get("address"),
        "first_seen": old_hist.get("first_seen") or prior.get("first_seen") or RUN_DATE,
        "last_seen": old_hist.get("last_seen") or prior.get("last_seen") or RUN_DATE,
        "missing_count": missing_count,
        "status": "missing_once" if missing_count == 1 else "removed_candidate",
    }

sorted_stores = sorted(
    fresh_stores,
    key=lambda s: (s.get("prefecture", ""), s.get("address", ""), s.get("name", ""))
)

current_obj = {
    "source": SEARCH_PAGE,
    "api_source": API_BASE,
    "eligible_filter": "domestic Matsuya/Matsunoya and attached MyCurry only; co-located official records merged",
    "excluded_counts": dict(excluded_counts),
    "official_eligible_count": official_total,
    "official_store_universe_count": universe,
    "generated_at": GENERATED_AT,
    "eligible_count": len(sorted_stores),
    "brand_counts": dict(sorted(brand_counts.items())),
    "stores": sorted_stores,
}

snapshot_obj = dict(current_obj)
snapshot_obj["snapshot_date"] = RUN_DATE

diff_obj = {
    "source": current_obj["source"],
    "generated_at": GENERATED_AT,
    "run_date": RUN_DATE,
    "previous_generated_at": previous.get("generated_at"),
    "counts": {
        "previous": len(previous_by_id),
        "current": len(fresh_by_id),
        "added": len(added_ids),
        "removed": len(removed_ids),
        "changed": len(changed_ids),
    },
    "added": [fresh_by_id[sid] for sid in added_ids],
    "removed": [previous_by_id[sid] for sid in removed_ids],
    "changed": [
        {"store_id": sid, "before": previous_by_id[sid], "after": fresh_by_id[sid]}
        for sid in changed_ids
    ],
}

history["updated_at"] = GENERATED_AT
history["run_date"] = RUN_DATE

save_json(CURRENT, current_obj)
save_json(SNAPSHOT, snapshot_obj)
save_json(DIFF, diff_obj)
save_json(HISTORY, history)

SUMMARY.parent.mkdir(parents=True, exist_ok=True)
with SUMMARY.open("w", encoding="utf-8") as f:
    f.write(f"# 松屋フーズホールディングス店舗DB 差分 {RUN_DATE}\n\n")
    f.write(f"- 優待対象店舗: {len(fresh_stores)} 店舗\n")
    f.write(f"- 新規: {len(added_ids)}\n")
    f.write(f"- 消失: {len(removed_ids)}\n")
    f.write(f"- 変更: {len(changed_ids)}\n")
    f.write("\n## ブランド別\n")
    for name, count in sorted(brand_counts.items()):
        f.write(f"- {name}: {count}\n")
    if added_ids:
        f.write("\n## 新規\n")
        for sid in added_ids[:200]:
            s = fresh_by_id[sid]
            f.write(f"- {s['brand_name']} / {s['name']} / {s['address']}\n")
    if removed_ids:
        f.write("\n## 消失\n")
        for sid in removed_ids[:200]:
            s = previous_by_id[sid]
            f.write(f"- {s.get('brand_name','')} / {s.get('name','')} / {s.get('address','')}\n")

print(json.dumps({
    "run_date": RUN_DATE,
    "eligible_count": len(fresh_stores),
    "brand_counts": dict(brand_counts),
    "added": len(added_ids),
    "removed": len(removed_ids),
    "changed": len(changed_ids),
}, ensure_ascii=False))
