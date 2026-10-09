import {test} from 'node:test';
import assert from 'node:assert/strict';
import worker from '../cloudflare/worker/src/index.js';
import {cachedData} from '../cloudflare/worker/src/data-cache.js';
const permit={limit:async()=>({success:true})};
const req=path=>new Request('https://api.example.com'+path);
const counter={idFromName:x=>x,get:()=>({fetch:async()=>Response.json({success:true})})};
function cache(){const entries=new Map();return {match:async r=>entries.get(r.url)?.clone(),put:async(r,v)=>entries.set(r.url,v.clone())};}

test('brand cache is reused and a revision change loads the new counts',async()=>{
 const old=globalThis.caches;globalThis.caches={default:cache()};
 let revision=0,count=1,reads=0;
 const env={API_RATE_LIMITER:permit,DB:{prepare(sql){return {bind(){return this;},all:async()=>{
  if(sql.includes('FROM issuer_stats')) return {results:[{issuer_id:'a',catalog_revision:revision}]};
  assert.ok(sql.includes('FROM brand_catalog'));reads++;return {results:[{issuer_id:'a',name:'Brand',count}]};
 }}}}};
 try{
  for(let i=0;i<2;i++) assert.equal((await (await worker.fetch(req('/v1/brands?issuers=a'),env)).json()).brands[0].count,1);
  assert.equal(reads,1);revision++;count=2;
  assert.equal((await (await worker.fetch(req('/v1/brands?issuers=a'),env)).json()).brands[0].count,2);assert.equal(reads,2);
 }finally{globalThis.caches=old;}
});

test('reference cache is reused, invalidated on change and does not cache upstream responses',async()=>{
 const old=globalThis.caches,oldFetch=globalThis.fetch;globalThis.caches={default:cache()};
 let revision=0,name='Target',reads=0,upstream=0;
 globalThis.fetch=async()=>{upstream++;return Response.json({results:[]});};
 const env={API_RATE_LIMITER:permit,SEARCH_RATE_LIMITER:permit,SEARCH_COUNTER:counter,DB:{prepare(sql){return {bind(){return this;},all:async()=>{
  if(sql.includes('FROM issuer_stats')) return {results:[{issuer_id:'a',reference_revision:revision,aliases_json:'["Target"]',updated_at:'now'}]};
  if(sql.includes('FROM reference_stores')){reads++;return {results:[{issuer_id:'a',store_id:'1',name}]};}
  return {results:[]};
 }}}}};
 try{
  const path='/v1/stores/search?lat=35&lng=139&radius=10000&issuers=a';
  assert.equal((await worker.fetch(req(path),env)).status,200);
  assert.equal((await worker.fetch(req(path),env)).status,200);assert.equal(reads,1);assert.equal(upstream,2);
  revision++;name='Changed';assert.equal((await worker.fetch(req(path),env)).status,200);assert.equal(reads,2);
 }finally{globalThis.caches=old;globalThis.fetch=oldFetch;}
});

test('one geo read gives all category counts beyond 600 candidates and the nearest 30',async()=>{
 const old=globalThis.caches;globalThis.caches={default:cache()};let geoReads=0;
 const rows=Array.from({length:701},(_,i)=>({issuer_id:'a',store_id:String(i),name:'store',lat:35+i*.00001,lng:139,category:i%2?'cafe':'restaurant'})).reverse();
 const env={API_RATE_LIMITER:permit,SEARCH_RATE_LIMITER:permit,SEARCH_COUNTER:counter,DB:{prepare(sql){return {bind(){return this;},all:async()=>{
  if(sql.includes('FROM issuer_stats'))return {results:[]};
  assert.ok(sql.includes('FROM stores'));assert.ok(!sql.includes('LIMIT'));geoReads++;return {results:rows};
 }}}}};
 try{
  const response=await worker.fetch(req('/v1/stores/search?lat=35&lng=139&radius=10000&issuers=a&category=cafe'),env);
  assert.equal(response.status,200);const data=await response.json();assert.equal(geoReads,1);
  assert.deepEqual(data.category_counts,{restaurant:351,cafe:350,all:701});assert.equal(data.results.length,30);
  assert.deepEqual(data.results.map(x=>x.store_id),Array.from({length:30},(_,i)=>String(i*2+1)));
 }finally{globalThis.caches=old;}
});

test('cache outage falls back to D1 and failed loads are never cached',async()=>{
 const old=globalThis.caches;let reads=0,puts=0;globalThis.caches={default:{match:async()=>{throw Error('down');},put:async()=>{puts++;throw Error('down');}}};
 try{assert.equal(await cachedData('a',300,async()=>++reads),1);assert.equal(await cachedData('a',300,async()=>++reads),2);
  await assert.rejects(cachedData('b',300,async()=>{throw Error('db failed');}));assert.equal(puts,2);
 }finally{globalThis.caches=old;}
});
