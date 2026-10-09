import {test} from 'node:test';
import assert from 'node:assert/strict';
import worker from '../cloudflare/worker/src/index.js';

const request = path => new Request('https://api.example.com'+path, {headers:{Origin:'https://example.com'}});
test('feature endpoint returns snapshot with CORS and cache headers, independently of normal radius', async () => {
  const snapshot = {id:'balnibarbi-dining',checkedOn:'2026-10-07',stores:[{id:'remote'}]};
  const env = {API_RATE_LIMITER:{limit:async()=>({success:true})},ALLOWED_ORIGIN:'https://example.com',DB:{prepare(sql) {
    assert.equal(sql, 'SELECT payload_json FROM feature_snapshots WHERE feature_id = ?');
    return {bind(id) {assert.equal(id,snapshot.id);return {all:async()=>({results:[{payload_json:JSON.stringify(snapshot)}]})};}};
  }}};
  const response = await worker.fetch(request('/v1/features/balnibarbi-dining'),env);
  assert.equal(response.status,200);
  assert.equal(response.headers.get('Access-Control-Allow-Origin'),'https://example.com');
  assert.equal(response.headers.get('Cache-Control'),'public, max-age=300');
  assert.deepEqual(await response.json(),snapshot);
});
test('feature endpoint rejects unknown datasets and survives missing D1 data', async () => {
  const env = {API_RATE_LIMITER:{limit:async()=>({success:true})},DB:{prepare(){return {bind(){return {all:async()=>({results:[]})};}};}}};
  assert.equal((await worker.fetch(request('/v1/features/private-dataset'),env)).status,404);
  assert.equal((await worker.fetch(request('/v1/features/balnibarbi-dining'),env)).status,503);
});
test('hotel voucher endpoints bind distinct dataset IDs and retain rate limiting', async () => {
  for (const id of ['vision-hotels','wakita-hotels','tkp-hotels','wealth-hotels','greens-hotels','tosei-hotels','sunfrontier-hotels','resol-hotels','seibu-free-hotels','daiwa-house-hotels','kyoritsu-hotel-discount','kyoritsu-resort-plan']) {
    let limited = 0;
    const env = {API_RATE_LIMITER:{limit:async()=>{limited++;return {success:true};}},DB:{prepare(){return {
      bind(actual) {assert.equal(actual,id);return {all:async()=>({results:[{payload_json:JSON.stringify({id,stores:[]})}]})};}
    };}}};
    const response=await worker.fetch(request('/v1/features/'+id),env);
    assert.equal(response.status,200);assert.equal((await response.json()).id,id);assert.equal(limited,1);
  }
});
