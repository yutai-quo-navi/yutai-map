import {test} from 'node:test';
import assert from 'node:assert/strict';
import worker from '../cloudflare/worker/src/index.js';
import {fixture} from './helpers/search-db.mjs';
import {cachedData} from '../cloudflare/worker/src/data-cache.js';
const permit={limit:async()=>({success:true})};
const req=path=>new Request('https://api.example.com'+path);
const counter={idFromName:x=>x,get:()=>({fetch:async()=>Response.json({success:true})})};
function cache(){const entries=new Map();return {match:async r=>entries.get(r.url)?.clone(),put:async(r,v)=>entries.set(r.url,v.clone())};}

test('brand listing uses the immutable snapshot, with zero D1 reads',async()=>{
 const f=fixture();f.insert('a','1');
 const first=await worker.fetch(req('/v1/brands?issuers=a'),f.env);assert.equal(first.status,200);assert.equal((await first.json()).brands[0].count,1);
 f.insert('a','2');const second=await worker.fetch(req('/v1/brands?issuers=a'),f.env);assert.equal((await second.json()).brands[0].count,2);assert.equal(f.queries.length,0);f.db.close();
});

test('cache outage falls back to D1 and failed loads are never cached',async()=>{
 const old=globalThis.caches;let reads=0,puts=0;globalThis.caches={default:{match:async()=>{throw Error('down');},put:async()=>{puts++;throw Error('down');}}};
 try{assert.equal(await cachedData('a',300,async()=>++reads),1);assert.equal(await cachedData('a',300,async()=>++reads),2);
  await assert.rejects(cachedData('b',300,async()=>{throw Error('db failed');}));assert.equal(puts,2);
 }finally{globalThis.caches=old;}
});
