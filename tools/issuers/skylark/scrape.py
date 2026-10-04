import json
import re
import urllib.request
from collections import Counter
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

BASE_URL = "https://store-info.skylark.co.jp"
SOURCE_URL = BASE_URL + "/"
GEOHASH_PREFIXES = ("w", "x", "y")

BASE = Path("data/issuers/skylark/stores")
CURRENT = BASE / "current.json"
HISTORY = BASE / "history.json"
SUMMARY = BASE / "last_diff.md"
BRANDS = Path("data/issuers/skylark/brands.json")
EXCLUSIONS = Path("data/issuers/skylark/exclusions.json")

JST = timezone(timedelta(hours=9))
NOW = datetime.now(JST)
RUN_DATE = NOW.strftime("%Y-%m-%d")
TODAY = NOW.date()
GENERATED_AT = NOW.isoformat(timespec="seconds")
SNAPSHOT = BASE / "snapshots" / f"{RUN_DATE}.json"
DIFF = BASE / "diffs" / f"{RUN_DATE}.json"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36 "
    "yutai-map-alpha/1.0"
)

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

def fetch_text(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept-Language": "ja,en-US;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read().decode("utf-8", "replace")

def fetch_json(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/json",
            "Referer": SOURCE_URL,
        },
    )
    with urllib.request.urlopen(req, timeout=240) as r:
        payload = r.read()
    return json.loads(payload.decode("utf-8", "replace"))

def extract_storelocator_config(html):
    marker = "const storelocator = "
    pos = html.find(marker)
    if pos < 0:
        raise RuntimeError("Official storelocator config marker was not found")
    raw = html[pos + len(marker):].lstrip()
    obj, _ = json.JSONDecoder().raw_decode(raw)
    if not isinstance(obj, dict):
        raise RuntimeError("Official storelocator config is not an object")
    return obj

def category_condition(marker):
    for cond in marker.get("conditions") or []:
        if (
            cond.get("key") == "カテゴリ"
            and cond.get("comparison") == "="
            and cond.get("value")
        ):
            return str(cond["value"])
    return None

def flatten_brand_markers(config):
    by_category = {}
    for group in config.get("markers") or []:
        for marker in group.get("data") or []:
            code = category_condition(marker)
            if not code:
                continue
            extra = marker.get("extra_fields") or {}
            by_category[code] = {
                "code": code,
                "name": marker.get("name") or code,
                "eligible": extra.get("is_yutaiken") is True,
                "page_key": extra.get("page_key") or "",
                "top_url": extra.get("top_url") or "",
            }
    return by_category

def parse_official_date(value):
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y.%m.%d", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise RuntimeError(f"Unexpected official date format: {text!r}")

def is_current_store(item):
    extra = item.get("extra_fields") or {}
    opened = parse_official_date(extra.get("開店日データ"))
    closed = parse_official_date(extra.get("閉店日データ"))
    if opened and opened > TODAY:
        return False
    if closed and closed < TODAY:
        return False
    if item.get("is_active") is False:
        return False
    return True

def is_upcoming_store(item):
    extra = item.get("extra_fields") or {}
    opened = parse_official_date(extra.get("開店日データ"))
    return bool(opened and opened > TODAY)

def category_for_brand(name):
    return "cafe" if "珈琲" in str(name or "") or "カフェ" in str(name or "") else "restaurant"

def official_store_url(brand, item):
    key = str(item.get("key") or "").strip()
    page_key = str(brand.get("page_key") or "").strip()
    if key and page_key:
        return f"{BASE_URL}/{page_key}/map/{key}/"
    return SOURCE_URL

def comparable(store):
    return {
        "store_code": store.get("store_code"),
        "brand_code": store.get("brand_code"),
        "brand_name": store.get("brand_name"),
        "category": store.get("category"),
        "name": store.get("name"),
        "address": store.get("address"),
        "prefecture": store.get("prefecture"),
        "phone": store.get("phone"),
        "lat": store.get("lat"),
        "lng": store.get("lng"),
        "open_date": store.get("open_date"),
        "close_date": store.get("close_date"),
    }

html = fetch_text(SOURCE_URL)
config = extract_storelocator_config(html)
brand_by_category = flatten_brand_markers(config)

if len(brand_by_category) < 30:
    raise RuntimeError(f"Suspiciously small official brand marker count: {len(brand_by_category)}")

eligible_brand_codes = {
    code for code, brand in brand_by_category.items() if brand["eligible"]
}
if len(eligible_brand_codes) < 30:
    raise RuntimeError(
        f"Suspiciously small shareholder-benefit brand count: {len(eligible_brand_codes)}"
    )

