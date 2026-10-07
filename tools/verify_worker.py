#!/usr/bin/env python3
"""Verify the public API or its country denial plus authenticated D1 state."""
import argparse
import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://yutai-map-api.yutaisamurai.workers.dev'
DATABASE = '4540cbaa-3214-4111-9c7a-11e18fd067db'
REQUIRED = {'yoshinoya': (5, []), 'toridoll': (10, ['丸亀製麺', 'コナズ珈琲']),
            'matsuya': (2, ['松屋', '松のや']), 'zensho': (1, []), 'colowide': (1, [])}

class CountryBlocked(Exception):
    pass

def fetch_public(path):
    try:
        with urllib.request.urlopen(BASE + path, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 403:
            try:
                data = json.load(error)
            except (ValueError, TypeError):
                raise error
            if data.get('error') == 'country_not_allowed':
                raise CountryBlocked() from error
        raise

def query_d1(sql):
    output = subprocess.check_output(['npx', 'wrangler', 'd1', 'execute', DATABASE,
                                      '--remote', '--command', sql, '--json'], text=True, timeout=60)
    groups = json.loads(output)
    if not groups or any(group.get('success') is False for group in groups):
        raise RuntimeError('D1 query failed')
    return [row for group in groups for row in group.get('results', [])]

def validate_brands(issuer, names):
    minimum, required = REQUIRED[issuer]
    if len(names) < minimum or not set(required).issubset(names):
        raise RuntimeError('Required eligible brands are missing for ' + issuer)

def verify_private(issuer=None):
    if issuer is None:
        row = query_d1('SELECT (SELECT COUNT(*) FROM stores) AS geo_count, '
                       '(SELECT COUNT(*) FROM reference_stores) AS reference_count;')[0]
        if int(row['geo_count']) <= 0 or int(row['reference_count']) <= 0:
            raise RuntimeError('D1 health counts are empty')
        print('Authenticated D1 health verified')
        return
    if issuer not in REQUIRED:
        raise ValueError('Unsupported issuer')
    row = query_d1(f"SELECT (SELECT COUNT(*) FROM stores WHERE issuer_id='{issuer}') + "
                   f"(SELECT COUNT(*) FROM reference_stores WHERE issuer_id='{issuer}') AS store_count, "
                   f"(SELECT COUNT(*) FROM store_raw WHERE issuer_id='{issuer}') AS raw_count;")[0]
    count = int(row['store_count'])
    config = json.loads((ROOT / 'data' / 'issuers' / issuer / 'config.json').read_text())
    health = config.get('health', {})
    if not int(health.get('minStores', 1)) <= count <= int(health.get('maxStores', 10**9)) or int(row['raw_count']) != count:
        raise RuntimeError('D1 issuer counts are inconsistent for ' + issuer)
    names = {row['brand_name'] for row in query_d1(
        f"SELECT DISTINCT brand_name FROM (SELECT brand_name FROM stores WHERE issuer_id='{issuer}' "
        f"UNION ALL SELECT brand_name FROM reference_stores WHERE issuer_id='{issuer}') WHERE brand_name != '';"
    )}
    validate_brands(issuer, names)
    print('Authenticated D1 issuer and brand counts verified:', issuer, count)

def verify(issuer=None):
    try:
        if issuer is None:
            data = fetch_public('/health')
            if not data.get('ok') or int(data.get('stores', 0)) <= 0 or int(data.get('referenceStores', 0)) <= 0:
                raise RuntimeError('Public API health failed')
        else:
            if issuer not in REQUIRED:
                raise ValueError('Unsupported issuer')
            locations = [(35.6812, 139.7671)]
            if issuer in ['yoshinoya', 'toridoll', 'matsuya']:
                locations.append((43.0618, 141.3545))
            for lat, lng in locations:
                params = urllib.parse.urlencode(dict(lat=lat, lng=lng, radius=10000, issuers=issuer))
                data = fetch_public('/v1/stores/search?' + params)
                if int(data.get('count', 0)) <= 0 or not all(store['issuer_id'] == issuer for store in data['results']):
                    raise RuntimeError('Eligible store search failed for ' + issuer)
            brands = fetch_public('/v1/brands?issuers=' + issuer)
            validate_brands(issuer, {brand['name'] for brand in brands['brands']})
        print('Public API verified:', issuer or 'health')
    except CountryBlocked:
        print('Public API correctly denied this runner country; verifying authenticated D1 instead. Japanese public search was not exercised.')
        verify_private(issuer)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--issuer', choices=sorted(REQUIRED))
    args = parser.parse_args()
    verify(args.issuer)
