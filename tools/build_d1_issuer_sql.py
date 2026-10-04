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
    return re.sub(r"[\s・･\-‐-–—ー_]", "", s)


def phone_norm(v):
    return re.sub(r"\D", "", str(v or ""))


def detect_brand(store_name, aliases):
    hay = normalize(store_name)
    matches = [a for a in aliases if normalize(a) and normalize(a) in hay]
    return max(matches, key=lambda x: len(normalize(x))) if matches else ""


def store_id_of(store):
    return str(store.get("store_id") or store.get("official_id") or store.get("id") or "")


def delete_store_rows(issuer, store_id):
    return [
        f"DELETE FROM stores WHERE issuer_id={q(issuer)} AND store_id={q(store_id)};",
        f"DELETE FROM reference_stores WHERE issuer_id={q(issuer)} AND store_id={q(store_id)};",
        f"DELETE FROM store_raw WHERE issuer_id={q(issuer)} AND store_id={q(store_id)};",
    ]


def upsert_store(issuer, store, aliases, categories, generated_at):
    store_id = store_id_of(store)
    if not store_id:
        raise RuntimeError(f"{issuer}: store without id in current snapshot")

    raw = json.dumps(store, ensure_ascii=False, separators=(",", ":"))
    lines = [
        "INSERT INTO store_raw (issuer_id,store_id,raw_json) VALUES ("
        + ",".join([q(issuer), q(store_id), q(raw)])
        + ") ON CONFLICT(issuer_id,store_id) DO UPDATE SET raw_json=excluded.raw_json;"
    ]

    brand = store.get("brand_name") or detect_brand(store.get("name", ""), aliases)
    category = store.get("category") or categories.get(brand) or "restaurant"
    lat = num(store.get("lat", store.get("latitude")))
    lng = num(store.get("lng", store.get("longitude")))

    if lat is not None and lng is not None:
        # A changed row may previously have lived in reference_stores.
        # Delete only the opposite representation; keep the target row and UPSERT it.
        lines.append(
            f"DELETE FROM reference_stores WHERE issuer_id={q(issuer)} AND store_id={q(store_id)};"
        )
        values = [
            q(issuer),
            q(store_id),
            q(store.get("name", "")),
            q(store.get("address", "")),
            q(store.get("phone", "")),
            q(brand),
            q(category),
            str(lat),
            str(lng),
            q(store.get("official_url", store.get("google_map_link", ""))),
            q(generated_at),
        ]
        lines.append(
            "INSERT INTO stores "
            "(issuer_id,store_id,name,address,phone,brand_name,category,lat,lng,official_url,updated_at) "
            "VALUES ("
            + ",".join(values)
            + ") ON CONFLICT(issuer_id,store_id) DO UPDATE SET "
            "name=excluded.name,address=excluded.address,phone=excluded.phone,"
            "brand_name=excluded.brand_name,category=excluded.category,"
            "lat=excluded.lat,lng=excluded.lng,official_url=excluded.official_url,"
            "updated_at=excluded.updated_at;"
        )
    else:
        # A changed row may previously have lived in stores.
        lines.append(
            f"DELETE FROM stores WHERE issuer_id={q(issuer)} AND store_id={q(store_id)};"
        )
        name = store.get("name", "")
        address = store.get("address", "")
        phone = store.get("phone", "")
        values = [
            q(issuer),
            q(store_id),
            q(name),
            q(address),
            q(phone),
            q(normalize(name)),
            q(normalize(address)),
            q(phone_norm(phone)),
            q(brand),
            q(category),
            q(store.get("official_url", store.get("google_map_link", ""))),
            q(generated_at),
        ]
        lines.append(
            "INSERT INTO reference_stores "
            "(issuer_id,store_id,name,address,phone,name_norm,address_norm,phone_norm,brand_name,category,official_url,updated_at) "
            "VALUES ("
            + ",".join(values)
            + ") ON CONFLICT(issuer_id,store_id) DO UPDATE SET "
            "name=excluded.name,address=excluded.address,phone=excluded.phone,"
            "name_norm=excluded.name_norm,address_norm=excluded.address_norm,"
            "phone_norm=excluded.phone_norm,brand_name=excluded.brand_name,"
            "category=excluded.category,official_url=excluded.official_url,"
            "updated_at=excluded.updated_at;"
        )

    return lines


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

current_by_id = {}
for store in stores:
    sid = store_id_of(store)
    if not sid:
        raise SystemExit(f"{issuer}: current snapshot contains a store without id")
    if sid in current_by_id:
        raise SystemExit(f"{issuer}: duplicate current store id: {sid}")
    current_by_id[sid] = store

generated = str(db.get("generated_at") or "").strip()
if not generated:
    generated = datetime.datetime.now(datetime.timezone.utc).isoformat()
run_date = generated[:10]
if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", run_date):
    raise SystemExit(f"{issuer}: invalid generated_at/run date: {generated!r}")

