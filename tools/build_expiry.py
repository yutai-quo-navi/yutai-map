#!/usr/bin/env python3
"""Validate the editable expiry ledger; generate public JSON and human-editable X drafts."""
import argparse
import calendar
import csv
import io
import json
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
COLUMNS = ['id', 'code', 'company_name', 'benefit_name', 'issue', 'expiry_date',
           'research_month', 'expiry_type', 'category', 'brands', 'source_url',
           'secondary_source_url', 'checked_on', 'status', 'notes', 'issuer_id',
           'search_brand', 'emoji', 'verification_method']
TYPES = {'利用期限', '申込期限', '登録期限', '予約期限', 'ポイント失効', '交換期限', '受取期限'}
CATEGORIES = {'dining': '外食・飲食系', 'shopping': '買物・割引系',
              'leisure': 'サービス・レジャー系', 'catalog': 'カタログ・申込期限', 'other': 'その他'}
STATUSES = {'confirmed', 'secondary', 'checking'}


def iso_date(value):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError(f'日付は YYYY-MM-DD: {value}')
    date.fromisoformat(value)
    return value


def month(value):
    if not re.fullmatch(r'\d{4}-\d{2}', value):
        raise ValueError(f'月は YYYY-MM: {value}')
    date.fromisoformat(value + '-01')
    return value


def load_master(path, manifest_path=ROOT / 'data/issuers/index.json', allow_legacy=False):
    issuers = {v['id']: v for v in json.loads(manifest_path.read_text())['issuers']}
    # Manual features share voucher deadlines, but never join store scraping/sync.
    feature_path = ROOT / 'data/features/index.json'
    if feature_path.exists():
        for feature in json.loads(feature_path.read_text())['features']:
            issuer = feature['issuer']
            if issuer['id'] in issuers and issuers[issuer['id']]['code'] != issuer['code']:
                raise ValueError('特集の会社IDと証券コードが不一致')
            issuers.setdefault(issuer['id'], issuer)
    rows, ids, keys = [], set(), set()
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        legacy = allow_legacy and reader.fieldnames == COLUMNS[:-1]
        if reader.fieldnames != COLUMNS and not legacy:
            raise ValueError('CSV列・順序が違います: ' + ','.join(COLUMNS))
        for line, raw in enumerate(reader, 2):
            try:
                if None in raw or any(v is None for v in raw.values()):
                    raise ValueError('列数が違います')
                if legacy:
                    raw['verification_method'] = 'official' if raw['status'] == 'confirmed' else ''
                row = {k: unicodedata.normalize('NFC', v).strip() for k, v in raw.items()}
                row['code'] = unicodedata.normalize('NFKC', row['code']).upper()
                if not re.fullmatch(r'[0-9]{3}[0-9A-Z]', row['code']):
                    raise ValueError('証券コードが不正')
                if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', row['id']) or row['id'] in ids:
                    raise ValueError('idが不正または重複')
                if not row['company_name'] or not row['benefit_name']:
                    raise ValueError('会社名と優待名称は必須')
                if row['status'] not in STATUSES or row['category'] not in CATEGORIES or row['expiry_type'] not in TYPES:
                    raise ValueError('確認状態・カテゴリ・期限種別が不正')
                if row['expiry_date']:
                    iso_date(row['expiry_date'])
                month(row['research_month'])
                if row['expiry_date'] and row['expiry_date'][:7] != row['research_month']:
                    raise ValueError('期限日と調査対象月が不一致（訂正時は両方更新）')
                if row['checked_on']:
                    iso_date(row['checked_on'])
                for field in ['source_url', 'secondary_source_url']:
                    if row[field] and (urlparse(row[field]).scheme not in {'https', 'http'} or not urlparse(row[field]).netloc):
                        raise ValueError(f'{field}はhttp(s) URL')
                if row['verification_method'] not in {'', 'official', 'user'}:
                    raise ValueError('確認経路はofficial / user / 空欄')
                if row['status'] == 'confirmed':
                    if not row['checked_on'] or not row['verification_method']:
                        raise ValueError('confirmedは確認日と確認経路が必須')
                    if row['verification_method'] == 'official' and not all(row[k] for k in ['expiry_date', 'source_url', 'issue']):
                        raise ValueError('公式確認済みは期限日・公式URL・対象発行回が必須')
                if row['status'] == 'secondary' and not row['secondary_source_url']:
                    raise ValueError('secondaryは二次情報URLが必須')
                if row['issuer_id']:
                    if row['issuer_id'] not in issuers or issuers[row['issuer_id']]['code'] != row['code']:
                        raise ValueError('店舗検索の会社IDと証券コードが不一致')
                if row['search_brand'] and not row['issuer_id']:
                    raise ValueError('ブランド検索には会社IDが必要')
                row['brands'] = list(dict.fromkeys(b.strip() for b in row['brands'].split('|') if b.strip()))
                if row['search_brand'] and row['search_brand'] not in row['brands']:
                    raise ValueError('検索ブランドは利用可能ブランドにも記載')
                key = (row['code'], row['benefit_name'], row['issue'], row['expiry_type'], row['expiry_date'] or row['research_month'])
                if key in keys:
                    raise ValueError('同じ優待・発行回・期限の重複')
                ids.add(row['id']); keys.add(key); rows.append(row)
            except ValueError as exc:
                raise ValueError(f'{path}:{line}: {exc}') from exc
    return sorted(rows, key=lambda r: (r['expiry_date'] or r['research_month'] + '-99', r['code'], r['id']))


