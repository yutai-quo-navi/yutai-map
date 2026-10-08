import json
import os
import sys
import time
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from srs_parser import verify_policy, parse_stores, BENEFIT_URL, SEARCH_PAGE, API_URL

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from store_snapshot import write_snapshot


def get(url, filename):
    folder = os.environ.get('SRS_SOURCE_DIR')
    if folder:
        return (Path(folder) / filename).read_text()
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0 yutai-map/1.0'})
            with urllib.request.urlopen(req, timeout=60) as response:
                return response.read(20_000_000).decode('utf-8')
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2 ** (attempt + 1))


verify_policy(get(BENEFIT_URL, 'benefit.html'))
data = json.loads(get(API_URL, 'stores.json'))
page = json.loads(get(API_URL + '&paging=true&page=1', 'page1.json'))
rows, excluded = parse_stores(data, page, datetime.now(ZoneInfo('Asia/Tokyo')).date())
write_snapshot('srs', rows, {'source':SEARCH_PAGE,'api_source':API_URL,'official_store_universe_count':page['totalCount'],
                            'official_eligible_count':len(rows),'excluded_counts':dict(Counter(e['reason'] for e in excluded))})