diff_path = current_path.parent / "diffs" / f"{run_date}.json"
if not diff_path.exists():
    raise SystemExit(
        f"{issuer}: diff file missing for incremental D1 sync: {diff_path}. "
        "Refusing to fall back to a full rewrite."
    )

diff = json.loads(diff_path.read_text(encoding="utf-8"))
counts = diff.get("counts") or {}
added_rows = diff.get("added") or []
removed_rows = diff.get("removed") or []
changed_rows = diff.get("changed") or []

try:
    previous_count = int(counts["previous"])
    expected_current = int(counts["current"])
    expected_added = int(counts["added"])
    expected_removed = int(counts["removed"])
    expected_changed = int(counts["changed"])
except (KeyError, TypeError, ValueError) as exc:
    raise SystemExit(f"{issuer}: malformed diff counts in {diff_path}: {exc}")

added_ids = [store_id_of(s) for s in added_rows]
removed_ids = [store_id_of(s) for s in removed_rows]
changed_ids = [str(c.get("store_id") or store_id_of(c.get("after") or {})) for c in changed_rows]

if any(not sid for sid in added_ids + removed_ids + changed_ids):
    raise SystemExit(f"{issuer}: diff contains row(s) without store_id")

if len(added_ids) != expected_added or len(removed_ids) != expected_removed or len(changed_ids) != expected_changed:
    raise SystemExit(
        f"{issuer}: diff list/count mismatch "
        f"added={len(added_ids)}/{expected_added} "
        f"removed={len(removed_ids)}/{expected_removed} "
        f"changed={len(changed_ids)}/{expected_changed}"
    )

if expected_current != len(current_by_id):
    raise SystemExit(
        f"{issuer}: diff/current snapshot mismatch: diff={expected_current} current={len(current_by_id)}"
    )

if previous_count + expected_added - expected_removed != expected_current:
    raise SystemExit(
        f"{issuer}: invalid diff arithmetic: previous={previous_count} "
        f"+ added={expected_added} - removed={expected_removed} != current={expected_current}"
    )

added_set = set(added_ids)
removed_set = set(removed_ids)
changed_set = set(changed_ids)
if len(added_set) != len(added_ids) or len(removed_set) != len(removed_ids) or len(changed_set) != len(changed_ids):
    raise SystemExit(f"{issuer}: duplicate store_id inside diff")
if added_set & removed_set or added_set & changed_set or removed_set & changed_set:
    raise SystemExit(f"{issuer}: overlapping added/removed/changed store ids")

missing_current = sorted((added_set | changed_set) - set(current_by_id))
if missing_current:
    raise SystemExit(f"{issuer}: added/changed ids absent from current snapshot: {missing_current[:10]}")
still_current = sorted(removed_set & set(current_by_id))
if still_current:
    raise SystemExit(f"{issuer}: removed ids still present in current snapshot: {still_current[:10]}")

aliases = config.get("aliases", [])
categories = config.get("categories", {})


lines = [
    "-- Incremental D1 sync generated by tools/build_d1_issuer_sql.py",
    f"-- issuer={issuer} previous={previous_count} current={expected_current} "
    f"added={expected_added} removed={expected_removed} changed={expected_changed}",
]

# Remove only stores that actually disappeared.
for sid in sorted(removed_set):
    lines.extend(delete_store_rows(issuer, sid))

# Insert new stores and UPSERT only stores whose official data changed.
for sid in sorted(added_set | changed_set):
    lines.extend(upsert_store(issuer, current_by_id[sid], aliases, categories, generated))

# Keep issuer-level metadata current. These are the only routine writes when
# there are no store changes.
meta = {k: v for k, v in db.items() if k not in ("stores", "upcoming_stores")}
meta_json = json.dumps(meta, ensure_ascii=False, separators=(",", ":"))
lines.append(
    "INSERT INTO issuer_state (issuer_id,current_meta_json,updated_at) VALUES ("
    + ",".join([q(issuer), q(meta_json), q(generated)])
    + ") ON CONFLICT(issuer_id) DO UPDATE SET "
    "current_meta_json=excluded.current_meta_json,updated_at=excluded.updated_at;"
)

aliases_json = json.dumps(aliases, ensure_ascii=False, separators=(",", ":"))
lines.append(
    "INSERT INTO issuer_search_config (issuer_id,aliases_json,updated_at) VALUES ("
    + ",".join([q(issuer), q(aliases_json), q(generated)])
    + ") ON CONFLICT(issuer_id) DO UPDATE SET "
    "aliases_json=excluded.aliases_json,updated_at=excluded.updated_at;"
)

OUTDIR.mkdir(parents=True, exist_ok=True)
out = OUTDIR / f"sync_{issuer}.sql"
out.write_text("\n".join(lines) + "\n", encoding="utf-8")

print(
    f"{issuer}: incremental sync previous={previous_count} current={expected_current} "
    f"added={expected_added} removed={expected_removed} changed={expected_changed} "
    f"store_writes={expected_added + expected_changed} -> {out.relative_to(ROOT)}"
)
