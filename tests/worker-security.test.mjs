import {test} from 'node:test';
import assert from 'node:assert/strict';
import worker from '../cloudflare/worker/src/index.js';

const allowed='https://yutai-quo-navi.github.io';
const request=(path,options={})=>new Request('https://api.example.com'+path,{headers:{Origin:allowed,'CF-Connecting-IP':'192.0.2.10'},...options});
const permit={limit:async()=>({success:true})};
const protectedPaths=['/health','/v1/brands?issuers=colowide','/v1/features/balnibarbi-dining','/v1/stores/search?lat=35.68&lng=139.76&issuers=colowide'];

test('every database endpoint stops a limited IP before any DB read',async()=>{
  for(const path of protectedPaths){
    let calls=0;
    const env={ALLOWED_ORIGIN:allowed,API_RATE_LIMITER:{limit:async({key})=>{assert.equal(key,'192.0.2.10');calls++;return {success:false};}},DB:{prepare(){assert.fail('DB must not be reached');}}};
    const response=await worker.fetch(request(path),env);
    assert.equal(response.status,429);
    assert.equal(response.headers.get('Retry-After'),'60');
    assert.equal(response.headers.get('Cache-Control'),'no-store');
    assert.equal(calls,1);
  }
});
test('missing or failed rate-limit binding closes access instead of allowing unlimited DB reads',async()=>{
  for(const API_RATE_LIMITER of [undefined,{limit:async()=>{throw new Error('unavailable');}}]){
    const response=await worker.fetch(request('/health'),{API_RATE_LIMITER,DB:{prepare(){assert.fail('DB must not be reached');}}});
    assert.equal(response.status,503);
    assert.equal((await response.json()).error,'rate_limit_unavailable');
  }
});
test('foreign browser origins, writes and oversized URLs are rejected before rate limit or DB work',async()=>{
  const env={ALLOWED_ORIGIN:allowed,API_RATE_LIMITER:{limit(){assert.fail('Limiter must not be reached');}},DB:{prepare(){assert.fail('DB must not be reached');}}};
  assert.equal((await worker.fetch(request('/health',{headers:{Origin:'https://evil.example'}}),env)).status,403);
  assert.equal((await worker.fetch(request('/health',{method:'POST'}),env)).status,405);
  assert.equal((await worker.fetch(request('/health?x='+'a'.repeat(2100)),env)).status,414);
  assert.equal((await worker.fetch(request('/health',{method:'OPTIONS'}),env)).status,204);
});
test('missing, empty and hostile coordinates cannot reach SQL; health checks without Origin stay supported',async()=>{
  const env={API_RATE_LIMITER:permit,DB:{prepare(){assert.fail('invalid input must not reach SQL');}}};
  for(const query of ['issuers=colowide','lat=&lng=0&issuers=colowide','lat=NaN&lng=0&issuers=colowide','lat=91&lng=0&issuers=colowide','lat=0&lng=181&issuers=colowide','lat=0&lng=0&radius=-1&issuers=colowide']){
    assert.equal((await worker.fetch(request('/v1/stores/search?'+query),env)).status,400);
  }
  const healthEnv={ALLOWED_ORIGIN:allowed,API_RATE_LIMITER:permit,DB:{prepare(){return {first:async()=>({count:1})};}}};
  const health=await worker.fetch(request('/health',{headers:{'CF-Connecting-IP':'192.0.2.10'}}),healthEnv);
  assert.equal(health.status,200);
  assert.equal(health.headers.get('X-Content-Type-Options'),'nosniff');
  assert.equal(health.headers.get('Cache-Control'),'no-store');
});
test('existing search limit remains a separate guard and prevents upstream queries',async()=>{
  const old=globalThis.caches;
  globalThis.caches={default:{match:async()=>undefined,put:async()=>{}}};
  try{
    const env={API_RATE_LIMITER:permit,SEARCH_RATE_LIMITER:{limit:async()=>({success:false})},DB:{prepare(){assert.fail('DB must not be reached');}}};
    const response=await worker.fetch(request(protectedPaths[3]),env);
    assert.equal(response.status,429);
    assert.equal(response.headers.get('Retry-After'),'60');
    assert.equal((await response.json()).retry_after,60);
  }finally{globalThis.caches=old;}
});
test('reference matching uses a fixed upstream destination and a timeout signal',async()=>{
  const oldCache=globalThis.caches,oldFetch=globalThis.fetch;
  globalThis.caches={default:{match:async()=>undefined}};
  let fetched=false;
  globalThis.fetch=async(url,options)=>{
    assert.equal(new URL(url).origin,'https://api.openpoiapi.com');
    assert.ok(options.signal instanceof AbortSignal);
    fetched=true;
    return new Response(JSON.stringify({results:[]}));
  };
  const env={API_RATE_LIMITER:permit,SEARCH_RATE_LIMITER:permit,DB:{prepare(sql){return {bind(){return {
    first:async()=>({aliases_json:'["店舗"]'}),
    all:async()=>({results:sql.includes('SELECT DISTINCT')?[{issuer_id:'colowide'}]:[{store_id:'test',name:'店舗'}]})
  };}};}}};
  try{
    assert.equal((await worker.fetch(request(protectedPaths[3]),env)).status,200);
    assert.equal(fetched,true);
  }finally{globalThis.caches=oldCache;globalThis.fetch=oldFetch;}
});

test('search limiter failure also stops DB reads without an unhandled exception',async()=>{
  const old=globalThis.caches;
  globalThis.caches={default:{match:async()=>undefined}};
  try{
    const response=await worker.fetch(request(protectedPaths[3]),{API_RATE_LIMITER:permit,
      SEARCH_RATE_LIMITER:{limit:async()=>{throw new Error('offline');}},DB:{prepare(){assert.fail('DB must not be reached');}}});
    assert.equal(response.status,503);
    assert.equal((await response.json()).error,'rate_limit_unavailable');
  }finally{globalThis.caches=old;}
});
