"""Promote the new issuers only after their verified D1 imports succeed."""
import json
from pathlib import Path
NOTES = {'ohsho': '公式店舗情報・座標に基づき、国内の餃子の王将・GYOZA OHSHO・JoyNahoを掲載しています。優待電子チケットの利用条件は公式情報をご確認ください。', 'joyfull': 'ジョイフルの国内店舗を公式店舗情報・座標から掲載しています。優待対象の喜楽や・並木街珈琲・二五十・キッチンジローは現在未掲載です。割引券とお食事券は併用できません。'}

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
