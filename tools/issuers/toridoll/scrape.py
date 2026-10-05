"""Import official domestic locations and the current benefit exclusions into D1."""
import html
import json
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, datetime, timezone, timedelta
from html.parser import HTMLParser
from pathlib import Path

SITE = 'https://stores.toridoll.com'
SEARCH_PAGE = SITE + '/directory'
BENEFIT_PAGE = 'https://www.toridoll.com/ir/stock/shareholder/'
BASE = Path('data/issuers/toridoll/stores')
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
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def get_page(url, cache_name):
    # Offline fixtures let the importer be validated without repeated official requests.
    fixture = os.environ.get('TORIDOLL_SOURCE_DIR')
    if fixture:
        return (Path(fixture) / cache_name).read_text(encoding='utf-8')
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 yutai-map/1.0 (+https://github.com/yutai-quo-navi/yutai-map)'})
            with urllib.request.urlopen(req, timeout=90) as response:
                body = response.read(30_000_001)
            if len(body)>30_000_000:
                raise RuntimeError('Unexpected oversized official page')
            return body.decode('utf-8')
        except (OSError, TimeoutError):
            if attempt==2:
                raise
            time.sleep(2*(attempt+1))


class JsonScript(HTMLParser):
    def __init__(self, key, value):
        super().__init__()
        self.key, self.value, self.inside = key, value, False
        self.parts, self.matches = [], []

    def handle_starttag(self, tag, attrs):
        if tag=='script' and dict(attrs).get(self.key)==self.value:
            self.inside=True
            self.parts=[]

    def handle_data(self, data):
        if self.inside:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag=='script' and self.inside:
            self.matches.append(json.loads(''.join(self.parts)))
            self.inside=False


def script_data(page, key, value):
    parser=JsonScript(key,value)
    parser.feed(page)
    if len(parser.matches)!=1:
        raise RuntimeError(f'Official JSON script missing or duplicated: {value}')
    return parser.matches[0]


def plain(value):
    return html.unescape(re.sub('<[^>]*>', ' ', value)).strip()


def norm(value):
    value=unicodedata.normalize('NFKC',str(value))
    value=re.sub(r'([一二三四五六七八九])丁目',lambda m: str('一二三四五六七八九'.index(m[1])+1)+'丁目',value)
    return re.sub(r'[\s・･\-‐–—ー_]', '', value)


def exclusion_section(value):
    found=[]
    def walk(node):
        if isinstance(node,list):
            for i,item in enumerate(node):
                if isinstance(item,dict) and item.get('head3')=='株主優待カードが利用できない店舗':
                    following=node[i+1:i+3]
                    if len(following)!=2 or following[0].get('fieldId')!='richText' or following[1].get('fieldId')!='table':
                        raise RuntimeError('Official benefit exclusion section changed')
                    if '国内の全店舗' not in following[0]['richText']:
                        raise RuntimeError('Official benefit eligibility scope changed')
                    found.append(following[1]['html']['html'])
                walk(item)
        elif isinstance(node,dict):
            for item in node.values():
                walk(item)
    walk(value)
    if len(found)!=1:
        raise RuntimeError('Official benefit exclusion table not uniquely identified')
    return found[0]


def parse_exclusions(table):
    out=[]
    brand=''
    for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>',table,re.S):
        cells=re.findall(r'<(?:th|td)\b[^>]*>(.*?)</(?:th|td)>',row,re.S)
        if len(cells)!=2:
            raise RuntimeError('Unknown exclusion table row layout')
        brand=plain(cells[0]) or brand
        branch=plain(cells[1])
        if not brand or not branch:
            raise RuntimeError('Empty official exclusion rule')
        brand=brand.replace('ラー麺','')
        branch=re.split(r'[（(]',branch)[0].strip()
        if 'オンラインショップ' in branch:
            out.append((brand,'オンラインショップ'))
        else:
            out.append((brand,branch.removesuffix('店')))
    if len(out)<10 or len(out)>80 or len(set(out))!=len(out):
        raise RuntimeError('Suspicious benefit exclusion coverage')
    return out


def comparable(store):
    return {k:v for k,v in store.items() if k not in ['first_seen','last_seen','status','missing_count']}


benefit=get_page(BENEFIT_PAGE,'benefit.html')
exclusions=parse_exclusions(exclusion_section(script_data(benefit,'id','__NEXT_DATA__')))
directory=get_page(SEARCH_PAGE,'directory.html')
regions=script_data(directory,'id','statelist-json')
japan=[row['key'] for row in regions if row['key']['entity']['profile']['address']['countryCode']=='JP']
if len(japan)!=47 or len({r['key'] for r in japan})!=47:
    raise RuntimeError('Incomplete official prefecture directory')
official_total=sum(int(row['count']) for row in japan)
if not 900<=official_total<=1600:
    raise RuntimeError(f'Unexpected domestic official count: {official_total}')
locator=script_data(directory,'class','js-fakelocator-params')
options=locator['schema']['c_storeBrands']['type']['optionType']['option']
brand_names={}
for option in options:
    display=option['displayName']
    for alias in [display,option['textValue'],*[x['value'] for x in option.get('displayNameTranslation',[])]]:
        brand_names[alias]=display
brand_names.update({'Zundo-ya':'ずんどう屋','Banpaiya':'晩杯屋','Udon Yamaguchi':'うどん山口'})
raw_by_id={}
future_ids=[]
closed_ids=[]
for region in japan:
    if not region['url'].startswith('日本/') or '..' in region['url']:
        raise RuntimeError('Unexpected official region URL')
    time.sleep(.25 if not os.environ.get('TORIDOLL_SOURCE_DIR') else 0)
    page=get_page(SITE+'/'+urllib.parse.quote(region['url'],safe='/'),region['key']+'.html')
    data=script_data(page,'class','js-fakelocator-params')
    entities=data['entities']
    if len(entities)!=int(region['count']):
        raise RuntimeError(f'Incomplete prefecture snapshot: {region["key"]} {len(entities)} != {region["count"]}')
    for entity in entities:
        profile=entity['profile']
        address=profile['address']
        meta=profile['meta']
        code=str(meta['id'])
        if address['countryCode']!='JP' or meta['countryCode']!='JP' or address['region']!=region['key']:
            raise RuntimeError('Foreign or misplaced store in domestic snapshot')
        if not re.fullmatch(r'[A-Za-z0-9_-]+',code) or code in raw_by_id:
            raise RuntimeError('Invalid or duplicate official store id')
        brand=brand_names.get(profile.get('c_storeBrands')) or brand_names.get(profile.get('c_cp_BrandName'))
        raw_brand=profile.get('c_storeBrands')
        if not brand and isinstance(raw_brand,str) and re.search(r'[ぁ-んァ-ン一-龠]',raw_brand) and norm(raw_brand) in norm(profile.get('name','')):
            brand=raw_brand
        if not brand:
            raise RuntimeError(f'Unknown official brand: {profile.get("c_cp_BrandName")} ({code})')
        coordinate=profile.get('yextDisplayCoordinate') or profile.get('displayCoordinate')
        if not coordinate:
            raise RuntimeError(f'Official display coordinates missing: {code}')
        lat,lng=float(coordinate['lat']),float(coordinate['long'])
        if not 20<=lat<=46 or not 122<=lng<=154:
            raise RuntimeError(f'Invalid domestic coordinates: {code}')
        name=profile.get('name')
        street=''.join(str(address.get(k) or '') for k in ['region','city','line1','line2','line3'])
        if not name or not address.get('city') or not address.get('line1'):
            raise RuntimeError(f'Incomplete official name/address: {code}')
        raw_by_id[code]={'store_id':'official:id:'+code,'official_id':code,'brand_name':brand,'category':'cafe' if brand in {'コナズ珈琲','KNOWS COFFEE','PALM WAGON'} else 'bakery' if brand=='焼きたてコッペ製パン' else 'restaurant','name':name,'address':street,'prefecture':address['region'],'postal_code':address.get('postalCode') or '','phone':(profile.get('mainPhone') or {}).get('display') or '','lat':lat,'lng':lng,'official_url':SITE+'/'+code,'benefit_status':'official_eligible'}
        if profile.get('closed') is True:
            closed_ids.append(code)
        opening=profile.get('c_店舗開店日')
        if opening and date(int(opening['year']),int(opening['month']),int(opening['day']))>NOW.date():
            future_ids.append(code)
    print(f'Validated {region["key"]}: {len(entities)} official locations',flush=True)
if len(raw_by_id)!=official_total:
    raise RuntimeError('Domestic store coverage differs from official directory')

excluded_ids=set(future_ids+closed_ids)
unmatched_exclusions=[]
for brand,branch in exclusions:
    # The official exclusion table names the facility; the directory omits it.
    match_branch='吉祥寺' if (brand,branch)==('いぶきうどん','アトレ吉祥寺') else branch
    matches=[code for code,s in raw_by_id.items() if s['brand_name']==brand and norm(match_branch) in norm(s['name'])]
    if len(matches)>1:
        raise RuntimeError(f'Ambiguous official exclusion: {brand} {branch}')
    if matches:
        excluded_ids.update(matches)
    elif branch not in ('オンラインショップ','キッチンカー'):
        unmatched_exclusions.append([brand,branch])
if len(unmatched_exclusions)>3:
    raise RuntimeError(f'Unable to match current exclusion table: {unmatched_exclusions}')
fresh_by_id={s['store_id']:s for code,s in raw_by_id.items() if code not in excluded_ids}
fresh_stores=list(fresh_by_id.values())
brand_counts=Counter(s['brand_name'] for s in fresh_stores)
pref_counts=Counter(s['prefecture'] for s in fresh_stores)
if len(pref_counts)!=47 or len(brand_counts)<10 or not 850<=len(fresh_stores)<=1600:
    raise RuntimeError('Suspicious eligible brand/prefecture coverage')

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
    "source": SEARCH_PAGE,
    "benefit_source": BENEFIT_PAGE,
    "generated_at": GENERATED_AT,
    "official_domestic_count": official_total,
    "excluded_count": len(excluded_ids),
    "future_opening_count": len(future_ids),
    "closed_count": len(closed_ids),
    "unmatched_exclusions": unmatched_exclusions,
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
    f.write(f"# トリドールホールディングス店舗DB 差分 {RUN_DATE}\n\n")
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
