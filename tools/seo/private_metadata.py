"""Publish public-only metadata from privately maintained issuer state.

No collector, store snapshot, SQL generator or D1 write runs here.
"""
import json
from datetime import datetime

ISSUERS = ('zensho',)
EVENT_FIELDS = {
    'event_id', 'at', 'run_date', 'kind', 'issuer_id', 'issuer_code',
    'issuer_name', 'store_id', 'name', 'address', 'brand_name', 'changed_fields',
}
CHANGE_KEYS = {
    'name', 'brand_name', 'business_type', 'category', 'branch_name', 'address',
    'prefecture', 'postal_code', 'phone', 'lat', 'lng', 'open_date', 'close_date',
    'benefits', 'benefit_status', 'official_url',
}


def validate_release(issuer, release):
    if set(release) != {'version', 'issuer_id', 'generated_at', 'brands', 'events'}:
        raise ValueError('Unexpected public release fields')
    if release['version'] != 1 or release['issuer_id'] != issuer:
        raise ValueError('Unexpected public release issuer/version')
    datetime.fromisoformat(release['generated_at'])
    brands = release['brands']
    if set(brands) != {'source', 'generated_at', 'eligible_filter', 'brands'}:
        raise ValueError('Unexpected public brand fields')
    if brands['eligible_filter'] != 'shareholder_coupon' or brands['generated_at'] != release['generated_at']:
        raise ValueError('Unverified or stale public brand metadata')
    seen = set()
    for row in brands['brands']:
        if set(row) != {'name', 'eligible_store_count'} or not isinstance(row['name'], str) or not row['name'] or row['name'] in seen:
            raise ValueError('Invalid public brand row')
        if type(row['eligible_store_count']) is not int or row['eligible_store_count'] <= 0:
            raise ValueError('Invalid public brand count')
        seen.add(row['name'])
    for event in release['events']:
        if set(event) - EVENT_FIELDS or event.get('issuer_id') != issuer or not event.get('event_id'):
            raise ValueError('Invalid or foreign public change event')
        if event.get('kind') not in {'added', 'removed', 'changed'}:
            raise ValueError('Unknown public change event kind')
        for field in event.get('changed_fields', []):
            if set(field) != {'key', 'label', 'before', 'after'} or field['key'] not in CHANGE_KEYS:
                raise ValueError('Private/unexpected field in public change event')
    return release


def publish_private_metadata(root, query):
    updates_path = root / 'data/updates.json'
    updates = json.loads(updates_path.read_text())
    events = {e['event_id']: e for e in updates.get('events', [])}
    writes = {}
    latest_at = updates.get('generated_at', '')
    for issuer in ISSUERS:
        rows = query('SELECT current_meta_json FROM issuer_state WHERE issuer_id=?', [issuer])
        if not rows:
            continue
        release = json.loads(rows[0]['current_meta_json']).get('public_release')
        if not release:
            continue  # Pre-cutover state remains usable while private sync is tested.
        validate_release(issuer, release)
        brands_path = root / f'data/issuers/{issuer}/brands.json'
        existing = json.loads(brands_path.read_text()) if brands_path.exists() else {}
        if existing.get('generated_at') and datetime.fromisoformat(existing['generated_at']) > datetime.fromisoformat(release['generated_at']):
            continue  # Never publish an older snapshot over a newer public one.
        writes[brands_path] = release['brands']
        for event in release['events']:
            old = events.get(event['event_id'])
            if old is not None and old != event:
                raise ValueError('Conflicting public event identity')
            events[event['event_id']] = event
        latest_at = max(latest_at, release['generated_at'])
    if len(events) != len(updates.get('events', [])):
        updates['events'] = sorted(events.values(), key=lambda e: (e.get('at', ''), e['event_id']), reverse=True)
        updates['event_count'] = len(events)
        updates['generated_at'] = latest_at
        writes[updates_path] = updates
    # All releases are validated before any publication file changes.
    for path, data in writes.items():
        content = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
        if not path.exists() or path.read_text() != content:
            path.write_text(content)
    return len(writes)
