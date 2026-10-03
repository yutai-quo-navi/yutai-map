import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

from bs4 import BeautifulSoup

URL = "https://www.colowide.co.jp/gs/search_keyword_results.php"
TARGET = "コロワイド/カッパ・クリエイト/アトム株主優待"

JST = timezone(timedelta(hours=9))
NOW = datetime.now(JST)
RUN_DATE = NOW.strftime("%Y-%m-%d")
GENERATED_AT = NOW.isoformat(timespec="seconds")

BASE = Path("data/colowide")
CURRENT = BASE / "current.json"
HISTORY = BASE / "history.json"
SNAPSHOT = BASE / "snapshots" / f"{RUN_DATE}.json"
DIFF = BASE / "diffs" / f"{RUN_DATE}.json"
SUMMARY = BASE / "last_diff.md"

PREFS = [
    "北海道","青森県","岩手県","宮城県","秋田県","山形県","福島県","茨城県","栃木県","群馬県",
    "埼玉県","千葉県","東京都","神奈川県","新潟県","富山県","石川県","福井県","山梨県","長野県",
    "岐阜県","静岡県","愛知県","三重県","滋賀県","京都府","大阪府","兵庫県","奈良県","和歌山県",
    "鳥取県","島根県","岡山県","広島県","山口県","徳島県","香川県","愛媛県","高知県",
    "福岡県","佐賀県","長崎県","熊本県","大分県","宮崎県","鹿児島県","沖縄県",
]
ADDR_RE = re.compile(r"^(?:" + "|".join(map(re.escape, PREFS)) + r").+")
PHONE_RE = re.compile(r"0\d{1,4}-\d{1,4}-\d{3,4}")

def normalize(s: str) -> str:
    return re.sub(r"[\s　・･\-‐–—ー_]+", "", str(s or "")).lower()

def stable_id(name: str, address: str, detail_url: str) -> str:
    if detail_url:
        parsed = urllib.parse.urlparse(detail_url)
        qs = urllib.parse.parse_qs(parsed.query)
        for key in ("id", "shop_id", "store_id", "shop", "store"):
            if qs.get(key):
                return f"official:{key}:{qs[key][0]}"
        m = re.search(r"/(?:shop|store)/(\d+)", parsed.path)
        if m:
            return f"official:path:{m.group(1)}"
    raw = normalize(name) + "|" + normalize(address)
    return "hash:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

def load_json(path: Path, default):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as f:
        return json.load(f)

def save_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")

