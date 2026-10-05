"""Build a read-only editor preview from the current ledger; never modify the ledger."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def records():
    with (ROOT / 'data/expiry_master.csv').open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        year, month = row['research_month'].split('-')
        row['research_year'] = year
        row['research_month_number'] = str(int(month))
    return rows


if __name__ == '__main__':
    source = (ROOT / 'tools/google-sheets/Editor.html').read_text()
    payload = json.dumps(records(), ensure_ascii=False).replace('<', '\\u003c')
    source = source.replace('<script>', '<script>window.EXPIRY_PREVIEW_ROWS=' + payload + ';</script><script>', 1)
    (ROOT / 'expiry-editor-preview.html').write_text(source)
    print('Preview built with', len(records()), 'records')
