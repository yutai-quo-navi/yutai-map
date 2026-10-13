import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {representativeMark} from '../representative-marks.js';
const html = await readFile(new URL('../index.html',import.meta.url),'utf8');
const manifest = JSON.parse(await readFile(new URL('../data/issuers/index.json',import.meta.url)));
const features = JSON.parse(await readFile(new URL('../data/features/index.json',import.meta.url)));
test('the first HTML response contains every public dining logo before asynchronous issuer data',async()=>{
  const region = html.match(/<div id="companyChips"[\s\S]*?<\/div>\s*<\/div>/)?.[0];
  assert.ok(region,'static dining card markup');
  for(const issuer of manifest.issuers.filter(x=>x.status==='public')){
    assert.match(region,new RegExp('data-issuer="'+issuer.id+'"'),'missing first-paint issuer '+issuer.id);
    const mark=representativeMark('dining',issuer.id);
    const file=mark.spriteIndex!=null?'./assets/logo-sprite-cell-'+mark.spriteIndex+'.webp':mark.asset;
    if(file){
      assert.ok(region.includes('src="'+file+'"'),issuer.id);
      const bytes=await readFile(new URL('../'+file,import.meta.url));
      assert.ok(bytes.length>0,issuer.id);
    }
  }
});
test('hotel logos already exist in HTML, but defer their network load until needed',async()=>{
  const start=html.indexOf('<section id="hotelFeatures"');
  const end=html.indexOf('</section>',start);
  assert.ok(start>0&&end>start);
  const cards=html.slice(start,end);
  for(const feature of features.features.filter(x=>x.section==='hotel'&&x.status==='public')){
    assert.ok(cards.includes('data-feature="'+feature.id+'"'),feature.id);
  }
  assert.match(cards,/loading="lazy"/);
});
test('logo card hydration reuses server rendered images instead of recreating them',async()=>{
  const app=await readFile(new URL('../app.js',import.meta.url),'utf8');
  const hotel=await readFile(new URL('../special-features.js',import.meta.url),'utf8');
  assert.match(app,/initialIssuerButtons/);
  assert.match(app,/logoCardHydrated/);
  assert.match(app,/existingGroups = new Map/);
  assert.match(hotel,/existingItems = new Map/);
  assert.match(hotel,/logoCardHydrated/);
});
