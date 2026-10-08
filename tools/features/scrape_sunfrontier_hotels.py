#!/usr/bin/env python3
"""Verify Sun Frontier's live voucher eligibility and hotel access pages monthly."""
import argparse
import hashlib
import html
import json
import math
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag
from zoneinfo import ZoneInfo
from scrape_kyoritsu_hotels import ROOT, Document, PREFECTURES, fetch as live_fetch, validate_previous, write_sql
from scrape_daiwa_hotels import address_from_detail
from scrape_seibu_hotels import official_coordinates

FEATURE = 'sunfrontier-hotels'
IR = 'https://www.sunfrt.co.jp/ir/stock_information/shareholder_benefits/'
CONDITIONS = '株主様ご優待割引券を宿泊代に利用できます。ホテルへ電話で予約、または公式サイトで現地決済の予約後に電話し、優待券利用を事前にお伝えください。他社予約サイトは対象外。券の株主様情報欄を記入し、チェックイン時に提示してください。使用枚数は贈呈枚数の範囲内。おつりは出ません。不足額・入湯税・宿泊税等は別途支払い。売買された券は利用できません。'
ALLOWED_HOSTS = {'seifutei.jp', 'hotel-oosado.jp', 'shijo-bettei.jp', 'or-okinawa.com', 'www.7e8e.jp',
    'hotel-azuma.jp', 'soraniwa-hotel.jp', 'stitch-hotel.jp', 'okinawa-hiyoriocean.jp',
    'maihama.hiyori-hotel.jp', 'kyoto-kamogawa.hiyori-hotel.jp', 'namba.hiyori-hotel.jp',
    'suminoe.hiyori-hotel.jp', 'shinsekai.hiyori-hotel.jp', 'dotonbori.hiyori-hotel.jp', 'matsuyama.hiyori-hotel.jp',
    'ishikari.tabino-hotel.jp', 'rokkasho.tabino-hotel.jp', 'utsunomiya-yuinomori.tabino-hotel.jp',
    'kashima.tabino-hotel.jp', 'narita.tabino-hotel.jp', 'sado.tabino-hotel.jp', 'matsumoto.tabino-hotel.jp',
    'hida-takayama.tabino-hotel.jp', 'kakogawa.tabino-hotel.jp', 'kurashiki-mizushima.tabino-hotel.jp',
    'aso-kumamoto.tabino-hotel.jp', 'miyakojima.tabino-hotel.jp', 'villa-miyakojima.tabino-hotel.jp',
    'toyokawa.tabino-hotel.jp', 'www.springsunny.jp', 'donden-sanso.jp'}


def fetch(url):
    cache = os.environ.get('SUNFRONTIER_SOURCE_DIR')
    path = Path(cache)/hashlib.sha256(url.encode()).hexdigest() if cache else None
    if path and path.exists():return path.read_text()
    document = live_fetch(url)
    if path:
        path.parent.mkdir(parents=True,exist_ok=True); path.write_text(document)
    return document


def verify_policy(document):
    text = re.sub(r'\s+', '', Document(document).root.text())
    required = ['株主様ご優待割引券', 'ホテルへ直接お電話', '公式ホームページからのご予約＋お電話',
                '現地決済', '事前に本券ご利用の旨', '株主様情報ご記入欄', 'おつりは出ません',
                '発行年の7月1日から翌年の6月30日', '1回あたりの使用枚数に制限はございません',
                '売買された券は無効', '入湯税や宿泊税']
    if any(term not in text for term in required):
        raise ValueError('Sun Frontier voucher rules changed; manual review required')


def pending_opening(text, today):
    if '開業予定' not in text:return False
    match = re.search(r'(\d{4})[.年](\d{1,2})(?:[.月](\d{1,2}))?', text)
    if not match:raise ValueError('Unrecognized planned opening date')
    y, m, d = match.groups()
    # Month-only openings require manual/listing confirmation during that month.
    return (int(y),int(m),int(d or 32)) > (today.year,today.month,today.day)


