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

test('cache outage falls back to D1 and failed loads are never cached',async()=>{
 const old=globalThis.caches;let reads=0,puts=0;globalThis.caches={default:{match:async()=>{throw Error('down');},put:async()=>{puts++;throw Error('down');}}};
 try{assert.equal(await cachedData('a',300,async()=>++reads),1);assert.equal(await cachedData('a',300,async()=>++reads),2);
  await assert.rejects(cachedData('b',300,async()=>{throw Error('db failed');}));assert.equal(puts,2);
 }finally{globalThis.caches=old;}
});
