import json
import os
import sys
import time
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from arclands_parser import parse_pages, SEARCH_URL, API_URL
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from store_snapshot import write_snapshot

def get(offset):
    folder=os.environ.get('ARCLANDS_SOURCE_DIR')
    if folder:return json.loads((Path(folder)/('arc-page-'+str(offset)+'.json')).read_text())
    url=API_URL+'?add=detail_group&datum=wgs84&limit=100&offset='+str(offset)
    for attempt in range(3):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 yutai-map/1.0','Referer':SEARCH_URL})
            with urllib.request.urlopen(req,timeout=60) as r:return json.loads(r.read(20_000_000))
        except OSError:
            if attempt==2:raise
            time.sleep(2**(attempt+1))

pages=[get(0)]
if not 600<=pages[0]['count']['total']<=1400:raise ValueError('Unexpected official total')
for offset in range(100,pages[0]['count']['total'],100):pages.append(get(offset))
rows,excluded,total=parse_pages(pages,datetime.now(ZoneInfo('Asia/Tokyo')).date())
write_snapshot('arclands',rows,dict(source=SEARCH_URL,api_source=API_URL,official_store_universe_count=total,official_eligible_count=len(rows),excluded_counts=dict(Counter(e['reason'] for e in excluded))))