def parse_hotels(document, today):
    hotels = {}
    for table in Document(document).root.find('table'):
        rows = table.find('tr')
        if not rows or 'ご宿泊' not in rows[0].text():continue
        for row in rows[1:]:
            cells = row.find('td')
            if len(cells) < 3 or cells[2].text() not in {'〇','○'}:continue
            if pending_opening(row.text(),today) or re.search(r'休業中|閉館|営業終了',row.text()):continue
            links = cells[0].find('a')
            if len(links) != 1:raise ValueError('Unexpected Sun Frontier eligibility row')
            url = links[0].attrs.get('href','')
            host = urlparse(url).hostname or ''
            approved = host in ALLOWED_HOSTS or bool(re.fullmatch(r'[a-z0-9-]+\.(?:tabino-hotel|hiyori-hotel)\.jp',host))
            if urlparse(url).scheme != 'https' or not approved:
                raise ValueError('Unverified Sun Frontier official property URL: '+links[0].text())
            name = re.sub(r'\s*（[^）]*開業予定）','',links[0].text()).strip()
            if url in hotels:raise ValueError('Duplicate hotel in eligibility listing')
            hotels[url] = {'id':'sunfrontier-'+hashlib.sha256(url.encode()).hexdigest()[:14],
                           'name':name,'phone':cells[1].text(),'sourceUrl':url,'eligibilitySourceUrl':IR}
    if not 25 <= len(hotels) <= 60:raise ValueError('Abnormal Sun Frontier lodging count')
    return list(hotels.values())


def hotel_address(document, hotel=None):
    document = re.sub(r'<(?:rt|rp)\b[^>]*>.*?</(?:rt|rp)>','',document,flags=re.I|re.S)
    # Villa's check-in guidance also lists the separate lit hotel. Its own
    # contact footer identifies the Villa address, rather than the first address.
    if hotel and urlparse(hotel['sourceUrl']).hostname == 'villa-miyakojima.tabino-hotel.jp':
        footers = Document(document).root.find('footer')
        own = [n for n in footers if re.sub(r'\s+','',hotel['name']) in re.sub(r'\s+','',n.text())]
        if len(own) != 1:raise ValueError('Unverified Villa contact footer')
        document = '<p>'+html.escape(own[0].text())+'</p>'
    doc = Document(document)
    try:
        address = address_from_detail(document)
    except ValueError:
        # Ishikari's official footer omits the prefecture; its postal/city pair is unique.
        addresses = [n.text() for n in doc.root.find('address')]
        ishikari = [a for a in addresses if re.match(r'〒061-3213\s*石狩市',a)]
        japanese = [n.text() for n in doc.root.find('div','ja')
                    if n.text().startswith('京都府京都市下京区西石垣')]
        if ishikari:address = ishikari[0].replace('石狩市','北海道石狩市',1)
        elif japanese:address = japanese[0]
        else:raise
    address = re.split(r'Google Maps|\b(?:TEL|FAX|Phone)\b|\s+\d+-\d+ [A-Za-z]',address,flags=re.I)[0].strip().rstrip('：:')
    address = re.split(r'\s+0\d{1,4}-\d{1,4}-\d{3,4}|\[\s*google\s*map\s*\]',address,flags=re.I)[0].strip()
    address = re.split(r'マップコード\s*[：:]',address)[0].strip()
    address = re.sub(r'（\s*[ぁ-ん ]+\s*）','',address)
    address = address.replace('京都市','京都府京都市',1) if re.match(r'〒\s*\d{3}-\d{4}\s*京都市',address) else address
    return address


def hotel_coordinates(document, hotel):
    try:return official_coordinates(document)
    except ValueError:pass
    doc = Document(document)
    for frame in doc.root.find('iframe'):
        source = frame.attrs.get('data-src','')
        if urlparse(source).hostname in {'www.google.com','maps.google.com'}:
            try:return official_coordinates('<iframe src="'+html.escape(source,quote=True)+'"></iframe>')
            except ValueError:pass
    # The ryokan publishes its own address and coordinates as structured Hotel data.
    for script in doc.root.find('script'):
        if script.attrs.get('type') != 'application/ld+json':continue
        try:data = json.loads(script.text())
        except ValueError:continue
        nodes = data if isinstance(data,list) else data.get('@graph',[data])
        for node in nodes:
            if not isinstance(node,dict) or node.get('@type') not in {'Hotel','LodgingBusiness'} or not isinstance(node.get('geo'),dict):continue
            name = re.sub(r'\s+','',str(node.get('name','')))
            expected = re.sub(r'\s+','',hotel['name'])
            if not name or (name not in expected and expected not in name):continue
            geo = node['geo']
            return {'lat':float(geo['latitude']), 'lng':float(geo['longitude']),
                    'coordinateSource':'公式ホテルの構造化データ'}
    raise ValueError('Missing official hotel coordinates')


