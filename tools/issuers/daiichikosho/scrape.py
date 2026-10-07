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

SITE = 'https://dkdining.com'
SEARCH_PAGE = SITE + '/search/index.html'
BENEFIT_URL = 'https://www.dkkaraoke.co.jp/stockinfo/shareholdercoupon.html'
BASE = Path('data/issuers/daiichikosho/stores')
CURRENT = BASE / 'current.json'
HISTORY = BASE / 'history.json'
SUMMARY = BASE / 'last_diff.md'
NOW = datetime.now(timezone(timedelta(hours=9)))
RUN_DATE = NOW.strftime('%Y-%m-%d')
GENERATED_AT = NOW.isoformat(timespec='seconds')
SNAPSHOT = BASE / 'snapshots' / f'{RUN_DATE}.json'
DIFF = BASE / 'diffs' / f'{RUN_DATE}.json'
CACHE = Path(os.environ['DK_SOURCE_DIR']) if os.environ.get('DK_SOURCE_DIR') else None



def load_json(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def get(url, fixture):
    if CACHE:
        return (CACHE / fixture).read_text(encoding='utf-8')
    if os.environ.get('DK_CAPTURE_DIR'):
        saved=Path(os.environ['DK_CAPTURE_DIR'])/fixture
        if saved.exists():return saved.read_text()
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 yutai-map/1.0', 'Accept': 'application/json,text/html'})
            with urllib.request.urlopen(req, timeout=90) as response:
                document=response.read(10_000_000).decode('utf-8')
                if os.environ.get('DK_CAPTURE_DIR'):
                    folder=Path(os.environ['DK_CAPTURE_DIR']);folder.mkdir(parents=True,exist_ok=True);(folder/fixture).write_text(document)
                return document
        except (OSError, ValueError):
            if attempt == 2:
                raise
            time.sleep(2 ** (attempt+1))


import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'features'))
from scrape_kyoritsu_hotels import Document, future_opening, PREFECTURES


def search_url(page):
    return SEARCH_PAGE+'?'+urllib.parse.urlencode({'searchBtn2':'以上の条件で検索する','page_id':page})


from store_parser import parse_page


policy=get(BENEFIT_URL,'benefit.html')
policy_text=Document(policy).root.text()
if not all(x in policy_text for x in ['当社グループが運営する','楽蔵','ウメ子の家','じぶんどき','飲食店舗']) or 'https://dkdining.com/' not in policy:
    raise ValueError('Dining voucher eligibility changed; preserve previous dataset')
first_page=get(search_url(1),'page-1.html')
universe,first_stores,exclusions=parse_page(first_page,1,NOW.date())
fresh_by_id={s['store_id']:s for s in first_stores}
for page in range(2,math.ceil(universe/20)+1):
    time.sleep(.5)
    count,rows,excluded=parse_page(get(search_url(page),f'page-{page}.html'),page,NOW.date())
    if count!=universe:raise ValueError('Store universe changed during pagination')
    exclusions.extend(excluded)
    for row in rows:
        if row['store_id'] in fresh_by_id:raise ValueError('Duplicate paginated store')
        fresh_by_id[row['store_id']]=row
if len(fresh_by_id)+len(exclusions)!=universe:raise ValueError('Incomplete official directory coverage')
fresh_stores=list(fresh_by_id.values());official_total=len(fresh_stores)
brand_counts=Counter(s['brand_name'] for s in fresh_stores)
excluded_counts=Counter(e['reason'] for e in exclusions)
API_BASE=SEARCH_PAGE
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
    if len(added_ids)>60 or len(removed_ids)>40 or len(changed_ids)>100:
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
    "eligible_filter": "Official DK dining directory; all pages and map identities verified; future openings excluded",
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
    f.write(f"# 第一興商店舗DB 差分 {RUN_DATE}\n\n")
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
