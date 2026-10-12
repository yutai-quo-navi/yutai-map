"""Refuse promotion if D1 counts differ from either validated official snapshot."""
import json
import sys
from pathlib import Path

def verify(data, issuers=None):
    if not data or any(x.get('success') is not True for x in data):
        raise ValueError('D1 query failed')
    rows = {r['issuer_id']:r for result in data for r in result.get('results',[])}
    for issuer in (issuers or ['yamaokaya','chikaranomoto']):
        snapshot = json.loads(Path(f'data/issuers/{issuer}/stores/current.json').read_text())
        row=rows.get(issuer,{})
        if row.get('geo_count') != len(snapshot['stores']) or row.get('reference_count') != 0:
            raise ValueError(f'{issuer}: D1 snapshot/count mismatch')
        print(f'{issuer}: verified {row["geo_count"]} official coordinates in D1')

if __name__=='__main__':verify(json.loads(Path(sys.argv[1]).read_text()))