def fetch_html() -> str:
    req = urllib.request.Request(
        URL,
        headers={
            "User-Agent": "Mozilla/5.0 yutai-map-alpha/1.0 (+https://github.com/yutai-quo-navi/yutai-map)"
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")

def parse_stores(html: str):
    soup = BeautifulSoup(html, "html.parser")
    stores = []
    seen_ids = set()

    for h3 in soup.find_all("h3"):
        chosen = None
        node = h3
        for _ in range(10):
            node = node.parent
            if not node:
                break
            txt = "\n".join(node.stripped_strings)
            if TARGET in txt and len(node.find_all("h3")) == 1:
                chosen = node
                break
        if not chosen:
            continue

        name = " ".join(h3.stripped_strings).strip()
        if not name:
            continue

        lines = [x.strip() for x in chosen.stripped_strings if x.strip()]
        benefit_lines = [x for x in lines if "株主優待" in x]
        if not any(TARGET in x for x in benefit_lines):
            continue

        address = next((x for x in lines if ADDR_RE.match(x)), "")
        phone = ""
        for x in lines:
            m = PHONE_RE.search(x)
            if m:
                phone = m.group(0)
                break

        a = h3.find("a", href=True)
        detail_url = urllib.parse.urljoin(URL, a["href"]) if a else ""
        store_id = stable_id(name, address, detail_url)

        if store_id in seen_ids:
            continue
        seen_ids.add(store_id)

        stores.append({
            "store_id": store_id,
            "name": name,
            "address": address,
            "phone": phone,
            "benefits": benefit_lines,
            "official_url": detail_url,
        })

    page_text = " ".join(soup.stripped_strings)
    m = re.search(r"(\d[\d,]*)\s*店舗", page_text)
    source_store_count = int(m.group(1).replace(",", "")) if m else None
    return source_store_count, stores

def comparable(store):
    return {
        "name": store.get("name", ""),
        "address": store.get("address", ""),
        "phone": store.get("phone", ""),
        "benefits": store.get("benefits", []),
        "official_url": store.get("official_url", ""),
    }

html = fetch_html()
source_store_count, fresh_stores = parse_stores(html)

previous = load_json(CURRENT, {"stores": []})
history = load_json(HISTORY, {"stores": {}})
previous_by_id = {s["store_id"]: s for s in previous.get("stores", [])}
fresh_by_id = {s["store_id"]: s for s in fresh_stores}

added_ids = sorted(set(fresh_by_id) - set(previous_by_id))
removed_ids = sorted(set(previous_by_id) - set(fresh_by_id))
common_ids = sorted(set(fresh_by_id) & set(previous_by_id))
changed_ids = [sid for sid in common_ids if comparable(fresh_by_id[sid]) != comparable(previous_by_id[sid])]

for sid, store in fresh_by_id.items():
    h = history["stores"].get(sid, {})
    first_seen = h.get("first_seen") or previous_by_id.get(sid, {}).get("first_seen") or RUN_DATE
    store["first_seen"] = first_seen
    store["last_seen"] = RUN_DATE
    store["status"] = "active"

    history["stores"][sid] = {
        "store_id": sid,
        "name": store["name"],
        "address": store["address"],
        "first_seen": first_seen,
        "last_seen": RUN_DATE,
        "missing_count": 0,
        "status": "active",
    }

for sid in removed_ids:
    prior = previous_by_id[sid]
    h = history["stores"].get(sid, {})
    missing_count = int(h.get("missing_count", 0)) + 1
    history["stores"][sid] = {
        "store_id": sid,
        "name": prior.get("name", ""),
        "address": prior.get("address", ""),
        "first_seen": h.get("first_seen") or prior.get("first_seen") or RUN_DATE,
        "last_seen": h.get("last_seen") or prior.get("last_seen") or RUN_DATE,
        "missing_count": missing_count,
        "status": "missing_once" if missing_count == 1 else "removed_candidate",
    }

current_obj = {
    "source": URL,
    "target_benefit": TARGET,
    "generated_at": GENERATED_AT,
    "source_store_count": source_store_count,
    "eligible_count": len(fresh_stores),
    "stores": sorted(fresh_stores, key=lambda x: (x.get("address", ""), x.get("name", ""))),
}

snapshot_obj = current_obj.copy()
snapshot_obj["snapshot_date"] = RUN_DATE

diff_obj = {
    "source": URL,
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
        {
            "store_id": sid,
            "before": previous_by_id[sid],
            "after": fresh_by_id[sid],
        }
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
    f.write(f"# コロワイド店舗DB 差分 {RUN_DATE}\n\n")
    f.write(f"- 公式検索全体表示: {source_store_count if source_store_count is not None else '不明'} 店舗\n")
    f.write(f"- 優待対象抽出: {len(fresh_stores)} 店舗\n")
    f.write(f"- 新規: {len(added_ids)}\n")
    f.write(f"- 消失: {len(removed_ids)}\n")
    f.write(f"- 変更: {len(changed_ids)}\n")

    if added_ids:
        f.write("\n## 新規\n")
        for sid in added_ids:
            s = fresh_by_id[sid]
            f.write(f"- {s['name']} / {s.get('address','')}\n")

    if removed_ids:
        f.write("\n## 消失\n")
        for sid in removed_ids:
            s = previous_by_id[sid]
            f.write(f"- {s['name']} / {s.get('address','')}\n")

    if changed_ids:
        f.write("\n## 変更\n")
        for sid in changed_ids:
            b, n = previous_by_id[sid], fresh_by_id[sid]
            f.write(f"- {b.get('name','')} → {n.get('name','')} / {n.get('address','')}\n")

print(json.dumps({
    "run_date": RUN_DATE,
    "source_store_count": source_store_count,
    "eligible_count": len(fresh_stores),
    "added": len(added_ids),
    "removed": len(removed_ids),
    "changed": len(changed_ids),
}, ensure_ascii=False))
