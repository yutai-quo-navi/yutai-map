import json
import re
import urllib.request
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

SOURCE_URL = "https://www.create-restaurants.co.jp/"
BENEFIT_URL = "https://www.createrestaurants.com/ir/stock/shareholder/"

BASE = Path("data/issuers/create/stores")
CURRENT = BASE / "current.json"
HISTORY = BASE / "history.json"
SUMMARY = BASE / "last_diff.md"
BRANDS = Path("data/issuers/create/brands.json")
EXCLUSIONS = Path("data/issuers/create/exclusions.json")

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

ELIGIBLE_VALUES = {"available", "aveilable"}
KNOWN_SHAREHOLDER_VALUES = {"", "available", "aveilable", "not available", "none"}

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

def fetch_html():
    req = urllib.request.Request(
        SOURCE_URL,
        headers={
            "User-Agent": UA,
            "Accept-Language": "ja,en-US;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=240) as r:
        data = r.read()
    if len(data) < 1_000_000:
        raise RuntimeError(f"Official restaurant page is unexpectedly small: {len(data)} bytes")
    return data.decode("utf-8", "replace")

def extract_shops_object(html):
    marker = "const shops_json = "
    pos = html.find(marker)
    if pos < 0:
        raise RuntimeError("Official page no longer exposes shops_json")

    raw = html[pos + len(marker):]
    # The current page emits one large JS object whose values are valid JSON arrays.
    # The object ends before the next script statement.
    end = raw.find("};")
    if end < 0:
        raise RuntimeError("Could not find the end of shops_json")
    literal = raw[:end + 1].strip()

    # Top-level keys are single-quoted JS identifiers. Nested store objects are JSON.
    normalized = re.sub(
        r"'([^'\\]+)'\s*:",
        lambda m: json.dumps(m.group(1), ensure_ascii=False) + ":",
        literal,
    )
    try:
        obj = json.loads(normalized)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"shops_json format changed: {e}") from e

    if not isinstance(obj, dict):
        raise RuntimeError("shops_json is no longer an object")
    return obj

def normalize_shareholder(value):
    return str(value or "").strip().lower()

def parse_date(value):
    text = str(value or "").strip()
    if not text or text.startswith("0000-00-00"):
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            pass
    raise RuntimeError(f"Unexpected official date format: {text!r}")

def join_address(row):
    pref = str(row.get("pref_name") or "").strip()
    a1 = str(row.get("address1_jp") or "").strip()
    a2 = str(row.get("address2_jp") or "").strip()
    if pref and a1.startswith(pref):
        first = a1
    else:
        first = pref + a1
    return re.sub(r"\s+", " ", (first + " " + a2).strip())

def category_for(row):
    text = " ".join([
        str(row.get("business_type") or ""),
        str(row.get("name_jp") or ""),
    ])
    if any(k in text for k in ("ベーカリー", "パン", "ブーランジェリー", "ベーグル")):
        return "bakery"
    if any(k in text for k in ("カフェ", "珈琲", "コーヒー", "抹茶専門")):
        return "cafe"
    if any(k in text for k in ("フードコート", "クレープ＆QQ", "クレープ＆ＱＱ", "ローストビーフ丼専門")):
        return "foodcourt"
    return "restaurant"

def comparable(store):
    return {
        "name": store.get("name"),
        "address": store.get("address"),
        "prefecture": store.get("prefecture"),
        "phone": store.get("phone"),
        "lat": store.get("lat"),
        "lng": store.get("lng"),
        "business_type": store.get("business_type"),
        "category": store.get("category"),
        "open_date": store.get("open_date"),
        "close_date": store.get("close_date"),
        "official_url": store.get("official_url"),
    }

html = fetch_html()
shops_obj = extract_shops_object(html)

required_containers = {
    "rest_api_country_5",
    "rest_api_app_country_5",
    "rest_api_app_9_country_5",
}
missing_containers = required_containers - set(shops_obj)
if missing_containers:
    raise RuntimeError(
        "Official store dataset containers changed/missing: "
        + ", ".join(sorted(missing_containers))
    )

main_rows = shops_obj.get("rest_api_country_5")
if not isinstance(main_rows, list):
    raise RuntimeError("rest_api_country_5 is not a list")

# The two app containers are subsets of the web container. Verify that assumption every run;
# if the official page architecture changes, stop rather than silently dropping stores.
main_ids = {str(x.get("store_id")) for x in main_rows if isinstance(x, dict)}
union_ids = set()
container_counts = {}
for key, value in shops_obj.items():
    if not isinstance(value, list):
        continue
    ids = {str(x.get("store_id")) for x in value if isinstance(x, dict)}
    union_ids |= ids
    container_counts[key] = len(ids)
if union_ids - main_ids:
    raise RuntimeError(
        f"Official secondary datasets now contain {len(union_ids - main_ids)} stores outside main dataset"
    )

if len(main_rows) < 900:
    raise RuntimeError(f"Suspiciously small official store universe: {len(main_rows)}")
if len(main_ids) != len(main_rows):
    raise RuntimeError(
        f"Duplicate/missing official store IDs: rows={len(main_rows)} ids={len(main_ids)}"
    )

shareholder_counts = Counter(normalize_shareholder(x.get("shareholder")) for x in main_rows)
unexpected_shareholder = set(shareholder_counts) - KNOWN_SHAREHOLDER_VALUES
if unexpected_shareholder:
    raise RuntimeError(
        "Unknown official shareholder eligibility values: "
        + json.dumps(sorted(unexpected_shareholder), ensure_ascii=False)
    )

eligible_rows = [
    x for x in main_rows
    if normalize_shareholder(x.get("shareholder")) in ELIGIBLE_VALUES
]
if len(eligible_rows) < 750:
    raise RuntimeError(f"Suspiciously small shareholder-benefit store count: {len(eligible_rows)}")

current_stores = []
upcoming_stores = []
business_counts = Counter()
excluded_rows = []

for row in main_rows:
    shareholder = normalize_shareholder(row.get("shareholder"))
    if shareholder not in ELIGIBLE_VALUES:
        excluded_rows.append({
            "store_id": str(row.get("store_id") or ""),
            "name": str(row.get("name_jp") or "").strip(),
            "reason": shareholder or "eligibility_blank",
        })
        continue

    if str(row.get("status") or "") != "1":
        continue

    open_date = parse_date(row.get("open_date"))
    close_date = parse_date(row.get("close_date"))

    store = {
        "store_id": f"official:id:{row.get('store_id')}",
        "official_id": str(row.get("store_id") or ""),
        "original_id": str(row.get("original_id") or ""),
        "name": str(row.get("name_jp") or "").strip(),
        "business_type": str(row.get("business_type") or "").strip(),
        "brand_name": str(row.get("business_type") or "").strip() or "公式対象店",
        "category": category_for(row),
        "address": join_address(row),
        "prefecture": str(row.get("pref_name") or "").strip(),
        "postal_code": str(row.get("post_code") or "").strip(),
        "phone": str(row.get("tel_number") or "").strip(),
        "lat": row.get("latitude"),
        "lng": row.get("longitude"),
        "open_date": str(row.get("open_date") or "").strip(),
        "close_date": str(row.get("close_date") or "").strip(),
        "official_url": str(row.get("store_url") or "").strip() or SOURCE_URL,
        "benefit_status": "available",
    }

    if not store["name"] or not store["address"]:
        raise RuntimeError(f"Eligible official store missing name/address: {store['store_id']}")
    try:
        lat = float(store["lat"])
        lng = float(store["lng"])
    except (TypeError, ValueError):
        raise RuntimeError(f"Eligible official store missing coordinates: {store['store_id']}")
    if not (20 <= lat <= 50 and 120 <= lng <= 155):
        raise RuntimeError(
            f"Eligible official store has suspicious coordinates: {store['store_id']} {lat},{lng}"
        )
    store["lat"] = lat
    store["lng"] = lng

    if open_date and open_date > TODAY:
        upcoming_stores.append(store)
        continue
    if close_date and close_date < TODAY:
        continue

    current_stores.append(store)
    business_counts[store["business_type"] or "(未分類)"] += 1

if len(current_stores) < 750:
    raise RuntimeError(f"Suspiciously small current eligible store count: {len(current_stores)}")
pref_count = len({s["prefecture"] for s in current_stores if s["prefecture"]})
if pref_count < 30:
    raise RuntimeError(f"Suspiciously few prefectures in eligible DB: {pref_count}")

previous = load_json(CURRENT, {"stores": []})
history = load_json(HISTORY, {"stores": {}})
previous_by_id = {s["store_id"]: s for s in previous.get("stores", [])}
fresh_by_id = {s["store_id"]: s for s in current_stores}

if len(fresh_by_id) != len(current_stores):
    raise RuntimeError("Duplicate eligible official store IDs detected")

if previous_by_id:
    ratio = len(fresh_by_id) / len(previous_by_id)
    if ratio < 0.80 or ratio > 1.25:
        raise RuntimeError(
            f"Store count changed too much: previous={len(previous_by_id)} "
            f"current={len(fresh_by_id)} ratio={ratio:.3f}"
        )
    previous_pref_counts = Counter(s.get("prefecture") for s in previous_by_id.values())
    current_pref_counts = Counter(s.get("prefecture") for s in fresh_by_id.values())
    for pref, old_count in previous_pref_counts.items():
        if pref and old_count >= 15 and current_pref_counts.get(pref, 0) < old_count * 0.50:
            raise RuntimeError(
                f"Prefecture count dropped too much: {pref} "
                f"previous={old_count} current={current_pref_counts.get(pref, 0)}"
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
        "name": store.get("name"),
        "business_type": store.get("business_type"),
        "address": store.get("address"),
        "prefecture": store.get("prefecture"),
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
        "name": prior.get("name"),
        "business_type": prior.get("business_type"),
        "address": prior.get("address"),
        "prefecture": prior.get("prefecture"),
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
    "business_types": [
        {"name": name, "eligible_store_count": count}
        for name, count in sorted(business_counts.items())
    ],
}

exclusions_obj = {
    "source": SOURCE_URL,
    "generated_at": GENERATED_AT,
    "rule": "Official restaurant search shareholder flag is not available",
    "shareholder_value_counts": dict(sorted(shareholder_counts.items())),
    "excluded_count": len(excluded_rows),
    "stores": excluded_rows,
}

current_obj = {
    "source": SOURCE_URL,
    "benefit_source": BENEFIT_URL,
    "generated_at": GENERATED_AT,
    "official_store_universe_count": len(main_rows),
    "eligible_flagged_count": len(eligible_rows),
    "eligible_count": len(sorted_stores),
    "upcoming_count": len(sorted_upcoming),
    "prefecture_count": pref_count,
    "container_counts": container_counts,
    "shareholder_value_counts": dict(sorted(shareholder_counts.items())),
    "business_type_counts": dict(sorted(business_counts.items())),
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
    f.write(f"# クリレス店舗DB 差分 {RUN_DATE}\n\n")
    f.write(f"- 公式店舗レコード全体: {len(main_rows)}\n")
    f.write(f"- 優待利用可フラグ: {len(eligible_rows)}\n")
    f.write(f"- 現在の優待対象店舗: {len(current_stores)}\n")
    f.write(f"- 開店予定: {len(upcoming_stores)}\n")
    f.write(f"- 対象都道府県: {pref_count}\n")
    f.write(f"- 新規: {len(added_ids)}\n")
    f.write(f"- 消失: {len(removed_ids)}\n")
    f.write(f"- 変更: {len(changed_ids)}\n")
    if added_ids:
        f.write("\n## 新規\n")
        for sid in added_ids[:200]:
            s = fresh_by_id[sid]
            f.write(f"- {s.get('name','')} / {s.get('address','')}\n")
    if removed_ids:
        f.write("\n## 消失\n")
        for sid in removed_ids[:200]:
            s = previous_by_id[sid]
            f.write(f"- {s.get('name','')} / {s.get('address','')}\n")

print(json.dumps({
    "run_date": RUN_DATE,
    "official_store_universe_count": len(main_rows),
    "eligible_flagged_count": len(eligible_rows),
    "eligible_count": len(current_stores),
    "upcoming_count": len(upcoming_stores),
    "prefecture_count": pref_count,
    "added": len(added_ids),
    "removed": len(removed_ids),
    "changed": len(changed_ids),
}, ensure_ascii=False))
