#!/usr/bin/env python3
import json
import pathlib
import glob
import sys

if len(sys.argv) != 4:
    raise SystemExit("usage: restore_d1_state.py ISSUER RAW_ROWS_JSON META_JSON")

issuer = sys.argv[1]
raw_rows_pattern = sys.argv[2]
meta_path = pathlib.Path(sys.argv[3])

def load_wranger_json(path):
    text = path.read_text(encoding="utf-8").lstrip("\ufeff").strip()
    data = json.loads(text)
    if not isinstance(data, list) or not data:
        return []
    return data[0].get("results") or []

raw_rows = []
for name in sorted(glob.glob(raw_rows_pattern)):
    raw_rows.extend(load_wranger_json(pathlib.Path(name)))
meta_rows = load_wranger_json(meta_path)

stores = []
for row in raw_rows:
    raw = row.get("raw_json")
    if not raw:
        continue
    store = json.loads(raw)
    if isinstance(store, dict):
        stores.append(store)

meta = {}
if meta_rows:
    raw_meta = meta_rows[0].get("current_meta_json") or "{}"
    meta = json.loads(raw_meta)

current = dict(meta)
# Incremental D1 sync intentionally does not rewrite unchanged store_raw rows.
# All stores present in store_raw were seen in the previous successful snapshot,
# so reconstruct their volatile last_seen/status from issuer_state.generated_at.
previous_run_date = str(current.get("generated_at", ""))[:10]
for store in stores:
    if previous_run_date:
        store["last_seen"] = previous_run_date
    store["status"] = "active"
current["stores"] = stores

base = pathlib.Path("data/issuers") / issuer / "stores"
base.mkdir(parents=True, exist_ok=True)

(base / "current.json").write_text(
    json.dumps(current, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)

history_stores = {}
for store in stores:
    sid = str(store.get("store_id") or store.get("official_id") or store.get("id") or "")
    if not sid:
        continue
    h = dict(store)
    h.setdefault("first_seen", store.get("first_seen") or "")
    h["last_seen"] = previous_run_date or store.get("last_seen") or ""
    h["missing_count"] = 0
    h["status"] = "active"
    history_stores[sid] = h

history = {
    "updated_at": current.get("generated_at", ""),
    "run_date": str(current.get("generated_at", ""))[:10],
    "stores": history_stores,
}
(base / "history.json").write_text(
    json.dumps(history, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)

print(f"restored {issuer}: {len(stores)} stores")
