#!/usr/bin/env python3
import html
import http.cookiejar
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE_URL = "https://maps.zensho.co.jp"
SEARCH_PAGE = BASE_URL + "/jp/shop.html"
API_URL = BASE_URL + "/api/search"
BENEFIT_URL = "https://www.zensho.co.jp/jp/ir/investor/complimentary.html"

BASE = Path("data/issuers/zensho/stores")
CURRENT = BASE / "current.json"
HISTORY = BASE / "history.json"
SUMMARY = BASE / "last_diff.md"
BRANDS = Path("data/issuers/zensho/brands.json")

JST = timezone(timedelta(hours=9))
NOW = datetime.now(JST)
RUN_DATE = NOW.strftime("%Y-%m-%d")
GENERATED_AT = NOW.isoformat(timespec="seconds")
SNAPSHOT = BASE / "snapshots" / f"{RUN_DATE}.json"
DIFF = BASE / "diffs" / f"{RUN_DATE}.json"

UA = "Mozilla/5.0 yutai-map-zensho/1.0 (+https://github.com/yutai-quo-navi/yutai-map)"
REQUEST_INTERVAL = 0.60
MAX_RETRIES = 3

PREFECTURES = [
    "北海道",
    "青森県","岩手県","宮城県","秋田県","山形県","福島県",
    "茨城県","栃木県","群馬県","埼玉県","千葉県","東京都","神奈川県",
    "新潟県","富山県","石川県","福井県","山梨県","長野県",
    "岐阜県","静岡県","愛知県","三重県",
    "滋賀県","京都府","大阪府","兵庫県","奈良県","和歌山県",
    "鳥取県","島根県","岡山県","広島県","山口県",
    "徳島県","香川県","愛媛県","高知県",
    "福岡県","佐賀県","長崎県","熊本県","大分県","宮崎県","鹿児島県","沖縄県",
]

PREF_RE = re.compile(
    r"^(北海道|東京都|京都府|大阪府|"
    + "|".join(re.escape(x) for x in PREFECTURES if x.endswith("県"))
    + r")"
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


def opener():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


_last_request_at = 0.0


def throttle():
    global _last_request_at
    wait = REQUEST_INTERVAL - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)


def post_json(op, pairs):
    global _last_request_at
    body = urllib.parse.urlencode(pairs).encode()
    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "User-Agent": UA,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "ja,en;q=0.8",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Referer": SEARCH_PAGE,
        },
    )

    error = None
    for attempt in range(1, MAX_RETRIES + 1):
        throttle()
        try:
            with op.open(req, timeout=180) as r:
                payload = r.read().decode("utf-8", "replace")
                _last_request_at = time.monotonic()
                data = json.loads(payload)
                if not isinstance(data, dict):
                    raise RuntimeError("Zensho search API response is not an object")
                return data
        except (urllib.error.URLError, json.JSONDecodeError, RuntimeError) as e:
            _last_request_at = time.monotonic()
            error = e
            if attempt == MAX_RETRIES:
                break
            time.sleep(2 ** attempt)

    raise RuntimeError(f"Zensho API failed after {MAX_RETRIES} attempts: {error!r}")


