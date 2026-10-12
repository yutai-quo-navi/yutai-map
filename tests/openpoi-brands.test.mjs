import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync(new URL('../app.js',import.meta.url),'utf8');
const functions=['classify','normalize','haversine'].map(name=>{
 const start=source.indexOf(`function ${name}(`),end=source.indexOf('\nfunction ',start+1);
 return source.slice(start,end<0?undefined:end);
}).join('\n');
const context=vm.createContext({});vm.runInContext(functions,context);
const configs=Object.fromEntries(['komeda','dnh','mos'].map(id=>[id,JSON.parse(fs.readFileSync(new URL(`../data/issuers/${id}/config.json`,import.meta.url)))]));
const origin={lat:35.68,lng:139.76};
const match=(id,name,extra={})=>context.classify({name,...origin,...extra},configs[id],origin);
test('published issuer manifest and configured catalogs are consistent',()=>{
 const index=JSON.parse(fs.readFileSync(new URL('../data/issuers/index.json',import.meta.url)));
 for(const [id,c] of Object.entries(configs)){
  assert.equal(index.issuers.find(x=>x.id===id)?.status,'public');
  assert.ok(['openpoi','official_coordinates'].includes(c.locationMode));
  assert.ok(c.health.requireCoordinates);
  for(const alias of c.aliases){assert.ok(c.aliasBrands[alias]);assert.ok(c.categories[alias]);}
  assert.ok(c.poiSearchNames.every(q=>!q.includes(' ')));
 }
});
test('Komeda variants retain the canonical brand for catalog filtering',()=>{
 for(const [name,brand] of [['コメダ珈琲 新宿店','コメダ珈琲店'],['Komeda Coffee Nagoya','コメダ珈琲店'],['KOMEDA is □ 東銀座店','KOMEDA is □'],['ADEMOK 南風原店','BAKERY ADEMOK'],['おかげ庵 横浜店','おかげ庵']]) assert.equal(match('komeda',name)?.matchedAlias,brand);
});
test('Doutor supported formats resolve correctly and NRS brands are rejected',()=>{
 for(const [name,brand] of [['エクセルシオールカフェ 渋谷','エクセルシオール カフェ'],['Doutor Coffee Shop Tokyo','ドトールコーヒーショップ'],['ル・カフェ ドトール 銀座店','ル・カフェ ドトール'],['ドトール珈琲農園 町田店','ドトール珈琲農園'],['ドトールキッチン 金井店','ドトールキッチン']]) assert.equal(match('dnh',name)?.matchedAlias,brand);
 for(const name of ['星乃珈琲店','洋麺屋五右衛門','神乃珈琲','カフェ コロラド']) assert.equal(match('dnh',name),null);
});
test('specific MOS formats beat parent names and Mister Donut is included',()=>{
 for(const [name,brand] of [['MOS BURGER 東京店','モスバーガー'],['Mother Leaf Tea Style 横浜店','マザーリーフティースタイル'],['マザーリーフティースタイル 新宿店','マザーリーフティースタイル'],['玄米食堂あえん','玄米食堂あえん'],['Mister Donut 東京店','ミスタードーナツ']]) assert.equal(match('mos',name)?.matchedAlias,brand);
});
test('non-Japanese and invalid coordinates cannot become benefit stores',()=>{
 for(const id of Object.keys(configs)){
  const name=configs[id].catalogBrands[0];
  assert.equal(match(id,name,{country:'US'}),null);
  assert.equal(match(id,name,{lat:'invalid'}),null);
  assert.ok(match(id,name,{country:'JP'}));
 }
});

test('Yamaokaya fallback distinguishes eligible ramen brands and excludes gyoza',()=>{
 const config=JSON.parse(fs.readFileSync(new URL('../data/issuers/yamaokaya/config.json',import.meta.url)));
 const classify=name=>context.classify({name,...origin,country:'JP'},config,origin);
 for(const [name,brand] of [['山岡家 青梅店','ラーメン山岡家'],['味噌ラーメン山岡家 すすきの店','味噌ラーメン山岡家'],['煮干しラーメン山岡家 荒川沖店','煮干しラーメン山岡家']]) assert.equal(classify(name)?.matchedAlias,brand);
 for(const name of ['餃子の山岡家 すすきの店','餃子山岡家','一蘭']) assert.equal(classify(name),null);
});
