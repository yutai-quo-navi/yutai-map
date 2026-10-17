import {test} from 'node:test';
import assert from 'node:assert/strict';
import worker from '../cloudflare/worker/src/index.js';
import {fixture} from './helpers/search-db.mjs';
const req=path=>new Request('https://api.example.com'+path);

test('brand listing uses the immutable snapshot, with zero D1 reads',async()=>{
 const f=fixture();f.insert('a','1');
 const first=await worker.fetch(req('/v1/brands?issuers=a'),f.env);assert.equal(first.status,200);assert.equal((await first.json()).brands[0].count,1);
 f.insert('a','2');const second=await worker.fetch(req('/v1/brands?issuers=a'),f.env);assert.equal((await second.json()).brands[0].count,2);assert.equal(f.queries.length,0);f.db.close();
});