def strip_tags(value):
    text = re.sub(r"<br\s*/?>", " ", str(value or ""), flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def result_count(list_html):
    m = re.search(r"検索結果：\s*<strong>([\d,]+)</strong>件", list_html or "")
    if not m:
        raise RuntimeError("Could not read Zensho result count")
    return int(m.group(1).replace(",", ""))


def detail_id(value):
    m = re.search(r"/jp/detail/(\d+)\.html", str(value or ""))
    return m.group(1) if m else ""


def parse_list_rows(list_html):
    rows = {}
    for m in re.finditer(r"<li\b[^>]*>(.*?)</li>", list_html or "", re.I | re.S):
        block = m.group(1)
        sid = detail_id(block)
        if not sid:
            continue

        h2 = re.search(r"<h2\b[^>]*>(.*?)</h2>", block, re.I | re.S)
        address = re.search(
            r'<dl\b[^>]*class=["\'][^"\']*address[^"\']*["\'][^>]*>.*?<dd\b[^>]*>(.*?)</dd>',
            block,
            re.I | re.S,
        )
        tel = re.search(
            r'<dl\b[^>]*class=["\'][^"\']*tel[^"\']*["\'][^>]*>.*?<dd\b[^>]*>(.*?)</dd>',
            block,
            re.I | re.S,
        )

        rows[sid] = {
            "full_name": strip_tags(h2.group(1)) if h2 else "",
            "address": strip_tags(address.group(1)) if address else "",
            "phone": strip_tags(tel.group(1)) if tel else "",
        }
    return rows


def category_for(brand, name):
    text = f"{brand} {name}"
    if any(k in text for k in ("カフェ", "珈琲", "コーヒー")):
        return "cafe"
    if any(k in text for k in ("ベーカリー", "パン")):
        return "bakery"
    return "restaurant"


def fetch_prefecture(prefecture):
    op = opener()
    initial = post_json(
        op,
        [
            ("brand[]", ""),
            ("facility[]", "shareholder_coupon"),
            ("address", prefecture),
        ],
    )
    count = result_count(initial.get("list") or "")

    payload = initial
    if count > 50:
        # Official UI's "more" request uses the current search state held in the session.
        # Keep the same cookie jar and ask for the remaining rows cumulatively.
        payload = post_json(op, [("morelist", str(count - 50))])

    list_html = payload.get("list") or ""
    mapdata = payload.get("mapdata")
    if not isinstance(mapdata, list):
        raise RuntimeError(f"{prefecture}: mapdata is not a list")

    listed = parse_list_rows(list_html)
    if len(mapdata) != count:
        raise RuntimeError(
            f"{prefecture}: mapdata count mismatch expected={count} actual={len(mapdata)}"
        )
    if len(listed) != count:
        raise RuntimeError(
            f"{prefecture}: list count mismatch expected={count} actual={len(listed)}"
        )

    stores = []
    ids = set()
    for item in mapdata:
        if not isinstance(item, dict):
            raise RuntimeError(f"{prefecture}: invalid mapdata row")

        sid = detail_id(item.get("link"))
        if not sid:
            raise RuntimeError(f"{prefecture}: mapdata row without official detail id")
        if sid in ids:
            raise RuntimeError(f"{prefecture}: duplicate detail id {sid}")
        ids.add(sid)

        listed_row = listed.get(sid)
        if not listed_row:
            raise RuntimeError(f"{prefecture}: detail id {sid} missing from list HTML")

        brand = str(item.get("brand") or "").strip()
        branch_name = str(item.get("name") or "").strip()
        full_name = listed_row["full_name"] or (brand + " " + branch_name).strip()
        address = listed_row["address"]
        phone = listed_row["phone"]

        try:
            lat = float(item.get("lat"))
            lng = float(item.get("lng"))
        except (TypeError, ValueError):
            raise RuntimeError(f"{prefecture}: invalid coordinates for {sid}")

        if not (20.0 <= lat <= 50.0 and 120.0 <= lng <= 155.0):
            raise RuntimeError(f"{prefecture}: coordinates outside Japan bounds for {sid}: {lat},{lng}")
        if not brand or not branch_name or not address:
            raise RuntimeError(f"{prefecture}: required official fields missing for {sid}")

        pm = PREF_RE.match(address)
        actual_pref = pm.group(1) if pm else ""
        if actual_pref != prefecture:
            # Official address search is substring based (e.g. "京都府" also
            # matches "東京都府中市"). Keep only rows whose actual address
            # starts with the requested prefecture, then verify nationwide
            # parity against the official eligible total after all 47 runs.
            continue

        stores.append({
            "store_id": f"official:id:{sid}",
            "official_id": sid,
            "brand_name": brand,
            "category": category_for(brand, full_name),
            "name": full_name,
            "branch_name": branch_name,
            "address": address,
            "prefecture": actual_pref,
            "phone": phone,
            "lat": lat,
            "lng": lng,
            "benefit_status": "shareholder_coupon",
            "official_url": urllib.parse.urljoin(BASE_URL, str(item.get("link") or "")),
        })

    return len(stores), stores


def fetch_universe_count():
    op = opener()
    payload = post_json(op, [])
    return result_count(payload.get("list") or "")


def comparable(store):
    return {
        "brand_name": store.get("brand_name"),
        "category": store.get("category"),
        "name": store.get("name"),
        "branch_name": store.get("branch_name"),
        "address": store.get("address"),
        "prefecture": store.get("prefecture"),
        "phone": store.get("phone"),
        "lat": store.get("lat"),
        "lng": store.get("lng"),
        "benefit_status": store.get("benefit_status"),
        "official_url": store.get("official_url"),
    }


official_universe_count = fetch_universe_count()
if not (4500 <= official_universe_count <= 5500):
    raise RuntimeError(
        f"Suspicious official store universe count: {official_universe_count}"
    )

all_stores = []
prefecture_counts = {}
for prefecture in PREFECTURES:
    count, stores = fetch_prefecture(prefecture)
    prefecture_counts[prefecture] = count
    all_stores.extend(stores)
    print(f"{prefecture}: {count}", flush=True)

fresh_by_id = {s["store_id"]: s for s in all_stores}
if len(fresh_by_id) != len(all_stores):
    duplicates = len(all_stores) - len(fresh_by_id)
    raise RuntimeError(f"Duplicate official IDs across prefectures: {duplicates}")

eligible_count = len(all_stores)
if not (4300 <= eligible_count <= 5200):
    raise RuntimeError(f"Suspicious shareholder-benefit store count: {eligible_count}")

# Read the official nationwide shareholder-coupon total independently.
# This catches a missing prefecture, an API behavior change, or accidental
# filtering even when every individual prefecture request looks plausible.
eligible_probe = post_json(
    opener(),
    [("brand[]", ""), ("facility[]", "shareholder_coupon")],
)
official_eligible_count = result_count(eligible_probe.get("list") or "")
if eligible_count != official_eligible_count:
    raise RuntimeError(
        "Nationwide eligible count mismatch: "
        f"partitioned={eligible_count} official={official_eligible_count}"
    )

if eligible_count > official_universe_count:
    raise RuntimeError(
        f"Eligible count exceeds official universe: {eligible_count}>{official_universe_count}"
    )

nonempty_prefectures = sum(1 for n in prefecture_counts.values() if n > 0)
if nonempty_prefectures < 45:
    raise RuntimeError(f"Suspiciously few prefectures with eligible stores: {nonempty_prefectures}")

brand_counts = Counter(s["brand_name"] for s in all_stores)
if len(brand_counts) < 10:
    raise RuntimeError(f"Suspiciously few eligible brands: {len(brand_counts)}")

previous = load_json(CURRENT, {"stores": []})
history = load_json(HISTORY, {"stores": {}})
previous_by_id = {s["store_id"]: s for s in previous.get("stores", [])}

if previous_by_id:
    ratio = eligible_count / len(previous_by_id)
    if ratio < 0.90 or ratio > 1.10:
        raise RuntimeError(
            f"Store count changed too much: previous={len(previous_by_id)} "
            f"current={eligible_count} ratio={ratio:.3f}"
        )

    old_brand_counts = Counter(s.get("brand_name") for s in previous_by_id.values())
    for brand, old_count in old_brand_counts.items():
        if brand and old_count >= 20:
            new_count = brand_counts.get(brand, 0)
            if new_count < old_count * 0.65:
                raise RuntimeError(
                    f"Brand count dropped too much: {brand} "
                    f"previous={old_count} current={new_count}"
                )

    old_pref_counts = Counter(s.get("prefecture") for s in previous_by_id.values())
    for pref, old_count in old_pref_counts.items():
        if pref and old_count >= 20:
            new_count = prefecture_counts.get(pref, 0)
            if new_count < old_count * 0.65:
                raise RuntimeError(
                    f"Prefecture count dropped too much: {pref} "
                    f"previous={old_count} current={new_count}"
                )

added_ids = sorted(set(fresh_by_id) - set(previous_by_id))
removed_ids = sorted(set(previous_by_id) - set(fresh_by_id))
common_ids = sorted(set(fresh_by_id) & set(previous_by_id))
changed_ids = [
    sid for sid in common_ids
    if comparable(fresh_by_id[sid]) != comparable(previous_by_id[sid])
]

# Once a baseline exists, stop on bulk changes rather than overwriting D1 with a bad scrape.
if previous_by_id:
    if len(added_ids) > 250:
        raise RuntimeError(f"Too many added stores in one run: {len(added_ids)}")
    if len(removed_ids) > 250:
        raise RuntimeError(f"Too many removed stores in one run: {len(removed_ids)}")
    if len(changed_ids) > 600:
        raise RuntimeError(f"Too many changed stores in one run: {len(changed_ids)}")

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
        "brand_name": store.get("brand_name"),
        "name": store.get("name"),
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
        "brand_name": prior.get("brand_name"),
        "name": prior.get("name"),
        "address": prior.get("address"),
        "prefecture": prior.get("prefecture"),
        "first_seen": old_hist.get("first_seen") or prior.get("first_seen") or RUN_DATE,
        "last_seen": old_hist.get("last_seen") or prior.get("last_seen") or RUN_DATE,
        "missing_count": missing_count,
        "status": "missing_once" if missing_count == 1 else "removed_candidate",
    }

