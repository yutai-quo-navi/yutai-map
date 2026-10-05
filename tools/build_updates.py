import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

JST = timezone(timedelta(hours=9))
NOW = datetime.now(JST)
ROOT = Path("data")
ISSUERS = ROOT / "issuers"
INDEX = ISSUERS / "index.json"
OUTPUT = ROOT / "updates.json"

INTERNAL_FIELDS = {
    "first_seen", "last_seen", "status", "missing_count",
    "generated_at", "snapshot_date"
}

FIELD_LABELS = {
    "name": "店名",
    "brand_name": "ブランド",
    "business_type": "業態",
    "address": "住所",
    "prefecture": "都道府県",
    "postal_code": "郵便番号",
    "phone": "電話",
    "lat": "緯度",
    "lng": "経度",
    "open_date": "開店日",
    "close_date": "閉店日",
    "benefits": "優待対象",
    "benefit_status": "優待対象",
    "official_url": "公式URL",
}


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


def changed_fields(before, after):
    keys = sorted((set(before) | set(after)) - INTERNAL_FIELDS)
    return [
        {
            "key": key,
            "label": FIELD_LABELS.get(key, key),
            "before": before.get(key),
            "after": after.get(key),
        }
        for key in keys
        if before.get(key) != after.get(key)
    ]


def event_id(payload):
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


manifest = load_json(INDEX, {"issuers": []})
issuer_meta = {
    x["id"]: {
        "id": x["id"],
        "code": x.get("code", ""),
        "name": x.get("name", x["id"]),
    }
    for x in manifest.get("issuers", [])
}

existing = load_json(OUTPUT, {"events": []})
events_by_id = {
    e["event_id"]: e
    for e in existing.get("events", [])
    if isinstance(e, dict) and e.get("event_id")
}

for issuer_dir in sorted(ISSUERS.iterdir()):
    if not issuer_dir.is_dir():
        continue
    issuer_id = issuer_dir.name
    meta = issuer_meta.get(issuer_id, {"id": issuer_id, "code": "", "name": issuer_id})
    diff_dir = issuer_dir / "stores" / "diffs"
    if not diff_dir.exists():
        continue

    for diff_path in sorted(diff_dir.glob("*.json")):
        diff = load_json(diff_path, {})
        counts = diff.get("counts") or {}

        # 初回DB生成時の全件追加は「新店」ではないため履歴に出さない。
        if not diff.get("previous_generated_at") or int(counts.get("previous") or 0) == 0:
            continue

        at = diff.get("generated_at") or (str(diff.get("run_date") or "") + "T00:00:00+09:00")
        run_date = diff.get("run_date") or str(at)[:10]

        for kind, rows in (
            ("added", diff.get("added") or []),
            ("removed", diff.get("removed") or []),
        ):
            for store in rows:
                core = {
                    "issuer_id": issuer_id,
                    "kind": kind,
                    "run_date": run_date,
                    "store_id": store.get("store_id", ""),
                    "name": store.get("name", ""),
                    "address": store.get("address", ""),
                    "brand_name": store.get("brand_name") or store.get("business_type") or "",
                }
                eid = event_id(core)
                events_by_id.setdefault(eid, {
                    "event_id": eid,
                    "at": at,
                    "run_date": run_date,
                    "kind": kind,
                    "issuer_id": issuer_id,
                    "issuer_code": meta["code"],
                    "issuer_name": meta["name"],
                    "store_id": core["store_id"],
                    "name": core["name"],
                    "address": core["address"],
                    "brand_name": core["brand_name"],
                })

        for row in diff.get("changed") or []:
            before = row.get("before") or {}
            after = row.get("after") or {}
            fields = changed_fields(before, after)
            # Brand-label maintenance is not an official store-information change.
            sid = row.get("store_id") or after.get("store_id") or before.get("store_id")
            if sid in (diff.get("brand_reclassified") or []):
                fields = [field for field in fields if field["key"] != "brand_name"]
            if not fields:
                continue
            store = after or before
            core = {
                "issuer_id": issuer_id,
                "kind": "changed",
                "run_date": run_date,
                "store_id": row.get("store_id") or store.get("store_id", ""),
                "fields": fields,
            }
            eid = event_id(core)
            events_by_id.setdefault(eid, {
                "event_id": eid,
                "at": at,
                "run_date": run_date,
                "kind": "changed",
                "issuer_id": issuer_id,
                "issuer_code": meta["code"],
                "issuer_name": meta["name"],
                "store_id": core["store_id"],
                "name": store.get("name", ""),
                "address": store.get("address", ""),
                "brand_name": store.get("brand_name") or store.get("business_type") or "",
                "changed_fields": fields,
            })

events = sorted(
    events_by_id.values(),
    key=lambda e: (e.get("at", ""), e.get("event_id", "")),
    reverse=True,
)

save_json(OUTPUT, {
    "version": 1,
    "generated_at": NOW.isoformat(timespec="seconds"),
    "event_count": len(events),
    "events": events,
})

print(json.dumps({
    "generated_at": NOW.isoformat(timespec="seconds"),
    "event_count": len(events),
}, ensure_ascii=False))
