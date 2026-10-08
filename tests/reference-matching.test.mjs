import {test} from 'node:test';
import assert from 'node:assert/strict';
import worker from '../cloudflare/worker/src/index.js';
const counterPermit={idFromName:ip=>ip,get:()=>({fetch:async()=>Response.json({success:true})})};

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

async function search(pois, refs=[reference], radius=10000){
  const oldFetch=globalThis.fetch, oldCaches=globalThis.caches;
  globalThis.fetch=async(url)=>{
    assert.equal(new URL(url).searchParams.get('radius'), String(Math.min(radius,30000)));
    return new Response(JSON.stringify({results:pois}));
  };
  globalThis.caches={default:{match:async()=>undefined}};
  const permit={limit:async()=>({success:true})};
  const env={API_RATE_LIMITER:permit, SEARCH_COUNTER:counterPermit, SEARCH_RATE_LIMITER:permit, DB:{prepare(sql){return {bind(){return {
    first:async()=>({aliases_json:'["ラパウザ"]'}),
    all:async()=>({results:sql.includes('SELECT DISTINCT')?[{issuer_id:'colowide'}]:refs})
  };}};}}};
  try {
    const response=await worker.fetch(new Request(`https://api.example.com/v1/stores/search?lat=43.055&lng=141.455&radius=${radius}&issuers=colowide&category=restaurant`),env);
    assert.equal(response.status,200);
    return await response.json();
  } finally {globalThis.fetch=oldFetch; globalThis.caches=oldCaches;}
}

test('30 km search includes a matched store beyond 10 km, excludes beyond 30 km and keeps the result limit',async()=>{
  const distant={...poi,lat:43.255,lng:141.455};
  assert.equal((await search([distant])).count,0);
  const widened=await search([distant], [reference], 30000);
  assert.equal(widened.count,1);
  assert.ok(widened.results[0].distance>10000 && widened.results[0].distance<30000);
  assert.equal(widened.limit,30);
  assert.equal((await search([{...distant,lat:43.405}], [reference], 30000)).count,0);
  assert.equal((await search([{...distant,lat:43.405}], [reference], 50000)).count,0);
});

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

test('a geographic brand cannot fill the shared candidate limit and hide La Pausa',async()=>{
  const oldFetch=globalThis.fetch, oldCaches=globalThis.caches;
  globalThis.caches={default:{match:async()=>undefined}};
  const queries=[];
  const unrelated=Array.from({length:200},(_,i)=>({...poi,name:'無関係な施設'+i}));
  globalThis.fetch=async(url)=>{
    const q=new URL(url).searchParams.get('q');
    queries.push(q);
    return new Response(JSON.stringify({results:q.includes('北海道')?unrelated:[poi]}));
  };
  const permit={limit:async()=>({success:true})};
  const env={API_RATE_LIMITER:permit,SEARCH_COUNTER:counterPermit,SEARCH_RATE_LIMITER:permit,DB:{prepare(sql){return {bind(){return {
    first:async()=>({aliases_json:JSON.stringify(['甘太郎','北海道','ラパウザ','ウルフギャング・パック','ウルフギャング･パック'])}),
    all:async()=>({results:sql.includes('SELECT DISTINCT')?[{issuer_id:'colowide'}]:[reference]})
  };}};}}};
  try {
    const response=await worker.fetch(new Request('https://api.example.com/v1/stores/search?lat=43.06&lng=141.48&radius=10000&issuers=colowide'),env);
    assert.equal(response.status,200);
    const data=await response.json();
    assert.deepEqual(data.results.map(s=>s.store_id),[reference.store_id]);
    assert.ok(queries.includes('北海道'));
    assert.ok(queries.some(q=>q.includes('ラパウザ')&&!q.includes('北海道')));
    assert.equal(queries.length,2);
    assert.equal(queries.filter(q=>q.includes('ウルフギャング')).length,1);
  } finally {globalThis.fetch=oldFetch;globalThis.caches=oldCaches;}
});

test('one issuer returns both official coordinates and matched references with correct counts',async()=>{
  const oldFetch=globalThis.fetch, oldCaches=globalThis.caches;
  globalThis.caches={default:{match:async()=>undefined}};
  const located={...reference,issuer_id:'fujio',store_id:'located',name:'公式座標店',lat:43.055,lng:141.456};
  const ref={...reference,issuer_id:'fujio'};
  globalThis.fetch=async()=>Response.json({results:[poi]});
  const permit={limit:async()=>({success:true})};
  const env={API_RATE_LIMITER:permit,SEARCH_COUNTER:counterPermit,SEARCH_RATE_LIMITER:permit,DB:{prepare(sql){return {bind(...args){
    if(sql.includes('FROM stores')) assert.ok(args.includes('fujio'),'mixed issuer must be searched in the coordinate table');
    return {first:async()=>({aliases_json:'["ラパウザ"]'}),all:async()=>({results:
      sql.includes('SELECT DISTINCT') ? [{issuer_id:'fujio'}] :
      sql.includes('FROM reference_stores') ? [ref] :
      sql.includes('FROM stores') ? [located] : []})};
  }};}}};
  try{
    const response=await worker.fetch(new Request('https://api.example.com/v1/stores/search?lat=43.055&lng=141.455&radius=10000&issuers=fujio'),env);
    assert.equal(response.status,200);
    const data=await response.json();
    assert.deepEqual(new Set(data.results.map(s=>s.store_id)),new Set(['located',ref.store_id]));
    assert.equal(data.category_counts.restaurant,2);
    assert.equal(data.category_counts.all,2);
  }finally{globalThis.fetch=oldFetch;globalThis.caches=oldCaches;}
});
