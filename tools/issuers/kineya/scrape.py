import json
import os
import sys
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from kineya_parser import API,PORTAL,SEARCH,own_directory,own_coordinates,parse_stores,norm
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from store_snapshot import write_snapshot


def get(url,filename,headers=None):
    folder=os.environ.get('KINEYA_SOURCE_DIR')
    if folder:return (Path(folder)/filename).read_text()
    for attempt in range(3):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 yutai-map/1.0',**(headers or {})})
            with urllib.request.urlopen(req,timeout=45) as r:return r.read(20_000_000).decode('utf-8')
        except OSError:
            if attempt==2:raise
            time.sleep(2**attempt)

policy=get('https://www.gourmet-kineya-hd.co.jp/ir/shareholder/','benefit.html')
if not all(t in policy for t in ['Genki Global Dining Concepts','JBイレブン','g-kineya.app.gmo-housepay.jp']):raise ValueError('Official mutual-use policy changed')
data=json.loads(get(API,'stores.json',{'Sub-Domain':'g-kineya','Accept':'application/json','Origin':PORTAL.rstrip('/')}))
cards=own_directory(get(SEARCH,'own.html'))
def detail(card):
    filename='own-pages/'+card['url'].rstrip('/').split('/')[-1]+'.html'
    folder=os.environ.get('KINEYA_SOURCE_DIR')
    if folder and not (Path(folder)/filename).exists():return None
    return own_coordinates(card,get(card['url'],filename))
with ThreadPoolExecutor(max_workers=4) as pool:
    coordinates=[row for row in pool.map(detail,cards) if row]
if not os.environ.get('KINEYA_SOURCE_DIR') and len(coordinates)!=len(cards):raise ValueError('Incomplete official coordinate coverage')
rows,excluded=parse_stores(data,coordinates)
jb=get('https://www.jb11.co.jp/','jb.html')
# An ongoing renovation notice overrides the voucher portal's listing. Reopening announcements take precedence.
text=norm(jb)
if '東広島店' in text and '2026年9月28日' in text and '休業' in text and not any(t in text for t in ['東広島店営業再開','東広島店リニューアルオープン']):
    active=[]
    for row in rows:
        if norm(row['name'])=='フジヤマ55東広島店':excluded.append({'id':row['official_id'],'reason':'公式改装休業案内'})
        else:active.append(row)
    rows=active
write_snapshot('kineya',rows,dict(source=PORTAL+'#/kabunushiyutai/search',api_source=API,official_store_universe_count=data['count'],official_eligible_count=len(rows),official_coordinate_directory_count=len(cards),excluded_counts=dict(Counter(e['reason'] for e in excluded))))
