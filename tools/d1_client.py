"""Run locked Wrangler without printing private rows; collect D1 operation metadata."""
import json
import os
import pathlib
import re
import subprocess

DATABASE = '4540cbaa-3214-4111-9c7a-11e18fd067db'
ROOT = pathlib.Path(__file__).resolve().parents[1]


def issuer_id(value):
    if not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', value):
        raise ValueError('Invalid issuer ID')
    if not (ROOT / 'data' / 'issuers' / value / 'config.json').is_file():
        raise ValueError('Missing issuer config')
    return value


def execute(*args):
    output = subprocess.check_output(['npx', 'wrangler', 'd1', 'execute', DATABASE,
                                      '--remote', '--json', *args], text=True)
    data = json.loads(output)
    if not isinstance(data, list) or not data or any(x.get('success') is False for x in data):
        raise RuntimeError('D1 operation failed or returned an invalid response')
    return data


def usage(label, data):
    record = {'operation': label,
              'rows_read': sum(int(x.get('meta', {}).get('rows_read', 0)) for x in data),
              'rows_written': sum(int(x.get('meta', {}).get('rows_written', 0)) for x in data)}
    print(json.dumps(record))
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a') as f:
            f.write(f"- {label}: read={record['rows_read']:,}, write={record['rows_written']:,}\n")
    return record
