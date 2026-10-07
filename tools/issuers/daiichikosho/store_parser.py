import re
from datetime import datetime
from urllib.parse import urlparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'features'))
from scrape_kyoritsu_hotels import Document, future_opening, PREFECTURES
SEARCH_PAGE='https://dkdining.com/search/index.html'

def parse_page(document,page,today):
    doc=Document(document)
    labels=doc.root.find('p','resultTxt')
    if len(labels)!=1:raise ValueError('Missing official result count')
    m=re.fullmatch(r'(\d+)件中 (\d+)〜(\d+)件を表示',labels[0].text())
    if not m:raise ValueError('Unexpected result pagination')
    total,first,last=map(int,m.groups())
    if not 120<=total<=250 or first!=(page-1)*20+1 or last!=min(page*20,total):raise ValueError('Abnormal store count/pagination')
    coordinates={}
    for node in doc.root.find('p'):
        sid=node.attrs.get('data-shop-id')
        if not sid:continue
        raw=node.attrs.get('data-latlng','')
        if not re.fullmatch(r'[0-9.]+,\s*[0-9.]+',raw):raise ValueError('Missing official store map coordinates: '+sid)
        lat,lng=map(float,raw.split(','))
        if not(20<=lat<=46 and 122<=lng<=154):raise ValueError('Invalid domestic store coordinates')
        coordinates[sid]=(lat,lng,node.attrs.get('data-title'),node.attrs.get('data-shop-url'))
    stores=[];excluded=[]
    cards=doc.root.find('div','search-con-list-box')
    if len(cards)!=last-first+1:raise ValueError('Incomplete store page')
    for card in cards:
        sid=card.attrs.get('id','').removeprefix('shop-list__id--')
        headings=card.find('h4');links=headings[0].find('a') if len(headings)==1 else []
        if len(links)!=1 or sid not in coordinates:raise ValueError('Missing official identity')
        name=links[0].text();url=links[0].attrs['href'];lat,lng,map_name,map_url=coordinates[sid]
        if re.sub(r'\s+','',name)!=re.sub(r'\s+','',map_name) or url!=map_url or not re.fullmatch(r'\d+',sid):raise ValueError('Conflicting official store map identity')
        opening=re.search(r'【(\d{1,2})/(\d{1,2})\s*OPEN】',name,re.I)
        upcoming=bool(opening and datetime(today.year,*map(int,opening.groups())).date()>today)
        if upcoming or future_opening(card.text(),today.isoformat()) or re.search(r'閉店しました|閉店いたしました|営業終了|休業中',card.text()):
            excluded.append({'id':sid,'name':name,'reason':'開店前・営業終了・休業中'});continue
        specs={}
        for spec in card.find('div','specBox'):
            titles=spec.find('span','specTitle');values=spec.find('span','specTxt')
            if len(titles)==len(values)==1:specs[titles[0].text()]=values[0].text()
        address=specs.get('住所','');postal=re.search(r'\d{3}-\d{4}',address)
        address=re.sub(r'^〒?\s*\d{3}-\d{4}\s*','',address).strip()
        if address.startswith('中央区銀座') and 35.65<lat<35.69 and 139.74<lng<139.79:
            address='東京都'+address
        for city,prefecture in [('大阪市','大阪府'),('京都市','京都府'),('福岡市','福岡県'),('横浜市','神奈川県'),('川崎市','神奈川県'),('名古屋市','愛知県'),('札幌市','北海道'),('広島市','広島県')]:
            if address.startswith(city):address=prefecture+address
        pref=next((v for v in PREFECTURES if address.startswith(v)),None)
        if not pref or not name or not url.startswith(('https://','http://')):raise ValueError('Incomplete official store address: '+sid+' '+repr(address))
        host=urlparse(url).hostname
        group=host.split('.')[0]
        brand={'jibundoki':'じぶんどき','rakuzo':'楽蔵','umeko':'ウメ子の家','michiru':'蒸しと酒 みちる','regalo':'REGALO','celts':'CELTS','kitchen':'KITCHEN','forestdiner':'フォレストダイナー','robace':'ROBACE','senyaichiya':'鮮や一夜','kyomachi':'京町しずく','bistroya':'びすとろ家','seseragi':'せせらぎを聴きながら','totouo':'ととうお','minatoichiya':'湊一や','ginten':'ぎん天。','harenohi':'鮨やハレの日','nanagome':'七合目','matsuri':'祭酒場','marunouchibase':'MARUNOUCHI BASE','darts-one':'ダーツワン','tokachiishikarihakodate':'十勝石狩函館','atarayo':'あたらよ','shinagawapivot':'SHINAGAWA PIVOT','mochinoki-pasta':'もちの木パスタ','ginzasukiyabashi-coffee':'銀座珈琲店','hachioji-coffee':'八王子珈琲店'}.get(group,name)
        if host.startswith('taishu-amatsu-'):brand='あまつ'
        if 'ハイボールバー' in name:brand='ハイボールバー'
        if 'CELTS' in name:brand='CELTS'
        category='cafe' if ('カフェ' in name or '珈琲' in name or 'Coffee' in name) else 'restaurant'
        stores.append({'store_id':'official:id:'+sid,'official_id':sid,'name':name,'address':address,'prefecture':pref,'postal_code':postal.group() if postal else '', 'phone':specs.get('電話番号',''),'brand_name':brand,'category':category,'lat':lat,'lng':lng,'official_url':url,'coordinate_source':SEARCH_PAGE,'benefit_status':'official_eligible'})
    return total,stores,excluded