def public_document(rows):
    # Keep historical confirmed entries too. The client computes the current month in JST.
    return {'version': 1, 'timezone': 'Asia/Tokyo',
            'entries': [{**r, 'expiry_year': int(r['research_month'][:4])} for r in rows if r['status'] == 'confirmed']}


def x_draft(rows, target_month, month_end=False):
    month(target_month)
    last_day = calendar.monthrange(int(target_month[:4]), int(target_month[5:]))[1]
    entries = [r for r in rows if r['status'] == 'confirmed' and r['research_month'] == target_month
               and (not month_end or r['expiry_date'].endswith(f'-{last_day:02}'))]
    heading = f'⚠️{int(target_month[5:])}月' + ('末' if month_end else '') + ' 期限優待まとめ'
    lines = [heading, '', 'お持ちの方はぜひ確認推奨👇']
    for cat, label in CATEGORIES.items():
        group = [r for r in entries if r['category'] == cat]
        if group:
            lines += ['', '◇' + label]
            for r in group:
                d = date.fromisoformat(r['expiry_date']) if r['expiry_date'] else None
                deadline = f'{d.month}/{d.day}' if d else f'{int(target_month[5:])}月（日付未登録）'
                lines.append(f"{r['emoji'] or '🎁'} {r['code']} {r['company_name']} {r['benefit_name']} / {deadline} {r['expiry_type']}" + (f" / {r['issue']}" if r['issue'] else ''))
    if not entries:
        lines += ['', '確認済みの期限情報はまだありません']
    return '\n'.join(lines) + '\n'


def candidates(rows, target_month):
    month(target_month)
    prior = f'{int(target_month[:4]) - 1:04}{target_month[4:]}'
    # Historical candidates are never rolled forward as confirmed facts.
    selected = [r for r in rows if r['research_month'] == prior]
    out = io.StringIO(newline='')
    writer = csv.writer(out)
    writer.writerow(['code', 'company_name', 'benefit_name', 'prior_issue', 'prior_expiry_date', 'prior_status', 'source_url', 'notes'])
    for r in selected:
        writer.writerow([r['code'], r['company_name'], r['benefit_name'], r['issue'], r['expiry_date'], r['status'], r['source_url'], r['notes']])
    return out.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--master', type=Path, default=ROOT / 'data/expiry_master.csv')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/expiry.json')
    parser.add_argument('--month', default=datetime.now(ZoneInfo('Asia/Tokyo')).strftime('%Y-%m'))
    parser.add_argument('--draft', type=Path, help='X初稿の保存先。省略時は標準出力')
    parser.add_argument('--month-end', action='store_true', help='月末日が期限の優待だけでX初稿を生成')
    parser.add_argument('--candidates', type=Path, help='前年同月の調査候補CSVを出力')
    parser.add_argument('--check', action='store_true', help='JSONがCSVと一致するか検証（書き込みなし）')
    parser.add_argument('--baseline', type=Path, help='旧CSVとの比較で履歴行の削除を検出')
    args = parser.parse_args()
    rows = load_master(args.master)
    if args.baseline:
        previous = load_master(args.baseline, allow_legacy=True)
        removed = {r['id'] for r in previous} - {r['id'] for r in rows}
        if removed:
            parser.error('履歴行は削除不可。訂正は同じidを編集: ' + ', '.join(sorted(removed)))
    data = json.dumps(public_document(rows), ensure_ascii=False, indent=2) + '\n'
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding='utf-8') != data:
            parser.error('expiry.jsonが原本と不一致。python tools/build_expiry.py を実行してください')
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(data, encoding='utf-8')
    if args.candidates:
        args.candidates.write_text(candidates(rows, args.month), encoding='utf-8-sig')
    draft = x_draft(rows, args.month, args.month_end)
    if args.draft:
        args.draft.write_text(draft, encoding='utf-8')
    else:
        print(draft, end='')


if __name__ == '__main__':
    main()
