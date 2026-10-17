import {test} from 'node:test';
import assert from 'node:assert/strict';
import worker from '../cloudflare/worker/src/index.js';
test('retired full catalogs never access D1 and remain rate limited',async()=>{
 for(const id of ['balnibarbi-dining','vision-hotels','wakita-hotels','tkp-hotels','wealth-hotels','greens-hotels','tosei-hotels','sunfrontier-hotels','resol-hotels','seibu-free-hotels','daiwa-house-hotels','kyoritsu-hotel-discount','kyoritsu-resort-plan']){
  let calls=0;const env={API_RATE_LIMITER:{limit:async()=>({success:++calls<2})},DB:{prepare(){assert.fail('No legacy D1 access');}}};
  const request=()=>new Request('https://test/v1/features/'+id);
  assert.equal((await worker.fetch(request(),env)).status,410);assert.equal((await worker.fetch(request(),env)).status,429);
 }
 assert.equal((await worker.fetch(new Request('https://test/v1/features/unknown'),{})).status,404);
});
