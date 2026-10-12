"""Promote the two new issuers only after both verified D1 imports succeeded."""
import json
from pathlib import Path
NOTES = {
    'yamaokaya': '公式店舗情報・座標に基づき、株主優待対象のラーメン山岡家・味噌ラーメン山岡家・煮干しラーメン山岡家を掲載しています。餃子業態は対象外です。券面と公式の利用条件をご確認ください。',
    'chikaranomoto': '力の源の優待対象のうち、一風堂・一風堂 KAY・RAMEN EXPRESS系を公式店舗情報・座標から掲載しています。名島亭・因幡うどんは現在未掲載です。優待カードの利用条件は券面と公式情報をご確認ください。'
}

def promote(issuers=None):
    configs = []
    manifest_path = Path('data/issuers/index.json')
    manifest = json.loads(manifest_path.read_text())
    for issuer in (issuers or list(NOTES)):
        note = NOTES[issuer]
        path = Path(f'data/issuers/{issuer}/config.json')
        config = json.loads(path.read_text())
        current = json.loads(Path(f'data/issuers/{issuer}/stores/current.json').read_text())
        health = config['health']
        if not health['minStores'] <= len(current['stores']) <= health['maxStores'] or any(not s.get('lat') or not s.get('lng') for s in current['stores']):
            raise ValueError('Invalid official snapshot')
        config.update(status='public', locationMode='official_coordinates', matchingMode='official_store_filter', note=note, catalogBrands=sorted(current['brand_counts']), verified=current['generated_at'][:10])
        configs.append((path,config))
        next(x for x in manifest['issuers'] if x['id']==issuer)['status']='public'
    for path,config in configs:
        path.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
    manifest['updated']=max(c['verified'] for _,c in configs)
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')

if __name__ == '__main__':
    promote()
