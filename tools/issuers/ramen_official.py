"""Official ramen locators. Reject incomplete lists before creating an issuer delta."""
import json
import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup, Comment
from official_api import fetch_text, fetch, store, snapshot, DATE

YAMA_BRANDS = {'ramen_yamaokaya': 'ラーメン山岡家', 'miso_ramen': '味噌ラーメン山岡家', 'niboshi_ramen': '煮干しラーメン山岡家'}
YAMA_SOURCE = 'https://www.yamaokaya.com/shops/'
CHIKARA_SOURCE = 'https://stores.ippudo.com/' + urllib.parse.quote('日本')


def yama_list(text):
    soup = BeautifulSoup(text, 'html.parser')
    script = next((x.string for x in soup.find_all('script') if 'var json_realtime =' in (x.string or '')), None)
    if script is None:
        raise ValueError('Missing official Yamaokaya coordinate JSON')
    data = json.JSONDecoder().raw_decode(script[script.index('{'):])[0]
    coords = {str(x['id']): x for x in data['shops']}
    if len(coords) != len(data['shops']):
        raise ValueError('Duplicate Yamaokaya coordinate IDs')
    items = soup.select('li.shops_item')
    ids = [re.fullmatch(r's(\d+)', x['id'])[1] for x in items]
    if len(set(ids)) != len(ids) or set(ids) != set(coords):
        raise ValueError('Incomplete Yamaokaya HTML/JSON coverage')
    result = []
    for item, sid in zip(items, ids):
        brand = item['data-brand']
        if brand not in {*YAMA_BRANDS, 'gyoza'}:
            raise ValueError('Unknown Yamaokaya brand')
        if brand == 'gyoza':
            continue  # Gyoza shops are not in the official shareholder eligible brands.
        href = item.select_one('a')['href']
        if href != f'/shops/{sid}/':
            raise ValueError('Yamaokaya ID/link mismatch')
        region = item.find_parent('section', class_='shops_part').select_one('h3').get_text(' ', strip=True)
        pref = re.findall(r'北海道|東京都|大阪府|京都府|[^\s]+県', region)
        if len(pref) != 1:
            raise ValueError('Missing Yamaokaya prefecture')
        result.append({'id': sid, 'brand': YAMA_BRANDS[brand], 'name': item.select_one('.shops_name').get_text(strip=True), 'prefecture': pref[0], 'lat': coords[sid]['lat'], 'lng': coords[sid]['lng'], 'url': 'https://www.yamaokaya.com' + href})
    return result, len(items)


def yama_detail(item, text):
    soup = BeautifulSoup(text, 'html.parser')
    if soup.body.get('class') != [item['id']]:
        raise ValueError('Yamaokaya detail ID mismatch')
    title = soup.title.get_text().split(' | ')[0]
    if title != item['name']:
        raise ValueError('Yamaokaya detail name mismatch')
    fields = {tr.select_one('th').get_text(strip=True): tr.select_one('td') for tr in soup.select('tr.info_table_row') if tr.select_one('th') and tr.select_one('td')}
    td = fields['住所']
    # Only direct address text; map and routing copy are not part of the address.
    address = ''.join(str(x).strip() for x in td.find_all(string=True, recursive=False) if not isinstance(x, Comment))
    address = re.sub(r'^〒\s*\d{3}-\d{4}\s*', '', address)
    if not re.match(r'北海道|東京都|大阪府|京都府|.{2,3}県', address):
        address = item['prefecture'] + address
    iframe = td.select_one('iframe')['src']
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(iframe).query)['q'][0]
    lat, lng = map(float, query.split(','))
    if abs(lat-float(item['lat'])) > .00001 or abs(lng-float(item['lng'])) > .00001:
        raise ValueError('Yamaokaya list/detail coordinate mismatch')
    phone = fields['電話番号'].get_text(' ', strip=True)
    return store('official:yamaokaya:'+item['id'], item['brand'], item['name'], address, phone, lat, lng, item['url'], 'restaurant')


def collect_yamaokaya():
    items, universe = yama_list(fetch_text(YAMA_SOURCE))
    def detail(item):
        time.sleep(.15)
        return yama_detail(item, fetch_text(item['url']))
    rows = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for i, row in enumerate(pool.map(detail, items), 1):
            rows.append(row)
            if i % 20 == 0:
                print(f'Yamaokaya details: {i}/{len(items)}', flush=True)
    return rows, {'source': YAMA_SOURCE, 'official_store_universe_count': universe, 'eligible_filter': 'Official shareholder policy: ramen, miso ramen and niboshi ramen Yamaokaya; gyoza excluded', 'coordinate_source': 'Official locator json_realtime, cross-checked against each official detail map'}


