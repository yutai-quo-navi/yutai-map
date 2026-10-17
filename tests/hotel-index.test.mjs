import {test} from 'node:test';
import assert from 'node:assert/strict';
import worker from '../cloudflare/worker/src/index.js';
import {snapshotFixture} from './helpers/snapshot-fixture.mjs';
import {issueCursor} from '../cloudflare/worker/src/search-cursor.js';
function fixture(n=77){
 const feature={id:'vision-hotels',section:'hotel',status:'public',availability:'continuous',storeCount:n,indexed:true,stores:[]};
 const rows=Array.from({length:n},(_,i)=>({issuer_id:feature.id,feature_id:feature.id,store_id:String(i).padStart(3,'0'),id:String(i),name:'Hotel '+i,address:'Tokyo',conditions:'Voucher',verified:true,lat:35.68+i*.001,lng:139.76,category:'other'}));
 const snap=snapshotFixture(rows,{features:[feature]});
 const manifest={...snap.manifest,key:snap.manifest.key.replace('search-index','hotel-index')};
 const permit={limit:async()=>({success:true})};
 const env={API_RATE_LIMITER:permit,SEARCH_RATE_LIMITER:permit,SEARCH_COUNTER:{idFromName:x=>x,get:()=>({fetch:async()=>Response.json({success:true})})},DB:{prepare(){assert.fail('Hotel search must never access D1');}},
 SEARCH_INDEX_BUCKET:{get:async key=>{
  if(key==='hotel-index/active.json'){const text=JSON.stringify(manifest);return {size:Buffer.byteLength(text),text:async()=>text};}
  return snap.bucket.get(key.replace('hotel-index','search-index'));
 }}};
 globalThis.caches={default:{match:async()=>null,put:async()=>{}}};
 const request=(p={})=>new Request('https://test/v1/hotels/search?'+new URLSearchParams({lat:35.68,lng:139.76,radius:'all',features:feature.id,...p}));
 return {env,request,rows};
}
test('hotel metadata excludes all facility records; search uses 30+30 and exact full counts',async()=>{
 const f=fixture(),old=globalThis.fetch;globalThis.fetch=()=>assert.fail('External API forbidden');
 try{
 const catalog=await (await worker.fetch(new Request('https://test/v1/hotels/catalog'),f.env)).json();assert.equal(catalog.features[0].storeCount,77);assert.deepEqual(catalog.features[0].stores,[]);
 const first=await (await worker.fetch(f.request(),f.env)).json();assert.equal(first.total,77);assert.equal(first.count,30);
 const second=await (await worker.fetch(f.request({cursor:first.next_cursor}),f.env)).json();assert.equal(second.count,30);assert.equal(second.next_cursor,null);assert.equal(second.limited,true);assert.equal(second.total,77);assert.equal(second.coverage.d1_rows_read,0);
 assert.deepEqual([...first.results,...second.results].map(r=>r.store_id),f.rows.slice(0,60).map(r=>r.store_id));
 const payload=JSON.parse(Buffer.from(first.next_cursor.split('.')[0],'base64url'));
 const third=await issueCursor('fixture-only-snapshot-signing-key-32-characters',{...payload,n:60});
 assert.equal((await worker.fetch(f.request({cursor:third}),f.env)).status,400);
 assert.equal((await worker.fetch(f.request({cursor:first.next_cursor,radius:'100000'}),f.env)).status,400);
 }finally{globalThis.fetch=old;}
});
test('hotel radius, zero, forged selections and rate guards fail without D1 or external calls',async()=>{
 const f=fixture(5);
 const near=await (await worker.fetch(f.request({radius:'100'}),f.env)).json();assert.equal(near.total,1);assert.equal(near.next_cursor,null);
 const zero=await (await worker.fetch(f.request({lat:0,lng:0,radius:'1'}),f.env)).json();assert.equal(zero.total,0);
 assert.equal((await worker.fetch(f.request({features:'wrong'}),f.env)).status,400);
 f.env.API_RATE_LIMITER={limit:async()=>({success:false})};assert.equal((await worker.fetch(f.request(),f.env)).status,429);
});
