#!/usr/bin/env python3
"""Restore one issuer with keyset pagination, stopping after the final page."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from d1_client import execute, issuer_id, usage


def read_snapshot(issuer, query, page_size=500):
    rows, metadata, cursor = [], [], None
    while True:
        after = " AND store_id>'" + cursor.replace("'", "''") + "'" if cursor is not None else ''
        result = query(f"SELECT store_id,raw_json FROM store_raw WHERE issuer_id='{issuer}'{after} ORDER BY store_id LIMIT {page_size};")
        metadata.extend(result)
        page = result[0].get('results', [])
        if any(not isinstance(x.get('store_id'), str) for x in page):
            raise ValueError('Missing store ID in D1 page')
        ids = [x['store_id'] for x in page]
        if ids != sorted(set(ids)) or (cursor is not None and ids and ids[0] <= cursor):
            raise ValueError('D1 cursor did not advance')
        rows.extend(page)
        if len(page) < page_size:
            break
        cursor = ids[-1]
    meta = query(f"SELECT current_meta_json FROM issuer_state WHERE issuer_id='{issuer}';")
    metadata.extend(meta)
    return rows, meta, metadata


def main():
    issuer = issuer_id(sys.argv[1])
    rows, meta, metadata = read_snapshot(issuer, lambda sql: execute('--command', sql))
    usage('restore:' + issuer, metadata)
    with tempfile.TemporaryDirectory(prefix='d1-restore-') as folder:
        folder = Path(folder)
        (folder / 'raw.json').write_text(json.dumps([{'results': rows}]))
        (folder / 'meta.json').write_text(json.dumps(meta))
        subprocess.run([sys.executable, 'tools/restore_d1_state.py', issuer,
                        str(folder / 'raw.json'), str(folder / 'meta.json')], check=True)


if __name__ == '__main__':
    main()
