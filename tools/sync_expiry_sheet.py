#!/usr/bin/env python3
"""Import an authenticated Sheets value snapshot without deleting ledger history."""
import argparse
import csv
import json
from datetime import date
from pathlib import Path
from build_expiry import COLUMNS, load_master

HEADERS = ['管理ID','証券コード','会社名','優待名称','期限年','期限月','期限日','期限種別','カテゴリ','利用可能ブランド','公式URL','最終確認日','確認状態','備考','対象発行回','二次情報URL','店舗検索会社ID','検索ブランド','Xアイコン','確認経路']
FIELDS = ['id','code','company_name','benefit_name','year','month','day','expiry_type','category','brands','source_url','checked_on','status','notes','issue','secondary_source_url','issuer_id','search_brand','emoji','verification_method']

def import_values(values, master, checked_on):
    if not values or values[0] != HEADERS:
        raise ValueError('期限DBの列名・順序が違います')
    with master.open(encoding='utf-8-sig',newline='') as handle:
        existing = {row['id']:row for row in csv.DictReader(handle)}
    rows = dict(existing)
    seen=set()
    for raw in values[1:]:
        if not any(raw): continue
        if len(raw)>len(FIELDS): raise ValueError('期限DBの列数が違います')
        item=dict(zip(FIELDS,[str(value) if value is not None else '' for value in raw]+['']*(len(FIELDS)-len(raw))))
        if not item['id'] or item['id'] in seen: raise ValueError('管理IDが空欄または重複しています')
        seen.add(item['id'])
        year,month=int(item.pop('year')),int(item.pop('month'))
        day=item.pop('day')
        item['research_month']=f'{year:04}-{month:02}'
        item['expiry_date']=date(year,month,int(day)).isoformat() if day else ''
        previous=existing.get(item['id'],{})
        if item['status']=='confirmed':
            item['checked_on']=item['checked_on'] or previous.get('checked_on') or checked_on
            item['verification_method']=item['verification_method'] or previous.get('verification_method') or 'user'
        rows[item['id']]={key:item.get(key,'') for key in COLUMNS}
    # Removed/merged sheet records remain historical, never revive old deadlines.
    for record_id in existing.keys() - seen:
        historical_note = 'シートに存在しない履歴行。現行の期限として表示しない。'
        rows[record_id] = {**rows[record_id], 'status':'checking',
            'notes':rows[record_id]['notes'] if historical_note in rows[record_id]['notes']
                else (rows[record_id]['notes']+'／'+historical_note).lstrip('／')}
    temporary=master.with_suffix('.importing.csv')
    try:
        with temporary.open('w',encoding='utf-8',newline='') as out:
            writer=csv.DictWriter(out,fieldnames=COLUMNS,lineterminator='\n');writer.writeheader();writer.writerows(rows.values())
        load_master(temporary)
        temporary.replace(master)
    finally:
        temporary.unlink(missing_ok=True)
    return len(seen)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('snapshot',type=Path,help='Connector get_spreadsheet_range JSON, with values and all rows')
    parser.add_argument('--master',type=Path,default=Path(__file__).resolve().parents[1]/'data/expiry_master.csv')
    parser.add_argument('--checked-on',required=True,help='Snapshot retrieval date in Japan: YYYY-MM-DD')
    args=parser.parse_args();date.fromisoformat(args.checked_on)
    values=json.loads(args.snapshot.read_text())['values']
    print(f'Imported {import_values(values,args.master,args.checked_on)} sheet rows; retained missing historical rows.')
