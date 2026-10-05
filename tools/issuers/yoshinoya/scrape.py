"""Import only the official eligible-store subset, keeping full DB private in D1."""
import json
import re
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

SITE = 'https://stores.yoshinoya-holdings.com/yoshinoya-holdings'
SEARCH_PAGE = SITE + '/spot/list?c_d1=1'
API_BASE = SITE + '/api/proxy2/shop/list'
BASE = Path('data/issuers/yoshinoya/stores')
CURRENT = BASE / 'current.json'
HISTORY = BASE / 'history.json'
SUMMARY = BASE / 'last_diff.md'
NOW = datetime.now(timezone(timedelta(hours=9)))
RUN_DATE = NOW.strftime('%Y-%m-%d')
GENERATED_AT = NOW.isoformat(timespec='seconds')
SNAPSHOT = BASE / 'snapshots' / f'{RUN_DATE}.json'
DIFF = BASE / 'diffs' / f'{RUN_DATE}.json'


def load_json(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 yutai-map/1.0 (+https://github.com/yutai-quo-navi/yutai-map)','Accept':'application/json,text/html'})
    with urllib.request.urlopen(req,timeout=90) as response:
        return response.read().decode('utf-8','replace')


html=get(SEARCH_PAGE)
if '株主優待券が利用できる' not in html:
    raise RuntimeError('Official eligible-store page title changed')
# Follow the public search page's own defaults, including unpublished/closed flags.
match=re.search(r'addDefaultCondition\((\{.*?\}),\s*navitimeModalMap\.params\)',html)
if not match:
    raise RuntimeError('Official default search conditions missing')
defaults=json.loads(match.group(1))
params={'c_d1':'1'}
for detail in defaults.get('details',[]):
    key=detail.get('parameter')
    if not re.fullmatch(r'd[0-9]+',str(key)) or key=='d1':
        raise RuntimeError(f'Unexpected default detail parameter: {key}')
    value=detail.get('value')
    if value not in ('true','false','either'):
        raise RuntimeError(f'Unknown default detail value: {value}')
    if value!='either': params['c_'+key]='1' if value=='true' else '0'
excluded=[]
for category in defaults.get('categories',[]):
    if category.get('value') not in ('false',False):
        raise RuntimeError('Official default category rules changed')
    excluded.append(category['code'])
params['exclude-category']='.'.join(excluded)


def fetch_page(offset, limit=200, eligible=True):
    query={**params,'offset':offset,'limit':limit}
    if not eligible: query.pop('c_d1')
    data=json.loads(get(API_BASE+'?'+urllib.parse.urlencode(query)))
    if not isinstance(data.get('items'),list) or not isinstance(data.get('count'),dict):
        raise RuntimeError('Official API response structure changed')
    return data


def comparable(store):
    return {k:v for k,v in store.items() if k not in ['first_seen','last_seen','status','missing_count']}


probe=fetch_page(0,1)
official_total=int(probe['count']['total'])
universe=int(fetch_page(0,1,eligible=False)['count']['total'])
if not 1500<=official_total<=2200 or official_total>=universe:
    raise RuntimeError(f'Invalid benefit filter counts eligible={official_total},universe={universe}')
fresh_by_id={}
brand_counts=Counter()
for offset in range(0,official_total,200):
    time.sleep(0.2)
    data=fetch_page(offset)
    if int(data['count']['total'])!=official_total or int(data['count']['offset'])!=offset:
        raise RuntimeError('Official total/offset changed during pagination')
    rows=data['items']
    if len(rows)!=min(200,official_total-offset):
        raise RuntimeError(f'Incomplete page at offset {offset}: {len(rows)}')
    for row in rows:
        code=str(row.get('code') or '')
        cats=row.get('categories') or []
        small=[c for c in cats if c.get('level')=='small']
        if not code or not small or not row.get('name') or not row.get('address_name'):
            raise RuntimeError('Store id/name/address/brand missing')
        if any(str(c.get('code')) in excluded for c in cats):
            raise RuntimeError('Excluded official category leaked into results')
        if any('せたが屋' in c.get('name','') for c in cats):
            raise RuntimeError('Noneligible Setagaya group leaked into results')
        if row.get('status')!='normal':
            raise RuntimeError(f'Unexpected official store status: {row.get("status")}')
        coord=row.get('coord') or {}
        lat=float(coord['lat']);lng=float(coord['lon'])
        if not 20<=lat<=46 or not 122<=lng<=154:
            raise RuntimeError('Missing or non-Japan coordinates')
        sid='official:id:'+code
        if sid in fresh_by_id:
            raise RuntimeError('Duplicate official store id in pagination')
        brand=small[0]['name']
        address=row['address_name']
        pref=re.match(r'(北海道|東京都|大阪府|京都府|.{2,3}県)',address)
        if not pref: raise RuntimeError('Unknown prefecture in official address')
        fresh_by_id[sid]={'store_id':sid,'official_id':code,'brand_name':brand,'category':'restaurant','name':row['name'],'address':address,'prefecture':pref.group(1),'postal_code':row.get('postal_code',''),'phone':row.get('phone',''),'lat':lat,'lng':lng,'official_url':SITE+'/spot/detail?'+urllib.parse.urlencode({'code':code}),'benefit_status':'official_eligible'}
        brand_counts[brand]+=1
if len(fresh_by_id)!=official_total or int(fetch_page(0,1)['count']['total'])!=official_total:
    raise RuntimeError('Fetched stores do not match independent official count')
fresh_stores=list(fresh_by_id.values())
pref_counts=Counter(s['prefecture'] for s in fresh_stores)
if len(pref_counts)<45 or len(brand_counts)<5:
    raise RuntimeError('Suspicious brand or prefecture coverage')

previous = load_json(CURRENT, {"stores": []})
history = load_json(HISTORY, {"stores": {}})
previous_by_id = {s["store_id"]: s for s in previous.get("stores", [])}

if previous_by_id:
    ratio = len(fresh_stores) / len(previous_by_id)
    if ratio < 0.80 or ratio > 1.50:
        raise RuntimeError(
            f"Store count changed too much: previous={len(previous_by_id)} current={len(fresh_stores)} ratio={ratio:.3f}"
        )

added_ids = sorted(set(fresh_by_id) - set(previous_by_id))
removed_ids = sorted(set(previous_by_id) - set(fresh_by_id))
common_ids = sorted(set(fresh_by_id) & set(previous_by_id))
changed_ids = [
    sid for sid in common_ids
    if comparable(fresh_by_id[sid]) != comparable(previous_by_id[sid])
]

if previous_by_id:
    if len(added_ids)>150 or len(removed_ids)>150 or len(changed_ids)>300:
        raise RuntimeError('Too many added/removed/changed stores; preserving existing D1')
    for field in ['brand_name','prefecture']:
        old=Counter(s.get(field) for s in previous_by_id.values())
        new=Counter(s.get(field) for s in fresh_stores)
        for group,count in old.items():
            if count>=10 and new[group]<count*0.5:
                raise RuntimeError(f'Group coverage dropped too much: {field} {group}')

for sid, store in fresh_by_id.items():
    old_hist = history["stores"].get(sid, {})
    first_seen = old_hist.get("first_seen") or previous_by_id.get(sid, {}).get("first_seen") or RUN_DATE
    store["first_seen"] = first_seen
    store["last_seen"] = RUN_DATE
    store["status"] = "active"
    history["stores"][sid] = {
        "store_id": sid,
        "shop_code": store.get("shop_code"),
        "brand_name": store.get("brand_name"),
        "name": store.get("name"),
        "address": store.get("address"),
        "first_seen": first_seen,
        "last_seen": RUN_DATE,
        "missing_count": 0,
        "status": "active",
    }

for sid in removed_ids:
    prior = previous_by_id[sid]
    old_hist = history["stores"].get(sid, {})
    missing_count = int(old_hist.get("missing_count", 0)) + 1
    history["stores"][sid] = {
        "store_id": sid,
        "shop_code": prior.get("shop_code"),
        "brand_name": prior.get("brand_name"),
        "name": prior.get("name"),
        "address": prior.get("address"),
        "first_seen": old_hist.get("first_seen") or prior.get("first_seen") or RUN_DATE,
        "last_seen": old_hist.get("last_seen") or prior.get("last_seen") or RUN_DATE,
        "missing_count": missing_count,
        "status": "missing_once" if missing_count == 1 else "removed_candidate",
    }

sorted_stores = sorted(
    fresh_stores,
    key=lambda s: (s.get("prefecture", ""), s.get("address", ""), s.get("name", ""))
)

current_obj = {
    "source": "https://stores.yoshinoya-holdings.com/yoshinoya-holdings/spot/list?c_d1=1",
    "api_source": API_BASE,
    "eligible_filter": params,
    "official_eligible_count": official_total,
    "official_store_universe_count": universe,
    "generated_at": GENERATED_AT,
    "eligible_count": len(sorted_stores),
    "brand_counts": dict(sorted(brand_counts.items())),
    "stores": sorted_stores,
}

snapshot_obj = dict(current_obj)
snapshot_obj["snapshot_date"] = RUN_DATE

diff_obj = {
    "source": current_obj["source"],
    "generated_at": GENERATED_AT,
    "run_date": RUN_DATE,
    "previous_generated_at": previous.get("generated_at"),
    "counts": {
        "previous": len(previous_by_id),
        "current": len(fresh_by_id),
        "added": len(added_ids),
        "removed": len(removed_ids),
        "changed": len(changed_ids),
    },
    "added": [fresh_by_id[sid] for sid in added_ids],
    "removed": [previous_by_id[sid] for sid in removed_ids],
    "changed": [
        {"store_id": sid, "before": previous_by_id[sid], "after": fresh_by_id[sid]}
        for sid in changed_ids
    ],
}

history["updated_at"] = GENERATED_AT
history["run_date"] = RUN_DATE

save_json(CURRENT, current_obj)
save_json(SNAPSHOT, snapshot_obj)
save_json(DIFF, diff_obj)
save_json(HISTORY, history)

SUMMARY.parent.mkdir(parents=True, exist_ok=True)
with SUMMARY.open("w", encoding="utf-8") as f:
    f.write(f"# 吉野家ホールディングス店舗DB 差分 {RUN_DATE}\n\n")
    f.write(f"- 優待対象店舗: {len(fresh_stores)} 店舗\n")
    f.write(f"- 新規: {len(added_ids)}\n")
    f.write(f"- 消失: {len(removed_ids)}\n")
    f.write(f"- 変更: {len(changed_ids)}\n")
    f.write("\n## ブランド別\n")
    for name, count in sorted(brand_counts.items()):
        f.write(f"- {name}: {count}\n")
    if added_ids:
        f.write("\n## 新規\n")
        for sid in added_ids[:200]:
            s = fresh_by_id[sid]
            f.write(f"- {s['brand_name']} / {s['name']} / {s['address']}\n")
    if removed_ids:
        f.write("\n## 消失\n")
        for sid in removed_ids[:200]:
            s = previous_by_id[sid]
            f.write(f"- {s.get('brand_name','')} / {s.get('name','')} / {s.get('address','')}\n")

print(json.dumps({
    "run_date": RUN_DATE,
    "eligible_count": len(fresh_stores),
    "brand_counts": dict(brand_counts),
    "added": len(added_ids),
    "removed": len(removed_ids),
    "changed": len(changed_ids),
}, ensure_ascii=False))
