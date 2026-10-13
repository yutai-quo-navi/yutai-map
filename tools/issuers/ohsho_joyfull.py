"""Complete official locator coverage, with coordinates in the world datum."""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
from official_api import DATE, fetch_text, store, snapshot

OHSHO = 'https://map.ohsho.co.jp'
OHSHO_LIST = OHSHO + '/b/ohsho/attr/?srt=citycode,poi_name_yomi'
JOYFULL = 'https://www.joyfull.co.jp/shop'


def ohsho_page(text, page=1, expected=None):
    soup = BeautifulSoup(text, 'html.parser')
    number = soup.select_one('.searchResult .number')
    match = re.fullmatch(r'(\d+)件', number.get_text(strip=True) if number else '')
    if not match:
        raise ValueError('Missing Ohsho official total')
    total = int(match[1])
    blocks = soup.select('.shopBlockList .shopBlock')
    if (expected is not None and total != expected) or len(blocks) != min(20, total-20*(page-1)) or not blocks:
        raise ValueError('Incomplete Ohsho pagination')
    hit = soup.select_one('.hitCount').get_text(strip=True)
    if hit != f'{20*(page-1)+1}～{min(20*page,total)}件を表示':
        raise ValueError('Wrong Ohsho result page')
    result = []
    for block in blocks:
        link = block.select_one('.shopName a')
        match = re.fullmatch(r'/b/ohsho/info/(\d+)/', link['href'])
        if not match:
            raise ValueError('Invalid Ohsho official ID')
        name = link.get_text(strip=True)
        brand = next((b for b in ['GYOZA OHSHO', 'Joy Naho', 'JoyNaho', '餃子の王将'] if name.startswith(b)), None)
        if not brand:
            raise ValueError('Unknown Ohsho brand')
        result.append({'id':match[1], 'name':name, 'brand': 'JoyNaho' if brand == 'Joy Naho' else brand, 'url':OHSHO+link['href']})
    return result, total


def ohsho_detail(item, text):
    soup = BeautifulSoup(text, 'html.parser')
    business = soup.select('[itemtype="https://schema.org/LocalBusiness"]')
    if len(business) != 1:
        raise ValueError('Missing Ohsho official structured coordinates')
    fields = {m['itemprop']:m['content'] for m in business[0].select('meta[itemprop]')}
    match = re.search(r'window\.infoJSON\s*=\s*', text)
    if not match:
        raise ValueError('Missing Ohsho official status')
    # This is a JavaScript object, not strict JSON: unrelated text fields may
    # contain JS-only escapes (e.g. \\'). Read only its plain ID/status/date
    # literals; coordinates and names come from the structured HTML above.
    script = next(s.get_text() for s in soup.find_all('script') if 'window.infoJSON' in s.get_text())
    def literal(key):
        values=re.findall(r'"'+re.escape(key)+r'"\s*:\s*"([^"\\]*)"',script)
        if len(values) != 1:
            raise ValueError('Missing or ambiguous Ohsho '+key)
        return values[0]
    if fields['code'] != item['id']+'_ohsho' or literal('id') != item['id'] or not item['name'].endswith(fields['name']):
        raise ValueError('Ohsho list/detail identity mismatch')
    if literal('poi_status') != '1':
        raise ValueError('Inactive Ohsho store in official results')
    if literal('print_start_date')[:10] > DATE or re.search(r'オープン予定|開店予定',item['name']):
        return None
    # infoJSON latitude/longitude and route daddr use Tokyo datum. The schema's
    # latitude/longitude are already WGS84; never use latitudeTky/longitudeTky.
    result = store('official:ohsho:'+item['id'],item['brand'],item['name'],fields['fullAddress'],fields.get('telephone'),fields['latitude'],fields['longitude'],item['url'],'restaurant')
    result['eligibility_source'] = 'https://ir.ohsho.co.jp/ir/faq/'
    return result


