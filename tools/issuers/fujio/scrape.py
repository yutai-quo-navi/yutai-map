"""Collect official eligible Fujio stores into the private D1 working snapshot."""
import json
import os
import re
import time
import urllib.request
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from fujio_parser import parse_directory, verify_policy, SEARCH_PAGE, BENEFIT_URL

BASE = Path('data/issuers/fujio/stores')
CURRENT = BASE / 'current.json'
HISTORY = BASE / 'history.json'
SUMMARY = BASE / 'last_diff.md'
NOW = datetime.now(timezone(timedelta(hours=9)))
RUN_DATE = NOW.strftime('%Y-%m-%d')
GENERATED_AT = NOW.isoformat(timespec='seconds')
SNAPSHOT = BASE / 'snapshots' / f'{RUN_DATE}.json'
DIFF = BASE / 'diffs' / f'{RUN_DATE}.json'


def load_json(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def get(url, fixture):
    folder = os.environ.get('FUJIO_SOURCE_DIR')
    if folder:
        return (Path(folder) / fixture).read_text(encoding='utf-8')
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 yutai-map/1.0', 'Accept': 'text/html'})
            with urllib.request.urlopen(req, timeout=60) as response:
                return response.read(10_000_000).decode('utf-8')
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2 ** (attempt+1))


verify_policy(get(BENEFIT_URL, 'benefit.html'))
universe, fresh_stores, exclusions = parse_directory(get(SEARCH_PAGE, 'directory.html'), NOW.date())
if not 500 <= len(fresh_stores) <= 1000:
    raise ValueError('Unexpected eligible store count')
if sum('lat' in row for row in fresh_stores) < 400:
    raise ValueError('Official coordinate coverage dropped too much')
fresh_by_id = {s['store_id']: s for s in fresh_stores}
if len(fresh_by_id) != len(fresh_stores):
    raise ValueError('Duplicate store IDs')
official_total = len(fresh_stores)
brand_counts = Counter(s['brand_name'] for s in fresh_stores)
excluded_counts = Counter(e['reason'] for e in exclusions)
API_BASE = SEARCH_PAGE
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
    if len(added_ids)>90 or len(removed_ids)>90 or len(changed_ids)>180:
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
    "eligible_filter": "Official Fujio directory; domestic eligible stores; closed stores excluded; map coordinates validated against current address",
    "excluded_counts": dict(excluded_counts),
    "official_eligible_count": official_total,
    "official_store_universe_count": universe,
    "generated_at": GENERATED_AT,
    "eligible_count": len(sorted_stores),
    "coordinate_count": sum("lat" in s for s in fresh_stores),
    "reference_count": sum("lat" not in s for s in fresh_stores),
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
    f.write(f"# フジオフード店舗DB 差分 {RUN_DATE}\n\n")
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
