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


def parse_output(output):
    # Wrangler bulk imports can print progress before their JSON result.
    # Read only a complete result array; never treat progress as success.
    decoder = json.JSONDecoder()
    for match in re.finditer(r'^\s*\[', output, flags=re.MULTILINE):
        try:
            data, _ = decoder.raw_decode(output[match.start():].lstrip())
        except json.JSONDecodeError:
            continue
        if isinstance(data, list) and data and all(isinstance(x, dict) and x.get('success') is True and isinstance(x.get('meta'), dict) for x in data):
            return data
    raise RuntimeError('D1 operation did not return a successful JSON result')


def execute(*args):
    output = subprocess.check_output(['npx', 'wrangler', 'd1', 'execute', DATABASE,
                                      '--remote', '--json', *args], text=True)
    data = parse_output(output)
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
