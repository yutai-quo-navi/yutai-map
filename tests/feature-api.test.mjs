import {test} from 'node:test';
import assert from 'node:assert/strict';
import worker from '../cloudflare/worker/src/index.js';

const request = path => Object.assign(new Request('https://api.example.com'+path, {headers:{Origin:'https://example.com'}}),{cf:{country:'JP'}});
test('feature endpoint returns snapshot with CORS and cache headers, independently of normal radius', async () => {
  const snapshot = {id:'balnibarbi-dining',checkedOn:'2026-10-07',stores:[{id:'remote'}]};
  const env = {API_RATE_LIMITER:{limit:async()=>({success:true})},ALLOWED_ORIGIN:'https://example.com',DB:{prepare(sql) {
    assert.equal(sql, 'SELECT payload_json FROM feature_snapshots WHERE feature_id = ?');
    return {bind(id) {assert.equal(id,snapshot.id);return {first:async()=>({payload_json:JSON.stringify(snapshot)})};}};
  }}};
  const response = await worker.fetch(request('/v1/features/balnibarbi-dining'),env);
  assert.equal(response.status,200);
  assert.equal(response.headers.get('Access-Control-Allow-Origin'),'https://example.com');
  assert.equal(response.headers.get('Cache-Control'),'public, max-age=300');
  assert.deepEqual(await response.json(),snapshot);
});
test('feature endpoint rejects unknown datasets and survives missing D1 data', async () => {
  const env = {API_RATE_LIMITER:{limit:async()=>({success:true})},DB:{prepare(){return {bind(){return {first:async()=>null};}};}}};
  assert.equal((await worker.fetch(request('/v1/features/private-dataset'),env)).status,404);
  assert.equal((await worker.fetch(request('/v1/features/balnibarbi-dining'),env)).status,503);
});
