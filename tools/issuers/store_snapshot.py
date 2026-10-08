"""Write the common private snapshot/diff format used by incremental D1 sync."""
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo


def write_snapshot(issuer, rows, metadata):
    now = datetime.now(ZoneInfo('Asia/Tokyo'))
    stamp, run_date = now.isoformat(timespec='seconds'), now.date().isoformat()
    base = Path('data/issuers') / issuer / 'stores'
    config = json.loads((base.parent / 'config.json').read_text())
    health = config['health']
    if not health['minStores'] <= len(rows) <= health['maxStores']:
        raise ValueError(f'{issuer}: unexpected store count {len(rows)}')
    current = {}
    for row in rows:
        sid = row.get('store_id')
        if not sid or sid in current or not row.get('name') or not row.get('address'):
            raise ValueError(f'{issuer}: incomplete/duplicate official store')
        if urlparse(row.get('official_url', '')).hostname not in health['allowedSourceHosts']:
            raise ValueError(f'{issuer}: unexpected official store source')
        if health.get('requireCoordinates') and ('lat' not in row or 'lng' not in row):
            raise ValueError(f'{issuer}: missing coordinates')
        current[sid] = dict(row)
    previous = json.loads((base / 'current.json').read_text()) if (base / 'current.json').exists() else {'stores': []}
    old = {r['store_id']: r for r in previous['stores']}
    comparable = lambda r: {k: v for k, v in r.items() if k not in {'first_seen', 'last_seen', 'status', 'missing_count'}}
    added, removed = sorted(current.keys() - old.keys()), sorted(old.keys() - current.keys())
    changed = sorted(sid for sid in current.keys() & old.keys() if comparable(current[sid]) != comparable(old[sid]))
    if old:
        if not .8 <= len(current) / len(old) <= 1.5:
            raise ValueError(f'{issuer}: excessive total count change; preserve D1')
        if any(len(ids) > health[key] for ids, key in [(added, 'maxAdded'), (removed, 'maxRemoved'), (changed, 'maxChanged')]):
            raise ValueError(f'{issuer}: excessive store changes; preserve D1')
        for field in health.get('groupFields', []):
            before, after = Counter(r[field] for r in old.values()), Counter(r[field] for r in current.values())
            if any(count >= health.get('minGroupSize', 10) and after[group] < count * .5 for group, count in before.items()):
                raise ValueError(f'{issuer}: group coverage dropped: {field}')
    for sid, row in current.items():
        row.update(first_seen=old.get(sid, {}).get('first_seen') or run_date, last_seen=run_date, status='active')
    snapshot = {**metadata, 'generated_at': stamp, 'eligible_count': len(current),
                'brand_counts': dict(sorted(Counter(r['brand_name'] for r in current.values()).items())),
                'coordinate_count': sum('lat' in r for r in current.values()),
                'reference_count': sum('lat' not in r for r in current.values()),
                'stores': sorted(current.values(), key=lambda r: (r.get('prefecture', ''), r['name'], r['store_id']))}
    diff = {'source': metadata['source'], 'generated_at': stamp, 'run_date': run_date,
            'previous_generated_at': previous.get('generated_at'),
            'counts': {'previous': len(old), 'current': len(current), 'added': len(added), 'removed': len(removed), 'changed': len(changed)},
            'added': [current[s] for s in added], 'removed': [old[s] for s in removed],
            'changed': [{'store_id': s, 'before': old[s], 'after': current[s]} for s in changed]}
    for path, data in [(base / 'current.json', snapshot), (base / 'snapshots' / (run_date + '.json'), snapshot), (base / 'diffs' / (run_date + '.json'), diff)]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    (base / 'last_diff.md').write_text(f"# {config['name']} 店舗差分 {run_date}\n\n対象店舗: {len(current)}\n追加: {len(added)} / 消失: {len(removed)} / 変更: {len(changed)}\n")
    print(json.dumps({'issuer': issuer, **diff['counts'], 'coordinates': snapshot['coordinate_count'], 'references': snapshot['reference_count']}, ensure_ascii=False))
