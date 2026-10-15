import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {compareDiningPriority,nearestDeadline,voucherEntriesFromLedger} from '../expiry.js';

test('dining uses deadlines then actual counts; expired Balnibarbi shares undated ordering',()=>{
  const rows=[{id:'tiny',count:10},{id:'balnibarbi',days:-15,count:94},
    {id:'major',count:3000},{id:'today',days:0,count:1},{id:'later',days:136,count:59},
    {id:'near-small',days:46,count:831},{id:'near-large',days:46,count:1229}];
  assert.deepEqual(rows.sort(compareDiningPriority).map(x=>x.id),
    ['today','near-large','near-small','major','balnibarbi','later','tiny']);
});

test('published HTML is already ordered using complete public aggregate counts',async()=>{
  const read=async p=>JSON.parse(await readFile(new URL('../'+p,import.meta.url),'utf8'));
  const issuers=(await read('data/issuers/index.json')).issuers.filter(x=>x.status==='public');
  const counts=await read('data/issuers/store-counts.json');
  const entries=[...(await read('data/voucher-deadlines.json')).entries,
    ...voucherEntriesFromLedger((await read('data/expiry.json')).entries,'利用期限',issuers)];
  const html=await readFile(new URL('../index.html',import.meta.url),'utf8');
  const day=html.match(/data-order-day="([^"]+)"/)[1];
  const now=new Date(day+'T12:00:00+09:00');
  const expected=issuers.map(x=>({id:x.id,days:nearestDeadline(entries,x.id,now)?.days,count:counts[x.id]}))
    .sort((a,b)=>compareDiningPriority(a,b)||a.id.localeCompare(b.id)).map(x=>x.id);
  const region=html.match(/<div id="companyChips"[^>]*>([\s\S]*?)<\/div>/)[1];
  assert.deepEqual([...region.matchAll(/data-issuer="([^"]+)"/g)].map(m=>m[1]),expected);
  assert.equal(expected.length,issuers.length);
});

test('Hikari expiry is the confirmed user supplied electronic dining coupon',async()=>{
 const ledger=JSON.parse(await readFile(new URL('../data/expiry.json',import.meta.url),'utf8'));
 const row=ledger.entries.find(e=>e.issuer_id==='hikari');
 assert.equal(row.expiry_date,'2027-02-28');assert.equal(row.benefit_name,'電子利用クーポン');
 assert.equal(row.category,'dining');assert.equal(row.verification_method,'user');
});

test('a distant Hikari expiry never outranks McDonalds; 60-day boundary matches badges',()=>{
 const rows=[{id:'hikari',days:136,count:59},{id:'mcd',days:167,count:3040},
 {id:'urgent',days:59,count:1},{id:'boundary',days:60,count:100}];
 assert.deepEqual(rows.sort(compareDiningPriority).map(x=>x.id),['urgent','mcd','boundary','hikari']);
});
