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

SITE = 'https://pkg.navitime.co.jp/royal-gr'
SEARCH_PAGE = SITE + '/spot/list'
API_BASE = SITE + '/api/proxy2/shop/list'
BASE = SITE + '/api/proxy2/shop/list'
BENEFIT_URL = 'https://www.royal-gr-holdings.co.jp/ir/yutai/'
OPENINGS_URL = 'https://www.royal-gr.co.jp/sp/shopsearch/shop_new_close.html'
BASE = Path('data/issuers/royal/stores')
CURRENT = BASE / 'current.json'
HISTORY = BASE / 'history.json'
SUMMARY = BASE / 'last_diff.md'
NOW = datetime.now(timezone(timedelta(hours=9)))
RUN_DATE = NOW.strftime('%Y-%m-%d')
GENERATED_AT = NOW.isoformat(timespec='seconds')
SNAPSHOT = BASE / 'snapshots' / f'{RUN_DATE}.json'
DIFF = BASE / 'diffs' / f'{RUN_DATE}.json'
CACHE = Path(os.environ['ROYAL_SOURCE_DIR']) if os.environ.get('ROYAL_SOURCE_DIR') else None



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


first = json.loads(get(API_BASE+'?offset=0&limit=200&c_d3=1&add=detail', 'page-0.json'))
universe = int(first['count']['total'])
if not 400 <= universe <= 800:
    raise RuntimeError(f'Unexpected eligible count: {universe}')
fresh_by_id, brand_counts = {}, Counter()
excluded_counts = Counter()
for offset in range(0, universe, 200):
    if offset:
        time.sleep(.5)
    params = urllib.parse.urlencode({'offset': offset, 'limit': 200, 'c_d3': 1, 'add': 'detail'})
    data = first if offset == 0 else json.loads(get(API_BASE+'?'+params, f'page-{offset}.json'))
    if int(data['count']['total']) != universe or int(data['count']['offset']) != offset or len(data['items']) != min(200, universe-offset):
        raise RuntimeError('Incomplete or changing pagination')
    for row in data['items']:
        flags = [f for d in row.get('details', []) for f in d.get('flags', []) if f.get('code') == '00003']
        if len(flags) != 1 or flags[0].get('value') is not True:
            raise RuntimeError('Official benefit filter or eligibility flag changed')
        for key in ('from_date', 'to_date'):
            if row.get(key):
                boundary = datetime.fromisoformat(row[key])
                if (key == 'from_date' and boundary > NOW) or (key == 'to_date' and boundary <= NOW):
                    excluded_counts['開店前・掲載終了'] += 1
                    break
        else:
            boundary = None
        if boundary is not None:
            continue
        code = str(row.get('code', ''))
        sid = 'official:id:' + code
        if not re.fullmatch(r'\d{10}', code) or sid in fresh_by_id:
            raise RuntimeError('Invalid or duplicate official id')
        if row.get('status') != 'normal' or not row.get('name') or not row.get('address_name'):
            raise RuntimeError('Invalid eligible store fields')
        lat, lng = float(row['coord']['lat']), float(row['coord']['lon'])
        if not 20 <= lat <= 46 or not 122 <= lng <= 154:
            raise RuntimeError('Invalid domestic coordinates')
        cats = [c for c in row.get('categories', []) if c.get('level') == 'large']
        if len(cats) != 1:
            raise RuntimeError('Official category structure changed')
        brand = cats[0]['name']
        if brand == 'ロイヤルホスト' and not row['name'].startswith('ロイヤルホスト'):
            brand = 'ロイヤルグループ専門店'
        category = 'other' if brand == 'リッチモンドホテル' else 'cafe' if brand in ('ロイヤルガーデンカフェ','スタンダードコーヒー','カフェクロワッサン') else 'bakery' if brand == 'ミセスエリザベスマフィン' else 'restaurant'
        address = row['address_name'].strip()
        pref = re.match(r'(北海道|東京都|大阪府|京都府|.{2,3}県)', address)
        prefectures = '北海道 青森県 岩手県 宮城県 秋田県 山形県 福島県 茨城県 栃木県 群馬県 埼玉県 千葉県 東京都 神奈川県 新潟県 富山県 石川県 福井県 山梨県 長野県 岐阜県 静岡県 愛知県 三重県 滋賀県 京都府 大阪府 兵庫県 奈良県 和歌山県 鳥取県 島根県 岡山県 広島県 山口県 徳島県 香川県 愛媛県 高知県 福岡県 佐賀県 長崎県 熊本県 大分県 宮崎県 鹿児島県 沖縄県'.split()
        pref_code = int(row['address_code'][:2])
        if not 1 <= pref_code <= 47:
            raise RuntimeError('Invalid prefecture code')
        prefecture = prefectures[pref_code-1]
        if pref and pref.group(1) != prefecture:
            raise RuntimeError('Address and prefecture code disagree')
        if not pref:
            address = prefecture + address
        fresh_by_id[sid] = {'store_id': sid, 'official_id': code, 'brand_name': brand, 'category': category, 'name': row['name'], 'address': address, 'prefecture': prefecture, 'postal_code': row.get('postal_code',''), 'phone': row.get('phone',''), 'lat': lat, 'lng': lng, 'official_url': SITE+'/spot/detail?'+urllib.parse.urlencode({'code':code}), 'benefit_status':'official_eligible'}
        brand_counts[brand] += 1
fresh_stores = list(fresh_by_id.values())
official_total = len(fresh_stores)
if official_total + sum(excluded_counts.values()) != universe or not {'ロイヤルホスト','てんや'} <= set(brand_counts):
    raise RuntimeError('Incomplete brand coverage')


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
    "eligible_filter": "official shareholder benefit flag 00003=true; domestic eligible locations",
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
    f.write(f"# ロイヤルホールディングス店舗DB 差分 {RUN_DATE}\n\n")
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
