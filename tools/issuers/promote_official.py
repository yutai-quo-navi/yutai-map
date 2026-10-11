"""Enable official-coordinate search only after every issuer sync has succeeded."""
import json
from pathlib import Path
NOTES={
'komeda':'公式店舗APIでKOMECA対応を確認した日本国内の店舗を掲載しています。利用条件は券面と公式情報をご確認ください。',
'dnh':'公式店舗検索の「ドトール バリューカード対応」店舗を掲載しています。株主ご優待カードの利用条件は券面と公式情報をご確認ください。星乃珈琲店・洋麺屋五右衛門は対象外です。',
'mos':'モスとミスタードーナツの公式店舗情報・座標を掲載しています。株主優待券は一部対象外店舗があります。利用前に券面・公式情報と店舗で利用条件をご確認ください。'
}
for issuer,note in NOTES.items():
    path=Path(f'data/issuers/{issuer}/config.json');config=json.loads(path.read_text())
    current=json.loads(Path(f'data/issuers/{issuer}/stores/current.json').read_text())
    health=config['health']
    if not health['minStores']<=len(current['stores'])<=health['maxStores']:raise ValueError('Invalid official snapshot')
    config.update(locationMode='official_coordinates',matchingMode='official_store_filter',note=note,showStoreNote=True,catalogBrands=sorted(current['brand_counts']),verified=current['generated_at'][:10])
    if issuer=='mos':config['storeSearchUrl']='https://www.mos.jp/shop/'
    path.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