def verify_hotel(hotel, today, detail_fetch=fetch):
    home = hotel['sourceUrl']; document = detail_fetch(home)
    links = []
    for link in Document(document).root.find('a'):
        if 'アクセス' not in link.text() and link.text().lower() != 'access':continue
        if re.search(r'不正|お詫び|お知らせ',link.text()):continue
        url = urldefrag(urljoin(home, link.attrs.get('href','')))[0]
        if urlparse(url).scheme == 'https' and urlparse(url).hostname == urlparse(home).hostname and url not in links:
            links.append(url)
    address = None; coordinates = None; location_url = home; address_url = home
    # Prefer the dedicated official access page; homepage maps are a fallback.
    candidates = links[:1] + [home]
    for url in dict.fromkeys(candidates):
        page = document if url == home else detail_fetch(url)
        if not address:
            try:address = hotel_address(page,hotel); address_url = url
            except ValueError:pass
        if not coordinates:
            try:coordinates = hotel_coordinates(page,hotel); location_url = url
            except ValueError:pass
    if address and not coordinates:
        supplements = json.loads((ROOT/'data/features/sunfrontier-hotel-coordinates.json').read_text())
        row = supplements.get(hotel['name'])
        if row and row['address'] == address and row['officialLocationUrl'] in candidates:
            page = document if row['officialLocationUrl'] == home else detail_fetch(row['officialLocationUrl'])
            if row.get('mapLink') and row['mapLink'] not in page:raise ValueError('Official map link changed')
            if row.get('sameBuildingName') and row['sameBuildingName'] not in Document(document).root.text():
                raise ValueError('Verified same-building restaurant changed')
            coordinates = {k:v for k,v in row.items() if k not in {'name','address','officialLocationUrl','mapLink','sameBuildingName'}}
    if not address or not coordinates:raise ValueError('Missing official hotel address or coordinates')
    if not (math.isfinite(coordinates['lat']) and math.isfinite(coordinates['lng'])
            and 20 <= coordinates['lat'] <= 46 and 122 <= coordinates['lng'] <= 154):
        raise ValueError('Invalid Sun Frontier hotel coordinates')
    return {**hotel, 'address':address, **coordinates, 'addressSourceUrl':address_url,
            'coordinateSourceUrl':coordinates.get('coordinateSourceUrl',location_url),
            'verified':True,'coordinateCheckedOn':today.isoformat(),'conditions':CONDITIONS}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--previous-counts',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'cloudflare/generated/sync_sunfrontier_hotels.sql')
    args = parser.parse_args(); today = datetime.now(ZoneInfo('Asia/Tokyo')).date()
    document = fetch(IR); verify_policy(document); hotels = parse_hotels(document,today)
    stores = []; errors = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = {pool.submit(verify_hotel,h,today):h for h in hotels}
        for task in as_completed(tasks):
            try:
                store = task.result(); stores.append(store); print('Verified:',store['name'],flush=True)
            except Exception as error:
                errors.append(tasks[task]['name']+': '+str(error)); print('Failed:',errors[-1],flush=True)
    if errors:raise ValueError('; '.join(errors))
    stores.sort(key=lambda s:s['name'])
    snapshot = {'id':FEATURE,'checkedOn':today.isoformat(),'stores':stores}
    if args.previous_counts:
        groups = json.loads(args.previous_counts.read_text())
        previous = {r['feature_id']:r['count'] for group in groups for r in group.get('results',[])}
        validate_previous([snapshot],previous)
    write_sql([snapshot],args.output,batch_id=FEATURE)
    Path('/tmp/sunfrontier-snapshot.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2))
    print('Verified',len(stores),'Sun Frontier hotels',flush=True)


if __name__=='__main__':main()
