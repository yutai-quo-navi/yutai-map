import json
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

API_BASE = "https://shop.monogatari.co.jp/api/v1"
BRANDS_PATH = Path("data/issuers/monogatari/brands.json")
BASE = Path("data/issuers/monogatari/stores")
CURRENT = BASE / "current.json"
HISTORY = BASE / "history.json"
SUMMARY = BASE / "last_diff.md"

JST = timezone(timedelta(hours=9))
NOW = datetime.now(JST)
RUN_DATE = NOW.strftime("%Y-%m-%d")
GENERATED_AT = NOW.isoformat(timespec="seconds")
SNAPSHOT = BASE / "snapshots" / f"{RUN_DATE}.json"
DIFF = BASE / "diffs" / f"{RUN_DATE}.json"

def load_json(path, default):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as f:
        return json.load(f)

def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")

def api_get(path, params):
    query = urllib.parse.urlencode(params, doseq=True)
    url = f"{API_BASE}{path}?{query}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 yutai-map-alpha/1.0 (+https://github.com/yutai-quo-navi/yutai-map)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def fetch_brand(brand):
    page = 1
    rows = []
    while True:
        payload = api_get("/shops/", [
            ("brandId[]", brand["api_code"]),
            ("page", page),
            ("perPage", 1000),
        ])
        data = payload.get("data") or []
        for item in data:
            if item.get("not_public_flag"):
                continue
            lat = item.get("latitude")
            lng = item.get("longitude")
            rows.append({
                "store_id": f"official:id:{item.get('id')}",
                "official_id": item.get("id"),
                "shop_code": item.get("shop_code"),
                "brand_code": brand["api_code"],
                "brand_name": brand["name"],
                "category": brand.get("category", "restaurant"),
                "name": item.get("name") or "",
                "address": item.get("address") or "",
                "prefecture": item.get("administrative_area") or "",
                "postal_code": item.get("postal_code") or "",
                "phone": item.get("telephone_number") or "",
                "lat": lat,
                "lng": lng,
                "google_map_link": item.get("google_map_link") or "",
            })
        last_page = int(payload.get("last_page") or 1)
        if page >= last_page:
            break
        page += 1
    return rows

def comparable(store):
    return {
        "shop_code": store.get("shop_code"),
        "brand_code": store.get("brand_code"),
        "brand_name": store.get("brand_name"),
        "category": store.get("category"),
        "name": store.get("name"),
        "address": store.get("address"),
        "prefecture": store.get("prefecture"),
        "postal_code": store.get("postal_code"),
        "phone": store.get("phone"),
        "lat": store.get("lat"),
        "lng": store.get("lng"),
    }

brands_obj = load_json(BRANDS_PATH, {"brands": []})
brands = brands_obj.get("brands") or []
if not brands:
    raise RuntimeError("brands.json is empty")

fresh_by_id = {}
brand_counts = Counter()

for brand in brands:
    if not brand.get("api_code"):
        raise RuntimeError(f"Missing api_code: {brand}")
    rows = fetch_brand(brand)
    brand_counts[brand["name"]] += len(rows)
    for row in rows:
        sid = row["store_id"]
        # 公式IDを主キーにする。万一複数ブランドに出た場合は最初の公式結果を保持。
        fresh_by_id.setdefault(sid, row)

fresh_stores = list(fresh_by_id.values())
if len(fresh_stores) < 500:
    raise RuntimeError(f"Suspiciously small store count: {len(fresh_stores)}")
missing_name = sum(1 for s in fresh_stores if not s.get("name"))
missing_address = sum(1 for s in fresh_stores if not s.get("address"))
missing_coords = sum(1 for s in fresh_stores if s.get("lat") in (None, "") or s.get("lng") in (None, ""))
if missing_name:
    raise RuntimeError(f"Parsed stores without names: {missing_name}")
if missing_address > max(10, int(len(fresh_stores) * 0.05)):
    raise RuntimeError(
        f"Too many parsed stores without addresses: {missing_address}/{len(fresh_stores)}"
    )
if missing_coords > max(10, int(len(fresh_stores) * 0.05)):
    raise RuntimeError(
        f"Too many parsed stores without coordinates: {missing_coords}/{len(fresh_stores)}"
    )

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
    "source": "https://www.monogatari.co.jp/brand/search/",
    "api_source": API_BASE,
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
    f.write(f"# 物語コーポレーション店舗DB 差分 {RUN_DATE}\n\n")
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
