#!/usr/bin/env python3
"""Add/correct an expiry record with a code and year/month; regenerate JSON."""
import argparse
import csv
import json
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from build_expiry import ROOT, COLUMNS, STATUSES, TYPES, CATEGORIES, load_master, month, iso_date, public_document


def select_record(rows, code, target_month, record_id=None, benefit=None, expiry_type=None):
    if record_id:
        matches = [r for r in rows if r['id'] == record_id and r['code'] == code]
        if len(matches) != 1:
            raise ValueError('指定idと証券コードに一致する行がありません')
        if matches[0]['research_month'][:4] != target_month[:4]:
            raise ValueError('別年分は新規追加してください。前年行は変更しません')
        return matches[0]
    matches = [r for r in rows if r['code'] == code and r['research_month'][:4] == target_month[:4]
               and (not benefit or r['benefit_name'] == benefit) and (not expiry_type or r['expiry_type'] == expiry_type)]
    exact = [r for r in matches if r['research_month'] == target_month]
    candidates = exact or matches
    if len(candidates) > 1:
        raise ValueError('同年の候補が複数あります。--idで対象券を選択: ' + ', '.join(r['id'] for r in candidates))
    return candidates[0] if candidates else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--code', required=True)
    period = parser.add_mutually_exclusive_group(required=True)
    period.add_argument('--month', help='年必須 YYYY-MM。日付未指定の月情報として記録')
    period.add_argument('--date', help='年必須 YYYY-MM-DD')
    parser.add_argument('--id', help='同年に券が複数あるときの訂正対象')
    parser.add_argument('--new', action='store_true', help='同年の別の券を新規追加')
    parser.add_argument('--company')
    parser.add_argument('--benefit')
    parser.add_argument('--issue')
    parser.add_argument('--type', choices=sorted(TYPES))
    parser.add_argument('--category', choices=CATEGORIES)
    parser.add_argument('--source')
    parser.add_argument('--notes')
    parser.add_argument('--status', choices=sorted(STATUSES), default='confirmed')
    args = parser.parse_args()
    args.code = unicodedata.normalize('NFKC', args.code).upper()
    if args.new and args.id:
        parser.error('--newと--idは併用できません')
    target = month(args.month) if args.month else iso_date(args.date)[:7]
    rows = load_master(ROOT / 'data/expiry_master.csv')
    try:
        existing = None if args.new else select_record(rows, args.code, target, args.id, args.benefit, args.type)
    except ValueError as e:
        parser.error(str(e))
    today = datetime.now(ZoneInfo('Asia/Tokyo')).date().isoformat()
    if existing:
        row = dict(existing)
    else:
        row = dict.fromkeys(COLUMNS, '')
        previous = next((r for r in reversed(rows) if r['code'] == args.code), None)
        manifest = json.loads((ROOT / 'data/issuers/index.json').read_text())['issuers']
        issuer = next((v for v in manifest if v['code'] == args.code), None)
        name = args.company or (previous or {}).get('company_name') or (issuer or {}).get('name')
        if not name:
            parser.error('初めての会社は--companyで会社名を指定してください')
        number = 1
        prefix = f'{args.code}-{target}'
        while any(r['id'] == f'{prefix}-{number}' for r in rows):
            number += 1
        row.update(id=f'{prefix}-{number}', code=args.code, company_name=name,
                   benefit_name=args.benefit or (previous or {}).get('benefit_name') or '株主優待券',
                   expiry_type=args.type or (previous or {}).get('expiry_type') or '利用期限',
                   category=args.category or (previous or {}).get('category') or 'other',
                   issuer_id=(issuer or {}).get('id', ''))
    row.update(research_month=target, expiry_date=args.date or '', status=args.status,
               checked_on=today, verification_method='user' if args.status == 'confirmed' else '')
    for arg, column in [('company','company_name'),('benefit','benefit_name'),('issue','issue'),('type','expiry_type'),('category','category'),('source','source_url'),('notes','notes')]:
        if getattr(args, arg) is not None:
            row[column] = getattr(args, arg)
    updated = [r for r in rows if r['id'] != row['id']] + [row]
    master = ROOT / 'data/expiry_master.csv'
    # Validate before replacing either deliverable. Keep a stable row id on corrections.
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='', suffix='.csv', dir=master.parent, delete=False) as f:
        tmp = Path(f.name)
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator='\n')
        writer.writeheader()
        writer.writerows({**r, 'brands': '|'.join(r['brands']) if isinstance(r['brands'], list) else r['brands']} for r in updated)
    try:
        validated = load_master(tmp)
        tmp.replace(master)
        (ROOT / 'data/expiry.json').write_text(json.dumps(public_document(validated),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    finally:
        tmp.unlink(missing_ok=True)
    print(('訂正' if existing else '追加') + f": {row['id']} / {row['company_name']} / {args.date or target} / {args.status}")


if __name__ == '__main__':
    main()