raw_by_id = {}
prefix_counts = {}
for prefix in GEOHASH_PREFIXES:
    payload = fetch_json(f"{BASE_URL}/api/point/{prefix}/")
    items = payload.get("items") or []
    prefix_counts[prefix] = len(items)
    for item in items:
        official_id = item.get("id")
        if official_id is None:
            raise RuntimeError(f"Official point without id in prefix {prefix}")
        raw_by_id[str(official_id)] = item

# The list endpoint contains richer opening/closing fields for new and scheduled stores.
# Overlay those fields onto the geohash dataset so a future opening is not shown as usable yet.
list_payload = fetch_json(f"{BASE_URL}/api/point/")
schedule_by_id = {
    str(item.get("id")): item
    for item in (list_payload.get("items") or [])
    if item.get("id") is not None
}
for sid, richer in schedule_by_id.items():
    base = raw_by_id.get(sid)
    if not base:
        continue
    base_extra = base.setdefault("extra_fields", {})
    richer_extra = richer.get("extra_fields") or {}
    for key in ("開店日データ", "閉店日データ"):
        if richer_extra.get(key):
            base_extra[key] = richer_extra[key]

if prefix_counts.get("w", 0) < 200 or prefix_counts.get("x", 0) < 2000:
    raise RuntimeError(f"Suspicious geohash coverage: {prefix_counts}")
if len(raw_by_id) < 2800:
    raise RuntimeError(f"Suspiciously small official store universe: {len(raw_by_id)}")

unknown_categories = Counter()
eligible_all = []
current_stores = []
upcoming_stores = []
brand_counts = Counter()

for item in raw_by_id.values():
    extra = item.get("extra_fields") or {}
    brand_code = str(extra.get("カテゴリ") or "")
    brand = brand_by_category.get(brand_code)
    if not brand:
        unknown_categories[brand_code or "(blank)"] += 1
        continue
    if not brand["eligible"]:
        continue

    lat = item.get("latitude")
    lng = item.get("longitude")
    name = str(item.get("name") or "").strip()
    address = str(item.get("address") or "").strip()
    store_code = str(item.get("key") or "").strip()

    row = {
        "store_id": f"official:id:{item.get('id')}",
        "official_id": item.get("id"),
        "store_code": store_code,
        "brand_code": brand_code,
        "brand_name": brand["name"],
        "category": category_for_brand(brand["name"]),
        "name": name,
        "address": address,
        "prefecture": str(extra.get("都道府県名") or "").strip(),
        "city": str(extra.get("市区町村名") or "").strip(),
        "phone": str(extra.get("電話番号") or "").strip(),
        "lat": lat,
        "lng": lng,
        "open_date": str(extra.get("開店日データ") or "").strip(),
        "close_date": str(extra.get("閉店日データ") or "").strip(),
        "official_url": official_store_url(brand, item),
    }
    eligible_all.append(row)

    if is_upcoming_store(item):
        upcoming_stores.append(row)
        continue
    if not is_current_store(item):
        continue

    current_stores.append(row)
    brand_counts[brand["name"]] += 1

if unknown_categories:
    raise RuntimeError(
        "Official stores contain categories absent from the official marker master: "
        + json.dumps(dict(unknown_categories), ensure_ascii=False)
    )
if len(eligible_all) < 2600:
    raise RuntimeError(f"Suspiciously small eligible store universe: {len(eligible_all)}")
if len(current_stores) < 2500:
    raise RuntimeError(f"Suspiciously small current eligible store count: {len(current_stores)}")

missing_required = [
    s["store_id"]
    for s in current_stores
    if not s.get("name") or not s.get("address") or s.get("lat") in (None, "") or s.get("lng") in (None, "")
]
if missing_required:
    raise RuntimeError(
        f"Current official rows missing name/address/coordinates: {len(missing_required)}"
    )

previous = load_json(CURRENT, {"stores": []})
history = load_json(HISTORY, {"stores": {}})
previous_by_id = {s["store_id"]: s for s in previous.get("stores", [])}
fresh_by_id = {s["store_id"]: s for s in current_stores}

if len(fresh_by_id) != len(current_stores):
    raise RuntimeError("Duplicate official store IDs detected")