def yext_document(text):
    soup = BeautifulSoup(text, 'html.parser')
    script = soup.find('script', type='module')
    match = re.search(r'JSON.parse\(decodeURIComponent\("([^"\n]+)"\)\)', script.string if script else '')
    if not match:
        raise ValueError('Missing official Yext page data')
    return json.loads(urllib.parse.unquote(match[1]))['document']


def chikara_row(row):
    name = row['name']
    brands = ['RAMEN EXPRESS 博多一風堂', 'IPPUDO RAMEN EXPRESS', '一風堂 KAY', '一風堂']
    normalized = re.sub(r'\s+', '', name)
    brand = next((b for b in brands if normalized.startswith(re.sub(r'\s+', '', b))), None)
    if not brand:
        raise ValueError('Unknown official Ippudo brand')
    address = row['address']
    if address['countryCode'] != 'JP':
        raise ValueError('Non-domestic Ippudo store')
    sid = row['slug']
    if not re.fullmatch(r'[A-Za-z0-9_-]+', sid):
        raise ValueError('Invalid Ippudo public store ID')
    coord = row['yextDisplayCoordinate']
    full = ''.join(address.get(k, '') for k in ['region','city','sublocality','line1','line2'])
    result = store('official:chikaranomoto:'+sid, brand, name, full, row.get('mainPhone'), coord['latitude'], coord['longitude'], 'https://stores.ippudo.com/'+sid, 'foodcourt' if 'EXPRESS' in brand else 'restaurant')
    result['eligibility_source'] = 'https://www.chikaranomoto.com/ir/benefit/'
    return result


CHIKARA_API = 'https://prod-cdn.us.yextapis.com/v2/accounts/me/search/vertical/query'
# Public search key embedded in the official locator client; no account credentials.
CHIKARA_PARAMS = {'api_key':'a3758bb059c4082e8cf35de765f59bbe','experienceKey':'locator','v':'20220511','version':'PRODUCTION','locale':'ja','verticalKey':'locations','input':'Japan','limit':50,'retrieveFacets':'true','skipSpellCheck':'true'}


def chikara_page(data, offset, total=None):
    if data['meta'].get('errors'):
        raise ValueError('Official Ippudo API returned errors')
    response = data['response']
    count = int(response['resultsCount'])
    if response['businessId'] != 2196888 or (total is not None and count != total):
        raise ValueError('Ippudo API identity/count changed during pagination')
    rows = [r['data'] for r in response['results']]
    if len(rows) != min(50, count-offset):
        raise ValueError('Incomplete Ippudo API pagination')
    if any(r.get('type') != 'location' or str(r.get('id')) != str(r.get('slug')) for r in rows):
        raise ValueError('Invalid official Ippudo API entity')
    return rows, count


def collect_chikaranomoto():
    rows, total, offset = [], None, 0
    while total is None or offset < total:
        url = CHIKARA_API + '?' + urllib.parse.urlencode({**CHIKARA_PARAMS, 'offset':offset})
        page, total = chikara_page(fetch(url), offset, total)
        if not 120 <= total <= 220:
            raise ValueError('Unexpected official Ippudo source size')
        rows.extend(page)
        offset += len(page)
        print(f'Ippudo API: {offset}/{total}', flush=True)
        time.sleep(.3)
    if len({r['id'] for r in rows}) != total:
        raise ValueError('Duplicate/missing Ippudo API results')
    result = []
    excluded = []
    for row in rows:
        if row.get('closed') is True or str(row.get('openDate') or row.get('c_openDate') or DATE) > DATE:
            excluded.append(row['id'])
            continue
        result.append(chikara_row(row))
    return result, {'source': 'https://stores.ippudo.com/search', 'api_source':CHIKARA_API, 'official_store_universe_count':total, 'excluded_closed_or_future_ids':excluded, 'eligible_filter':'Domestic Ippudo, Ippudo KAY and RAMEN EXPRESS brands named in the official shareholder policy; other Chikaranomoto brands are outside this initial source scope', 'coordinate_source':'Official locator Yext API yextDisplayCoordinate; complete pagination and unique IDs validated', 'eligibility_source':'https://www.chikaranomoto.com/ir/benefit/'}


def chikara_city(city, doc):
    if doc['slug'] != city['slug'] or doc['meta']['entityType']['id'] != 'ce_city':
        raise ValueError('Wrong Ippudo city document')
    children = doc['dm_directoryChildren']
    if len(children) != len(city['dm_directoryChildren']):
        raise ValueError('Incomplete Ippudo city coverage')
    return [chikara_row(row) for row in children]
