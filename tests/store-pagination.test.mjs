import {test} from 'node:test';
import assert from 'node:assert/strict';
import worker from '../cloudflare/worker/src/index.js';
import {fixture,request} from './helpers/search-db.mjs';
async function search(f,params={}){const res=await worker.fetch(request(params),f.env);return {status:res.status,data:await res.json(),headers:res.headers};}
test('all 77 stores page 30+30+17 in precise distance order, without duplicates or external requests',async()=>{
 const f=fixture();for(let i=0;i<77;i++)f.insert('a',String(77-i),100+i*.01);f.audit('a');
 const old=globalThis.fetch;globalThis.fetch=()=>assert.fail('Search must never call external APIs');
 try{
  let cursor,ids=[],sizes=[];
  do {const {status,data,headers}=await search(f,{...(cursor?{cursor}:{})});assert.equal(status,200);assert.equal(data.incomplete,false);assert.equal(headers.get('Cache-Control'),'no-store');sizes.push(data.count);ids.push(...data.results.map(r=>r.store_id));cursor=data.next_cursor;assert.equal(data.has_more,!!cursor);}while(cursor);
  assert.deepEqual(sizes,[30,30,17]);assert.deepEqual(ids,Array.from({length:77},(_,i)=>String(77-i)));assert.equal(new Set(ids).size,77);
  assert.ok(f.queries.filter(q=>q.sql.includes('WITH candidates')).every(q=>q.rows<=30));
  const pages=f.queries.filter(q=>q.sql.includes('WITH candidates'));
  assert.ok(pages[0].sql.includes('COUNT(*) AS all_count'));
  assert.ok(pages.slice(1).every(q=>!q.sql.includes('COUNT(*) AS all_count')),
    'signed revision-bound totals must be reused instead of recounting on every page');
 }finally{globalThis.fetch=old;f.db.close();}
});
test('exact multiple of 30 has no phantom next page; equal distances use issuer and store IDs',async()=>{
 const f=fixture();for(let i=0;i<60;i++)f.insert('a',String(i).padStart(3,'0'),1);f.audit('a');
 const first=await search(f),last=await search(f,{cursor:first.data.next_cursor});assert.equal(last.data.count,30);assert.equal(last.data.next_cursor,null);assert.equal(last.data.has_more,false);assert.equal(last.data.results[0].store_id,'030');f.db.close();
});
test('a forged, expired or changed-condition cursor is rejected before database reads',async()=>{
 const f=fixture();for(let i=0;i<31;i++)f.insert('a',String(i),i);f.audit('a');const first=await search(f);const cursor=first.data.next_cursor;
 for(const params of [{cursor:'start'},{cursor:'[0,"a","1"]'},{cursor:cursor.slice(0,-2)+'aa'},{cursor,lat:'35.7'},{cursor,brand:'different'},{cursor,category:'cafe'},{cursor,radius:'5000'},{cursor,issuers:'b'}]){
  const n=f.queries.length;assert.equal((await search(f,params)).status,400);assert.equal(f.queries.length,n);
 }
 const old=Date.now;Date.now=()=>old()+1900*1000;try{assert.equal((await search(f,{cursor})).status,400);}finally{Date.now=old;}f.db.close();
});
test('catalog or coordinate changes invalidate continuation instead of skipping or repeating stores',async()=>{
 const f=fixture();for(let i=0;i<31;i++)f.insert('a',String(i),i);f.audit('a');const first=await search(f);f.insert('a','new',.1);
 const r=await search(f,{cursor:first.data.next_cursor});assert.equal(r.status,409);assert.equal(r.data.error,'catalog_changed');f.db.close();
});
test('signed continuation does not charge a new search; both search and API guards remain enforced',async()=>{
 const f=fixture();for(let i=0;i<77;i++)f.insert('a',String(i),i);f.audit('a');let searches=0,api=0;
 f.env.SEARCH_RATE_LIMITER={limit:async()=>({success:++searches<=1})};f.env.API_RATE_LIMITER={limit:async()=>({success:++api<=3})};
 const first=await search(f),second=await search(f,{cursor:first.data.next_cursor}),third=await search(f,{cursor:second.data.next_cursor});assert.equal(third.status,200);assert.equal(searches,1);
 assert.equal((await search(f,{cursor:first.data.next_cursor})).status,429);assert.equal(api,4);f.db.close();
});
test('all 44 issuers participate, including the final issuer; explicit limit never increases 30 rows',async()=>{
 const f=fixture();const ids=Array.from({length:44},(_,i)=>'company'+i);
 for(const [i,id] of ids.entries()){f.insert(id,String(i),i);f.audit(id);}
 const a=await search(f,{issuers:ids.join(','),limit:'9000'});assert.equal(a.data.count,30);
 const b=await search(f,{issuers:ids.join(','),cursor:a.data.next_cursor});assert.equal(b.data.count,14);assert.ok(b.data.results.some(r=>r.issuer_id==='company43'));f.db.close();
});
