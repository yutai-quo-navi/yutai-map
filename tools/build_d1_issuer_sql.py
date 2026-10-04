#!/usr/bin/env python3
import datetime
import json
import pathlib
import re
import sys
import unicodedata

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTDIR = ROOT / "cloudflare" / "generated"

def q(v):
    return "'" + str(v if v is not None else "").replace("'", "''") + "'"

def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def normalize(v):
    s = unicodedata.normalize("NFKC", str(v or "")).lower()
    return re.sub(r"[\s・･\-‐‑–—ー_]", "", s)

def phone_norm(v):
    return re.sub(r"\D", "", str(v or ""))

def detect_brand(store_name, aliases):
    hay = normalize(store_name)
    matches = [a for a in aliases if normalize(a) and normalize(a) in hay]
    return max(matches, key=lambda x: len(normalize(x))) if matches else ""

if len(sys.argv) != 2:
    raise SystemExit("usage: build_d1_issuer_sql.py ISSUER")

issuer = sys.argv[1]
config_path = ROOT / "data" / "issuers" / issuer / "config.json"
if not config_path.exists():
    raise SystemExit(f"missing config: {config_path}")

config = json.loads(config_path.read_text(encoding="utf-8"))
rel = config.get("storeDataPath")
if not rel:
    raise SystemExit(f"{issuer}: no storeDataPath")

current_path = ROOT / str(rel).removeprefix("./")
if not current_path.exists():
    raise SystemExit(f"{issuer}: generated current DB missing: {current_path}")

db = json.loads(current_path.read_text(encoding="utf-8"))
stores = db.get("stores") or []
if not stores:
    raise SystemExit(f"{issuer}: generated store DB is empty")

aliases = config.get("aliases", [])
categories = config.get("categories", {})
generated = db.get("generated_at", "")
now = datetime.datetime.now(datetime.timezone.utc).isoformat()

lines = [
    f"DELETE FROM stores WHERE issuer_id={q(issuer)};",
    f"DELETE FROM reference_stores WHERE issuer_id={q(issuer)};",
    f"DELETE FROM store_raw WHERE issuer_id={q(issuer)};",
    f"DELETE FROM issuer_state WHERE issuer_id={q(issuer)};",
    f"DELETE FROM issuer_search_config WHERE issuer_id={q(issuer)};",
]

geo_count = 0
ref_count = 0
raw_count = 0

for s in stores:
    store_id = str(s.get("store_id") or s.get("official_id") or s.get("id") or "")
    if not store_id:
        continue

    raw = json.dumps(s, ensure_ascii=False, separators=(",",":"))
    lines.append(
        "INSERT INTO store_raw (issuer_id,store_id,raw_json) VALUES ("
        + ",".join([q(issuer),q(store_id),q(raw)]) + ");"
    )
    raw_count += 1

    brand = s.get("brand_name") or detect_brand(s.get("name",""), aliases)
    category = s.get("category") or categories.get(brand) or "restaurant"
    lat = num(s.get("lat", s.get("latitude")))
    lng = num(s.get("lng", s.get("longitude")))

    if lat is not None and lng is not None:
        values = [
            q(issuer), q(store_id), q(s.get("name","")), q(s.get("address","")),
            q(s.get("phone","")), q(brand), q(category), str(lat), str(lng),
            q(s.get("official_url", s.get("google_map_link",""))), q(generated or now),
        ]
        lines.append(
            "INSERT INTO stores "
            "(issuer_id,store_id,name,address,phone,brand_name,category,lat,lng,official_url,updated_at) "
            "VALUES (" + ",".join(values) + ");"
        )
        geo_count += 1
    else:
        name = s.get("name","")
        address = s.get("address","")
        phone = s.get("phone","")
        values = [
            q(issuer), q(store_id), q(name), q(address), q(phone),
            q(normalize(name)), q(normalize(address)), q(phone_norm(phone)),
            q(brand), q(category),
            q(s.get("official_url", s.get("google_map_link",""))), q(generated or now),
        ]
        lines.append(
            "INSERT INTO reference_stores "
            "(issuer_id,store_id,name,address,phone,name_norm,address_norm,phone_norm,brand_name,category,official_url,updated_at) "
            "VALUES (" + ",".join(values) + ");"
        )
        ref_count += 1

meta = {k:v for k,v in db.items() if k not in ("stores","upcoming_stores")}
meta_json = json.dumps(meta, ensure_ascii=False, separators=(",",":"))
lines.append(
    "INSERT INTO issuer_state (issuer_id,current_meta_json,updated_at) VALUES ("
    + ",".join([q(issuer),q(meta_json),q(generated or now)]) + ");"
)

aliases_json = json.dumps(aliases, ensure_ascii=False, separators=(",",":"))
lines.append(
    "INSERT INTO issuer_search_config (issuer_id,aliases_json,updated_at) VALUES ("
    + ",".join([q(issuer),q(aliases_json),q(generated or now)]) + ");"
)

OUTDIR.mkdir(parents=True, exist_ok=True)
out = OUTDIR / f"sync_{issuer}.sql"
out.write_text("\n".join(lines)+"\n", encoding="utf-8")
print(f"{issuer}: raw={raw_count} geo={geo_count} reference={ref_count} -> {out.relative_to(ROOT)}")