if previous_by_id:
    ratio = len(current_stores) / len(previous_by_id)
    if ratio < 0.85 or ratio > 1.20:
        raise RuntimeError(
            f"Store count changed too much: previous={len(previous_by_id)} "
            f"current={len(current_stores)} ratio={ratio:.3f}"
        )
    previous_brand_counts = Counter(
        s.get("brand_name") for s in previous_by_id.values() if s.get("brand_name")
    )
    for brand_name, old_count in previous_brand_counts.items():
        if old_count >= 10:
            new_count = brand_counts.get(brand_name, 0)
            if new_count < old_count * 0.50:
                raise RuntimeError(
                    f"Brand count dropped too much: {brand_name} previous={old_count} current={new_count}"
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
    first_seen = (
        old_hist.get("first_seen")
        or previous_by_id.get(sid, {}).get("first_seen")
        or RUN_DATE
    )
    store["first_seen"] = first_seen
    store["last_seen"] = RUN_DATE
    store["status"] = "active"
    history["stores"][sid] = {
        "store_id": sid,
        "store_code": store.get("store_code"),
        "brand_code": store.get("brand_code"),
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
        "store_code": prior.get("store_code"),
        "brand_code": prior.get("brand_code"),
        "brand_name": prior.get("brand_name"),
        "name": prior.get("name"),
        "address": prior.get("address"),
        "first_seen": old_hist.get("first_seen") or prior.get("first_seen") or RUN_DATE,
        "last_seen": old_hist.get("last_seen") or prior.get("last_seen") or RUN_DATE,
        "missing_count": missing_count,
        "status": "missing_once" if missing_count == 1 else "removed_candidate",
    }

sorted_stores = sorted(
    current_stores,
    key=lambda s: (s.get("prefecture", ""), s.get("address", ""), s.get("name", "")),
)
sorted_upcoming = sorted(
    upcoming_stores,
    key=lambda s: (s.get("open_date", ""), s.get("prefecture", ""), s.get("name", "")),
)

brands_obj = {
    "source": SOURCE_URL,
    "generated_at": GENERATED_AT,
    "brands": [
        brand_by_category[code]
        for code in sorted(brand_by_category)
    ],
}
exclusions_obj = {
    "source": SOURCE_URL,
    "generated_at": GENERATED_AT,
    "rule": "Official store locator marker has is_yutaiken != true",
    "brands": [
        brand_by_category[code]
        for code in sorted(brand_by_category)
        if not brand_by_category[code]["eligible"]
    ],
}

current_obj = {
    "source": SOURCE_URL,
    "api_source": BASE_URL + "/api/point/{geohash_prefix}/",
    "generated_at": GENERATED_AT,
    "official_store_universe_count": len(raw_by_id),
    "eligible_universe_count": len(eligible_all),
    "eligible_count": len(sorted_stores),
    "upcoming_count": len(sorted_upcoming),
    "eligible_brand_count": len(eligible_brand_codes),
    "prefix_counts": prefix_counts,
    "brand_counts": dict(sorted(brand_counts.items())),
    "stores": sorted_stores,
    "upcoming_stores": sorted_upcoming,
}
snapshot_obj = dict(current_obj)
snapshot_obj["snapshot_date"] = RUN_DATE

diff_obj = {
    "source": SOURCE_URL,
    "generated_at": GENERATED_AT,
    "run_date": RUN_DATE,
    "previous_generated_at": previous.get("generated_at"),
    "counts": {
        "previous": len(previous_by_id),
        "current": len(fresh_by_id),
        "added": len(added_ids),
        "removed": len(removed_ids),
        "changed": len(changed_ids),
        "upcoming": len(sorted_upcoming),
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

save_json(BRANDS, brands_obj)
save_json(EXCLUSIONS, exclusions_obj)
save_json(CURRENT, current_obj)
save_json(SNAPSHOT, snapshot_obj)
save_json(DIFF, diff_obj)
save_json(HISTORY, history)

SUMMARY.parent.mkdir(parents=True, exist_ok=True)
with SUMMARY.open("w", encoding="utf-8") as f:
    f.write(f"# すかいらーく店舗DB 差分 {RUN_DATE}\n\n")
    f.write(f"- 公式店舗レコード全体: {len(raw_by_id)}\n")
    f.write(f"- 優待対象ブランド: {len(eligible_brand_codes)}\n")
    f.write(f"- 現在営業中の優待対象店舗: {len(current_stores)}\n")
    f.write(f"- 開店予定: {len(upcoming_stores)}\n")
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
            f.write(f"- {s.get('brand_name','')} / {s['name']} / {s['address']}\n")
    if removed_ids:
        f.write("\n## 消失\n")
        for sid in removed_ids[:200]:
            s = previous_by_id[sid]
            f.write(f"- {s.get('brand_name','')} / {s.get('name','')} / {s.get('address','')}\n")

print(json.dumps({
    "run_date": RUN_DATE,
    "official_store_universe_count": len(raw_by_id),
    "eligible_universe_count": len(eligible_all),
    "eligible_count": len(current_stores),
    "upcoming_count": len(upcoming_stores),
    "eligible_brand_count": len(eligible_brand_codes),
    "added": len(added_ids),
    "removed": len(removed_ids),
    "changed": len(changed_ids),
}, ensure_ascii=False))
