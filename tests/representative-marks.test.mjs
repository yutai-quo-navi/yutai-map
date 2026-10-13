import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {representativeMark} from '../representative-marks.js';

const dining = [
  'skylark','colowide','create','zensho','toridoll','yoshinoya','mcd',
  'monogatari','matsuya','royal','balnibarbi','daiichikosho','fujio','srs',
  'arclands','kineya','saintmarc','chimney','ringerhut','hiday','ichibanya',
  'komeda','dnh','mos','yamaokaya','chikaranomoto','ohsho','joyfull','yossix','foodlife'
];
const hotel = [
  'daiwa-house-hotels','seibu-free-hotels','kyoritsu-hotel-discount',
  'kyoritsu-resort-plan','resol-hotels','sunfrontier-hotels','tosei-hotels',
  'greens-hotels','wealth-hotels','tkp-hotels','vision-hotels','wakita-hotels'
];

test('every currently public dining issuer has a representative brand mark', async()=>{
  const manifest = JSON.parse(await readFile(new URL('../data/issuers/index.json',import.meta.url)));
  const visible = manifest.issuers.filter(x=>x.status==='public').map(x=>x.id);
  assert.deepEqual([...visible].sort(),[...dining].sort());
  for(const id of visible){
    const mark=representativeMark('dining',id);
    assert.ok(mark, id);
    assert.ok(mark.name.length > 1, id);
    assert.match(mark.color,/^#[0-9a-f]{6}$/i);
  }
});

test('every hotel benefit has a unique correctly paired representative brand', async()=>{
  const features=JSON.parse(await readFile(new URL('../data/features/index.json',import.meta.url)));
  const ids=features.features.filter(x=>x.section==='hotel').map(x=>x.id);
  assert.deepEqual([...ids].sort(),[...hotel].sort());
  for(const id of ids) assert.ok(representativeMark('hotel',id)?.name,id);
  assert.equal(representativeMark('hotel','kyoritsu-hotel-discount').name,'dormy inn');
  assert.equal(representativeMark('hotel','kyoritsu-resort-plan').name,'共立リゾート');
});

test('mark fallback is always available without a third-party image',()=>{
  assert.equal(representativeMark('dining','missing'),null);
  assert.equal(representativeMark('hotel','missing'),null);
  for(const id of dining.concat(hotel)){
    const mark=representativeMark(hotel.includes(id)?'hotel':'dining',id);
    assert.ok(mark.name && mark.sub && mark.symbol,'fallback: '+id);
    if(mark.asset)assert.ok(mark.asset.startsWith('./assets/') || mark.asset.startsWith('https://'),mark.asset);
  }
});

test('selected labels are absent but deadline badges stay in both selection views',async()=>{
  const app=await readFile(new URL('../app.js',import.meta.url),'utf8');
  const features=await readFile(new URL('../special-features.js',import.meta.url),'utf8');
  assert.doesNotMatch(app,/state\.textContent='選択中'/);
  assert.doesNotMatch(features,/state\.textContent = '選択中'/);
  assert.match(app,/if\(bubble\) badge\.appendChild\(makeDeadlineBadge\(/);
  assert.match(features,/if \(bubble\) detail\.append\(bubble\)/);
});

test('the restaurant representative marks are not holding-company logos',()=>{
  assert.equal(representativeMark('dining','ichibanya').name,'CoCo壱番屋');
  assert.match(representativeMark('dining','ichibanya').asset,/ES9CSLQUwAAS2Sc/);
  assert.equal(representativeMark('dining','create').name,'磯丸水産');
  assert.equal(representativeMark('dining','colowide').name,'牛角');
  assert.equal(representativeMark('dining','balnibarbi').name,'BALNIBARBI');
  assert.match(decodeURIComponent(representativeMark('dining','chikaranomoto').asset),/Ippudo Logo\.png/);
});

test('optical logo sizing keeps all card heights fixed',async()=>{
  const css=await readFile(new URL('../representative-marks.css',import.meta.url),'utf8');
  for (const id of ['komeda','toridoll','dnh','matsuya','kineya','chikaranomoto','yossix']){
    assert.ok(css.includes('[data-issuer="'+id+'"]'),id);
  }
  assert.match(css,/\.benefit-choice-status\{display:none!important\}/);
});

test('dining and hotel cards use fixed grid heights and accessible name',async()=>{
  const css=await readFile(new URL('../representative-marks.css',import.meta.url),'utf8');
  assert.match(css,/#companyChips[\s\S]*?grid-auto-rows:112px/);
  assert.match(css,/#hotelFeatures \.feature-buttons[\s\S]*?grid-auto-rows:146px/);
  assert.match(css,/pointer-events:none/);
  const js=await readFile(new URL('../representative-marks.js',import.meta.url),'utf8');
  assert.match(js,/setAttribute\('aria-hidden', 'true'\)/);
});


const suppliedLogos = {
  yamaokaya: 'ラーメン山岡家',
  yossix: 'や台ずし',
  srs: '和食さと',
  arclands: 'かつや',
  create: '磯丸水産',
  chimney: 'はなの舞'
};
test('every supplied issuer has an available local image',async()=>{
  for(const [id,brand] of Object.entries(suppliedLogos)){
    const info=representativeMark('dining',id);
    assert.equal(info.name,brand,id);
    assert.ok(info.asset.startsWith('./assets/'),id);
    const bytes=await readFile(new URL('../'+info.asset,import.meta.url));
    assert.ok(bytes.byteLength>0,id);
  }
});
test('sizing rules keep provided image proportions and grid row heights',async()=>{
  const css=await readFile(new URL('../representative-marks.css',import.meta.url),'utf8');
  for(const id of Object.keys(suppliedLogos)){
    assert.match(css,new RegExp('data-issuer="'+id+'"'),id);
  }
  assert.ok(css.includes('.representative-mark-image{object-fit:contain}'));
  assert.match(css,/grid-auto-rows:112px/);
  assert.match(css,/grid-auto-rows:146px/);
});

test('restaurant identities use intrinsic image proportions rather than stretched backgrounds',async()=>{
  for(const id of ['create','fujio','balnibarbi','saintmarc','kineya','ringerhut','daiichikosho','monogatari']){
    const info=representativeMark('dining',id);
    const bytes=await readFile(new URL('../'+info.asset,import.meta.url));
    assert.ok(bytes.length>0,id);
  }
  const js=await readFile(new URL('../representative-marks.js',import.meta.url),'utf8');
  assert.ok(!js.includes('backgroundPosition'));
  const css=await readFile(new URL('../representative-marks.css',import.meta.url),'utf8');
  assert.match(css,/width:auto;\s*height:auto;/);
});

test('hotel logo image sources and selected card behavior are configured',async()=>{
  const imageBacked=[
    'kyoritsu-hotel-discount','greens-hotels','seibu-free-hotels',
    'sunfrontier-hotels','resol-hotels','daiwa-house-hotels',
    'tosei-hotels','tkp-hotels','wealth-hotels','wakita-hotels'
  ];
  for(const id of imageBacked) assert.ok(representativeMark('hotel',id)?.asset,id);
  const css=await readFile(new URL('../representative-marks.css',import.meta.url),'utf8');
  assert.match(css,/grid-auto-rows:146px/);
  assert.match(css,/\.representative-mark-image/);
});
