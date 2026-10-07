import {test} from 'node:test';
import assert from 'node:assert/strict';
import worker from '../cloudflare/worker/src/index.js';

const reference = {
  issuer_id:'colowide', store_id:'official:id:26486',
  name:'ラパウザ 厚別通り店', brand_name:'ラパウザ', category:'restaurant',
  address:'北海道札幌市白石区川下５条４丁目１−１', phone:'011-879-6220'
};
const poi = {
  name:'ラパウザ小麦の家厚別通り店',
  address:'北海道札幌市白石区川下５条４丁目１－１',
  lat:43.053332318, lng:141.445576788
};

async function search(pois, refs=[reference]){
  const oldFetch=globalThis.fetch, oldCaches=globalThis.caches;
  globalThis.fetch=async()=>new Response(JSON.stringify({results:pois}));
  globalThis.caches={default:{match:async()=>undefined}};
  const permit={limit:async()=>({success:true})};
  const env={API_RATE_LIMITER:permit, SEARCH_RATE_LIMITER:permit, DB:{prepare(sql){return {bind(){return {
    first:async()=>({aliases_json:'["ラパウザ"]'}),
    all:async()=>({results:sql.includes('SELECT DISTINCT')?[{issuer_id:'colowide'}]:refs})
  };}};}}};
  try {
    const response=await worker.fetch(new Request('https://api.example.com/v1/stores/search?lat=43.055&lng=141.455&radius=10000&issuers=colowide&category=restaurant'),env);
    assert.equal(response.status,200);
    return await response.json();
  } finally {globalThis.fetch=oldFetch; globalThis.caches=oldCaches;}
}

test('official brand and complete branch match across an inserted name qualifier and address dash forms',async()=>{
  const data=await search([poi]);
  assert.equal(data.count,1);
  assert.equal(data.results[0].store_id,reference.store_id);
  assert.equal(data.results[0].name,reference.name);
  assert.ok(data.results[0].distance<10000);
});

test('split name match requires the full address, full branch and brand in order',async()=>{
  for (const changes of [
    {address:'北海道札幌市白石区川下５条４丁目２－１'},
    {address:'北海道札幌市'},
    {name:'ラパウザ小麦の家厚別店'},
    {name:'ラパウザ小麦の家時計台前店'},
    {name:'小麦の家厚別通り店'},
    {name:'厚別通り店ラパウザ小麦の家'},
    {name:'大戸屋 厚別通り店'},
    {lat:35.68,lng:139.76}
  ]) assert.equal((await search([{...poi,...changes}])).count,0,JSON.stringify(changes));
  assert.equal((await search([poi],[])).count,0);
});

test('existing exact name, name containment and phone matches remain supported',async()=>{
  for(const p of [
    {...poi,name:reference.name},
    {...poi,name:'ラパウザ 厚別通り店（小麦の家）'},
    {...poi,name:'小麦の家',phone:reference.phone}
  ]) assert.equal((await search([p])).count,1);
});

test('same brand at a different branch cannot displace the correct official store',async()=>{
  const other={...reference,store_id:'other',name:'ラパウザ 時計台前店',address:'北海道札幌市中央区北１条西３丁目'};
  const data=await search([poi],[other,reference]);
  assert.deepEqual(data.results.map(s=>s.store_id),[reference.store_id]);
});