def collect_ohsho():
    items,total = ohsho_page(fetch_text(OHSHO_LIST))
    if not 650 <= total <= 950:
        raise ValueError('Unexpected Ohsho official total')
    for page in range(2,(total+19)//20+1):
        time.sleep(.2)
        batch,_ = ohsho_page(fetch_text(OHSHO_LIST+'&start='+str(page)),page,total)
        items.extend(batch)
    if len({x['id'] for x in items}) != total:
        raise ValueError('Duplicate or missing Ohsho IDs')
    def detail(item):
        time.sleep(.15)
        return ohsho_detail(item,fetch_text(item['url']))
    rows,excluded = [],[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for i,row in enumerate(pool.map(detail,items),1):
            if row: rows.append(row)
            else: excluded.append(items[i-1]['id'])
            if i%50 == 0: print(f'Ohsho details: {i}/{total}',flush=True)
    return rows, {'source':OHSHO_LIST,'official_store_universe_count':total,'excluded_future_ids':excluded,'coordinate_source':'Official detail LocalBusiness latitude/longitude (WGS84); Tokyo-datum fields excluded','eligible_filter':'Domestic Gyoza Ohsho, GYOZA OHSHO and JoyNaho from official shareholder FAQ'}


def joyfull_page(text):
    soup = BeautifulSoup(text,'html.parser')
    section = soup.select_one('#shop-result')
    if not section:
        raise ValueError('Missing Joyfull official result section')
    match = re.search(r'(\d+)\s*件の店舗があります',section.get_text(' ',strip=True))
    items = section.select('[data-shop-item]')
    if not match:
        if items or '検索条件に一致する店舗が見つかりませんでした' not in section.get_text():
            raise ValueError('Missing Joyfull official result total')
        return [],0
    total = int(match[1])
    if len(items) != total:
        raise ValueError('Incomplete Joyfull official region')
    rows=[]
    for item in items:
        match = re.fullmatch(r'shop_(\d+)',item['id'])
        if not match or item['href'] != JOYFULL+'/'+match[1]:
            raise ValueError('Joyfull ID/link mismatch')
        name=item['data-shop-name']
        if item.select_one('.rs-name').get_text(strip=True) != name:
            raise ValueError('Joyfull name mismatch')
        if re.search(r'オープン予定|開店予定',name):
            raise ValueError('Future Joyfull opening in locator')
        row=store('official:joyfull:'+match[1],'ジョイフル','ジョイフル '+name,item['data-shop-address'],'',item['data-latitude'],item['data-longitude'],item['href'],'restaurant')
        row['eligibility_source']='https://corporate.joyfull.co.jp/ir-complimentary'
        rows.append(row)
    if len({r['store_id'] for r in rows}) != total:
        raise ValueError('Duplicate Joyfull official IDs')
    return rows,total


def collect_joyfull():
    soup=BeautifulSoup(fetch_text(JOYFULL),'html.parser')
    regions=sorted(set(int(m[1]) for a in soup.select('a[href]') if (m:=re.fullmatch(re.escape(JOYFULL)+r'\?area=(\d+)(?:#shop-result)?',a['href']))))
    if regions != list(range(1,10)):
        raise ValueError('Joyfull region navigation changed')
    rows,counts=[],{}
    for region in regions:
        time.sleep(.2)
        batch,total=joyfull_page(fetch_text(JOYFULL+'?area='+str(region)))
        rows.extend(batch);counts[str(region)]=total
        print(f'Joyfull region {region}: {total}',flush=True)
    if len({r['store_id'] for r in rows}) != sum(counts.values()):
        raise ValueError('Overlapping or incomplete Joyfull regions')
    return rows,{'source':JOYFULL,'official_store_universe_count':len(rows),'region_counts':counts,'coordinate_source':'Official regional HTML data-latitude/data-longitude','eligible_filter':'Domestic Joyfull only; other eligible group brands require separate official sources'}