sorted_stores = sorted(
    all_stores,
    key=lambda s: (
        PREFECTURES.index(s["prefecture"]) if s["prefecture"] in PREFECTURES else 999,
        s["address"],
        s["name"],
    ),
)

current_obj = {
    "source": SEARCH_PAGE,
    "benefit_source": BENEFIT_URL,
    "api_source": API_URL,
    "generated_at": GENERATED_AT,
    "official_store_universe_count": official_universe_count,
    "eligible_count": eligible_count,
    "official_eligible_count": official_eligible_count,
    "eligible_filter": "shareholder_coupon",
    "prefecture_count": nonempty_prefectures,
    "prefecture_counts": prefecture_counts,
    "brand_counts": dict(sorted(brand_counts.items())),
    "stores": sorted_stores,
}

snapshot_obj = dict(current_obj)
snapshot_obj["snapshot_date"] = RUN_DATE

diff_obj = {
    "source": SEARCH_PAGE,
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

brands_obj = {
    "source": SEARCH_PAGE,
    "generated_at": GENERATED_AT,
    "eligible_filter": "shareholder_coupon",
    "brands": [
        {"name": name, "eligible_store_count": count}
        for name, count in sorted(brand_counts.items())
    ],
}

history["updated_at"] = GENERATED_AT
history["run_date"] = RUN_DATE

save_json(BRANDS, brands_obj)
save_json(CURRENT, current_obj)
save_json(SNAPSHOT, snapshot_obj)
save_json(DIFF, diff_obj)
save_json(HISTORY, history)

SUMMARY.parent.mkdir(parents=True, exist_ok=True)
with SUMMARY.open("w", encoding="utf-8") as f:
    f.write(f"# ゼンショー店舗DB 差分 {RUN_DATE}\n\n")
    f.write(f"- 公式店舗全体: {official_universe_count}\n")
    f.write(f"- 株主優待券利用可: {eligible_count}\n")
    f.write(f"- 対象都道府県: {nonempty_prefectures}\n")
    f.write(f"- ブランド数: {len(brand_counts)}\n")
    f.write(f"- 新規: {len(added_ids)}\n")
    f.write(f"- 消失: {len(removed_ids)}\n")
    f.write(f"- 変更: {len(changed_ids)}\n")
    f.write("\n## ブランド別\n")
    for name, count in sorted(brand_counts.items()):
        f.write(f"- {name}: {count}\n")
    f.write("\n## 都道府県別\n")
    for pref in PREFECTURES:
        f.write(f"- {pref}: {prefecture_counts[pref]}\n")

print(json.dumps({
    "run_date": RUN_DATE,
    "official_store_universe_count": official_universe_count,
    "eligible_count": eligible_count,
    "official_eligible_count": official_eligible_count,
    "prefecture_count": nonempty_prefectures,
    "brand_count": len(brand_counts),
    "brand_counts": dict(sorted(brand_counts.items())),
    "added": len(added_ids),
    "removed": len(removed_ids),
    "changed": len(changed_ids),
}, ensure_ascii=False))
