#!/usr/bin/env python3
import json
import pathlib
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "issuers" / "index.json"

if len(sys.argv) != 2:
    raise SystemExit("usage: check_d1_health.py D1_QUERY_JSON")

def load_wranger(path):
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8").lstrip("\ufeff"))
    return data[0].get("results") or []

rows = load_wranger(sys.argv[1])
by_issuer = {r["issuer_id"]: r for r in rows}
manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
now = datetime.now(timezone.utc)
errors = []

for item in manifest.get("issuers", []):
    if item.get("status") != "public":
        continue
    issuer = item["id"]
    cfg_path = ROOT / str(item["config"]).removeprefix("./")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    health = cfg.get("health") or {}
    row = by_issuer.get(issuer)
    if not row:
        errors.append(f"{issuer}: no D1 state")
        continue

    count = int(row.get("store_count") or 0)
    raw_count = int(row.get("raw_count") or 0)
    lo = int(health.get("minStores", 1))
    hi = int(health.get("maxStores", 10**9))
    if not lo <= count <= hi:
        errors.append(f"{issuer}: D1 count {count} outside {lo}..{hi}")
    if raw_count != count:
        errors.append(f"{issuer}: raw/current mismatch {raw_count}!={count}")

    stamp = str(row.get("updated_at") or "").replace("Z","+00:00")
    try:
        dt = datetime.fromisoformat(stamp)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age = (now - dt.astimezone(timezone.utc)).total_seconds()/86400
        if age > float(health.get("maxAgeDays", 40)):
            errors.append(f"{issuer}: D1 state stale {age:.1f} days")
    except Exception:
        errors.append(f"{issuer}: invalid updated_at {stamp!r}")

    print(f"OK {issuer}: stores={count} raw={raw_count} updated={row.get('updated_at')}")

if errors:
    print("ERRORS")
    for e in errors:
        print("-", e)
    raise SystemExit(1)

print("All public issuers passed D1 state checks.")
