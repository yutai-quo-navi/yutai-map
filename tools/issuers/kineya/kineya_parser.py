import math
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'features'))
from scrape_kyoritsu_hotels import Document,PREFECTURES
PORTAL='https://g-kineya.app.gmo-housepay.jp/'
API='https://api.gmo-housepay.jp/app/v1/shops?directory=kabunushiyutai&limit=1000&offset=1'
SEARCH='https://gourmet-kineya.co.jp/search'
COMPANIES={'株式会社グルメ杵屋レストラン','Genki Global Dining Concepts','株式会社ＪＢイレブン','株式会社ゆきむら壱番亭'}
BRANDS=['GELATERIA solege','KAMI-HIKOKI','BAR心斎橋1923','おらがそば','おらが蕎麦','かつ里','きなさ','きねや','ぎんざ田中屋','しゃぽーるーじゅ','すみ田','そじ坊','もりの屋','やおみ','グルメ','サイアムオーキッド','シジャン','ティーヌン','ロムレット','丼丼亭','二尺五寸','叶家','天はな','天亭','明月庵ぎんざ田中屋','杵屋麦丸','杵屋','神田','穂の香','萬野','開明軒','麦まる','GENKI SUSHI','GINZA SEN-RYO','うま勝','てっか丸','京都千両','千両','元気寿司','魚べい','フジヤマ55','FUJIYAMA55','モトヤマ55','ゴーゴーカレーxフジヤマ55','一刻屋','一刻魁堂','ロンフーダイニング','ロンフーエアキッチン','有楽家','コメダ珈琲店','鯱ひげ','名古屋鯱ひげ','ドン・キホーテ','らーめん 王子','ゆきむら亭','つけ麺吉衛門','中華料理雪村','壱番亭','炎座','石焼らーめん一兆','醤々亭','雪村','鶏一番']

def norm(v):return re.sub(r'\s+','',unicodedata.normalize('NFKC',str(v or ''))).lower()
def phone(v):return re.sub(r'\D','',str(v or ''))
def brand_for(name):
    matches=[b for b in BRANDS if norm(name).startswith(norm(b))]
    if not matches:raise ValueError('Unknown official eligible brand: '+name)
    return max(matches,key=lambda b:len(norm(b)))

def own_directory(html):
    cards=Document(html).root.find('a','search_result_item')
    label=re.search(r'検索結果：(\d+)件',html)
    if not label or len(cards)!=int(label[1]) or not 250<=len(cards)<=500:raise ValueError('Incomplete Kineya restaurant directory')
    rows=[]
    for c in cards:
        if not any(i.attrs.get('alt')=='株主優待ご利用可' for i in c.find('img')):continue
        names=c.find('p','name')[0].find('span');address=c.find('p','address')[0].find('span')[-1].text();url=c.attrs['href']
        if not re.fullmatch(r'https://gourmet-kineya\.co\.jp/search/\d+/?',url):raise ValueError('Unexpected detail URL')
        rows.append(dict(name=' '.join(n.text() for n in names),address=address,url=url))
    return rows

def own_coordinates(card,html):
    if '株主優待' not in html:raise ValueError('Official benefit detail missing')
    m=re.search(r'destination=(-?\d+\.\d+),(-?\d+\.\d+)',html)
    if not m:raise ValueError('Official coordinates missing')
    lat,lng=map(float,m.groups())
    if not (math.isfinite(lat) and math.isfinite(lng) and 20<=lat<=46 and 122<=lng<=154):raise ValueError('Invalid official coordinates')
    tels=set(phone(x) for x in re.findall(r'href="tel:([^"<>]+)',html))
    if len(tels)!=1:raise ValueError('Ambiguous official store telephone')
    return dict(card,phone=tels.pop(),lat=lat,lng=lng)

def parse_stores(data,coordinates):
    shops=data.get('list');count=data.get('count')
    if not isinstance(shops,list) or len(shops)!=count or data.get('offset')!=1 or not 500<=count<=1000:raise ValueError('Incomplete official voucher directory')
    if set(s['company'] for s in shops)!=COMPANIES:raise ValueError('Official partner companies changed')
    phone_counts=Counter(c['phone'] for c in coordinates)
    mapped={c['phone']:c for c in coordinates if phone_counts[c['phone']]==1}
    rows,excluded,seen=[],[],set()
    for s in shops:
        sid=str(s['id'])
        if sid in seen:raise ValueError('Duplicate voucher store')
        seen.add(sid)
        if s['name']=='水間鉄道フリー乗車証':
            excluded.append({'id':sid,'reason':'鉄道乗車証交換窓口'});continue
        name=re.sub(r'\s+',' ',s['name']).strip();address=re.sub(r'\s+',' ',s['address']).strip()
        pref=next((p for p in PREFECTURES if address.startswith(p)),None)
        if not pref or not name:raise ValueError('Missing official domestic identity')
        brand=brand_for(name)
        row=dict(store_id='official:gmo:'+sid,official_id=sid,name=name,address=address,prefecture=pref,phone=s.get('telephone',''),brand_name=brand,category='cafe' if brand in {'コメダ珈琲店','鯱ひげ','名古屋鯱ひげ'} else 'restaurant',official_url=PORTAL+'#/shop/'+sid+'/',benefit_status='official_eligible',operating_company=s['company'])
        m=mapped.get(phone(row['phone']))
        if m and s['company']=='株式会社グルメ杵屋レストラン' and m['address'].startswith(pref):
            # The official current detail page is authoritative for branch address/coordinates.
            row.update(address=m['address'],lat=m['lat'],lng=m['lng'],official_url=m['url'],coordinate_source=m['url'])
        rows.append(row)
    return rows,excluded
