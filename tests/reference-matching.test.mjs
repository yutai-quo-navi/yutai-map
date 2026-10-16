import {test} from 'node:test';
import assert from 'node:assert/strict';
import worker from '../cloudflare/worker/src/index.js';
import {fixture,request} from './helpers/search-db.mjs';
function ref(f,id='r'){f.db.prepare(`INSERT INTO reference_stores(issuer_id,store_id,name,address,phone,brand_name,category,updated_at) VALUES('a',?,'Reference','東京都千代田区1','0311112222','Brand','restaurant',?)`).run(id,new Date().toISOString());}
function resolve(f,id='r',addr='東京都千代田区1'){f.db.prepare(`INSERT INTO coordinate_resolutions VALUES('a',?,'Reference',?,'0311112222',35.6812,139.7671,'verified','official_store_map_pin','https://example.com/r','[]',?)`).run(id,addr,new Date().toISOString());}
async function search(f,params={}){const r=await worker.fetch(request(params),f.env);assert.equal(r.status,200);return r.json();}
test('unlocated official rows make zero explicitly incomplete on every page',async()=>{
 const f=fixture();ref(f);f.audit('a');let d=await search(f);assert.equal(d.count,0);assert.equal(d.incomplete,true);assert.equal(d.coverage.unresolved_stores,1);
 for(let i=0;i<31;i++)f.insert('a',String(i),i);f.audit('a');d=await search(f);assert.equal(d.incomplete,true);const p=await search(f,{cursor:d.next_cursor});assert.equal(p.incomplete,true);assert.equal(p.coverage.unresolved_stores,1);f.db.close();
});
test('a verified pin contributes to the same distance set and category totals on all pages',async()=>{
 const f=fixture();ref(f);resolve(f);for(let i=0;i<31;i++)f.insert('a',String(i),100+i);f.audit('a');const d=await search(f);assert.equal(d.incomplete,false);assert.equal(d.results[0].store_id,'r');assert.equal(d.category_counts.all,32);const p=await search(f,{cursor:d.next_cursor});assert.equal(p.count,2);assert.equal(p.incomplete,false);f.db.close();
});
test('identity changes disable an old pin immediately; wrong-address and ambiguous pins are never searched',async()=>{
 const f=fixture();ref(f);resolve(f,'r','東京都千代田区2');f.audit('a');assert.equal((await search(f)).count,0);
 f.db.exec("UPDATE coordinate_resolutions SET address='東京都千代田区1',status='ambiguous'");assert.equal((await search(f)).count,0);
 f.db.exec("UPDATE coordinate_resolutions SET status='verified'");assert.equal((await search(f)).count,1);
 f.db.exec("UPDATE reference_stores SET address='東京都千代田区3'");assert.equal((await search(f)).count,0);f.db.close();
});
test('missing, stale and revised official audits never imply complete search',async()=>{
 const f=fixture();f.insert('a','1');let d=await search(f);assert.equal(d.incomplete,true);assert.deepEqual(d.coverage.unverified_issuers,['a']);f.audit('a');assert.equal((await search(f)).incomplete,false);
 f.db.exec("UPDATE issuer_catalog_audit SET checked_at='2025-01-01T00:00:00Z'");assert.equal((await search(f)).incomplete,true);f.audit('a');f.insert('a','2');assert.equal((await search(f)).incomplete,true);f.db.close();
});
test('no double representation, accurate category-zero totals and no loss at spherical radius boundary',async()=>{
 const f=fixture();ref(f,'same');resolve(f,'same');f.insert('a','same',10,'cafe');f.insert('a','edge',29999.99);f.insert('a','outside',30000.1);f.audit('a');
 const d=await search(f,{radius:'30000'});assert.equal(d.category_counts.all,2);assert.deepEqual(d.results.map(r=>r.store_id),['same','edge']);
 const z=await search(f,{radius:'30000',category:'bakery'});assert.equal(z.count,0);assert.equal(z.category_counts.all,2);assert.equal(z.next_cursor,null);f.db.close();
});
