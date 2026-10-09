import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import worker, {SearchCounter} from '../cloudflare/worker/src/index.js';

const allowed='https://yutai-quo-navi.github.io';
const request=(path,options={})=>new Request('https://api.example.com'+path,{headers:{Origin:allowed,'CF-Connecting-IP':'192.0.2.10'},...options});
const permit={limit:async()=>({success:true})};
const counterPermit={idFromName:ip=>ip,get:()=>({fetch:async()=>Response.json({success:true})})};
const protectedPaths=['/health','/v1/brands?issuers=colowide','/v1/features/balnibarbi-dining','/v1/stores/search?lat=35.68&lng=139.76&issuers=colowide',
  '/v1/features/kyoritsu-hotel-discount','/v1/features/kyoritsu-resort-plan','/v1/features/daiwa-house-hotels'];

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
  const healthEnv={ALLOWED_ORIGIN:allowed,API_RATE_LIMITER:permit,DB:{prepare(){return {all:async()=>({results:[{stores:1,referenceStores:1}]})};}}};
  const health=await worker.fetch(request('/health',{headers:{'CF-Connecting-IP':'192.0.2.10'}}),healthEnv);
  assert.equal(health.status,200);
  assert.equal(health.headers.get('X-Content-Type-Options'),'nosniff');
  assert.equal(health.headers.get('Cache-Control'),'no-store');
});
test('existing search limit remains a separate guard and prevents upstream queries',async()=>{
  const old=globalThis.caches;
  globalThis.caches={default:{match:async()=>undefined,put:async()=>{}}};
  try{
    const env={API_RATE_LIMITER:permit,SEARCH_COUNTER:counterPermit,SEARCH_RATE_LIMITER:{limit:async()=>({success:false})},DB:{prepare(){assert.fail('DB must not be reached');}}};
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
  const env={API_RATE_LIMITER:permit,SEARCH_COUNTER:counterPermit,SEARCH_RATE_LIMITER:permit,DB:{prepare(sql){return {bind(){return {
    first:async()=>({aliases_json:'["店舗"]'}),
    all:async()=>({results:sql.includes('FROM issuer_stats')?[{issuer_id:'colowide',aliases_json:'["店舗"]'}]:sql.includes('FROM reference_stores')?[{store_id:'test',name:'店舗'}]:[]})
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
    const response=await worker.fetch(request(protectedPaths[3]),{API_RATE_LIMITER:permit,SEARCH_COUNTER:counterPermit,
      SEARCH_RATE_LIMITER:{limit:async()=>{throw new Error('offline');}},DB:{prepare(){assert.fail('DB must not be reached');}}});
    assert.equal(response.status,503);
    assert.equal((await response.json()).error,'rate_limit_unavailable');
  }finally{globalThis.caches=old;}
});

async function withReferenceFixture(aliasGroups, upstream, check, searchLimiter=permit){
  const oldFetch=globalThis.fetch, oldCache=globalThis.caches, oldError=console.error;
  const locks=new Map(), calls=[], dbReads=[];
  globalThis.caches={default:{match:async key=>locks.get(key.url)?.clone(),put:async(key,value)=>{locks.set(key.url,value.clone());}}};
  globalThis.fetch=async(url,options)=>{calls.push({url,options});return upstream(url,options,calls.length);};
  console.error=()=>{};
  const env={API_RATE_LIMITER:permit,SEARCH_COUNTER:counterPermit,SEARCH_RATE_LIMITER:searchLimiter,DB:{prepare(sql){
    dbReads.push(sql);
    return {args:[],bind(...args){this.args=args;return this;},
      async first(){return {aliases_json:JSON.stringify(aliasGroups[this.args[0]] || [])};},
      async all(){return {results:sql.includes('FROM issuer_stats')
        ? Object.keys(aliasGroups).filter(id=>this.args.includes(id)).map(issuer_id=>({issuer_id,aliases_json:JSON.stringify(aliasGroups[issuer_id])}))
        : sql.includes('FROM reference_stores\n')
          ? [{issuer_id:this.args[0],store_id:'target',name:'Target Store',address:'東京都千代田区',brand_name:'Target',category:'restaurant'}]
          : []};}
    };
  }}};
  try{await check({env,calls,dbReads});}
  finally{globalThis.fetch=oldFetch;globalThis.caches=oldCache;console.error=oldError;}
}

const syntheticAliases=(count,prefix='brand')=>Array.from({length:count},(_,i)=>`${prefix}${i}`);
const emptyUpstream=()=>new Response(JSON.stringify({results:[]}));
const referenceRequest=(issuers='colowide',options={})=>request(`/v1/stores/search?lat=35.681236&lng=139.767125&radius=10000&issuers=${issuers}`,options);

test('the configured ten-per-minute guard blocks the eleventh search for both manual clients and bots',async()=>{
  const config=readFileSync(new URL('../cloudflare/wrangler.toml',import.meta.url),'utf8');
  const searchConfig=config.split('name = "SEARCH_RATE_LIMITER"')[1].split('[[ratelimits]]')[0];
  assert.match(searchConfig,/limit = 10\b/);
  assert.match(searchConfig,/period = 60\b/);
  let limiterCalls=0;
  const limiter={limit:async({key})=>{assert.equal(key,'192.0.2.10');return {success:++limiterCalls<=10};}};
  await withReferenceFixture({colowide:['Target']},emptyUpstream,async({env,calls,dbReads})=>{
    for(let i=0;i<10;i++){
      const response=await worker.fetch(referenceRequest('colowide',{headers:{'CF-Connecting-IP':'192.0.2.10','User-Agent':i%2?'audit-bot':'Mozilla/5.0'}}),env);
      assert.equal(response.status,200);
    }
    const reads=dbReads.length;
    for(const agent of ['audit-bot','Mozilla/5.0']){
      const response=await worker.fetch(referenceRequest('colowide',{headers:{'CF-Connecting-IP':'192.0.2.10','User-Agent':agent}}),env);
      assert.equal(response.status,429);
      assert.equal(response.headers.get('Retry-After'),'60');
      assert.equal(response.headers.get('Cache-Control'),'no-store');
      assert.match((await response.json()).message,/しばらくお待ちください/);
      assert.equal(dbReads.length,reads);
      assert.equal(calls.length,10);
    }
    assert.equal(limiterCalls,11,'the cached lock blocks the twelfth search before another limiter call');
  },limiter);
});

test('the OpenPOI budget applies to all selected issuers and accepts its boundary',async()=>{
  await withReferenceFixture({colowide:syntheticAliases(280),other:syntheticAliases(280,'other')},emptyUpstream,async({env,calls})=>{
    assert.equal((await worker.fetch(referenceRequest('colowide,other'),env)).status,200);
    assert.equal(calls.length,40);
    for(const {url,options} of calls){
      assert.equal(new URL(url).origin,'https://api.openpoiapi.com');
      assert.equal(options.redirect,'manual');
      assert.ok(options.signal instanceof AbortSignal);
    }
  });
});

test('an oversized aggregate OpenPOI plan stops before making any upstream request',async()=>{
  await withReferenceFixture({colowide:syntheticAliases(294),other:syntheticAliases(280,'other')},emptyUpstream,async({env,calls})=>{
    const response=await worker.fetch(referenceRequest('colowide,other'),env);
    assert.equal(response.status,502);
    assert.deepEqual(await response.json(),{error:'search_failed'});
    assert.equal(calls.length,0);
  });
});

test('upstream outages, redirects and malformed replies return failure without retry or false zero results',async()=>{
  for(const upstream of [()=>new Response('',{status:429}),()=>{throw new TypeError('redirect refused');},()=>new Response('{}')]){
    await withReferenceFixture({colowide:['Target']},upstream,async({env,calls})=>{
      const response=await worker.fetch(referenceRequest(),env);
      assert.equal(response.status,502);
      assert.deepEqual(await response.json(),{error:'search_failed'});
      assert.equal(calls.length,1);
    });
  }
});

test('valid empty replies and partial upstream failures retain their existing behavior',async()=>{
  await withReferenceFixture({colowide:syntheticAliases(15)},(_url,_options,call)=>call===1
    ? new Response('',{status:503})
    : new Response(JSON.stringify({results:[{name:'Target Store',address:'東京都千代田区',lat:35.681236,lng:139.767125}]})),async({env,calls})=>{
      const response=await worker.fetch(referenceRequest(),env);
      assert.equal(response.status,200);
      assert.equal((await response.json()).count,1);
      assert.equal(calls.length,2);
  });
});

function counterStorage(){
  const values=new Map();
  return {values,alarmTime:null,kv:{get:key=>structuredClone(values.get(key)),put:(key,value)=>values.set(key,structuredClone(value))},
    transactionSync:fn=>fn(),async setAlarm(time){this.alarmTime=time;},async deleteAll(){values.clear();this.alarmTime=null;}};
}

test('the shared counter permits ten concurrent requests and keeps the limit after object recreation',async()=>{
  const storage=counterStorage();
  const counter=new SearchCounter({storage});
  const replies=await Promise.all(Array.from({length:16},()=>counter.fetch().then(r=>r.json())));
  assert.equal(replies.filter(r=>r.success).length,10);
  assert.equal(replies.filter(r=>!r.success).length,6);
  assert.equal((await (await new SearchCounter({storage}).fetch()).json()).success,false);
  assert.equal(storage.values.get('times').length,10);
});

test('the shared counter uses a rolling minute across clock boundaries and expires its data',async()=>{
  const oldNow=Date.now;
  let now=59_000;
  Date.now=()=>now;
  const storage=counterStorage(),counter=new SearchCounter({storage});
  try{
    for(let i=0;i<10;i++) assert.equal((await (await counter.fetch()).json()).success,true);
    for(now of [60_001,118_999]) assert.equal((await (await counter.fetch()).json()).success,false);
    await counter.alarm();
    assert.equal(storage.values.size,1);
    assert.equal(storage.alarmTime,119_000);
    now=119_000;
    await counter.alarm();
    assert.equal(storage.values.size,0);
    assert.equal((await (await counter.fetch()).json()).success,true);
  }finally{Date.now=oldNow;}
});

test('a shared-counter rejection or outage stops searches before SQL and never falls back to unlimited access',async()=>{
  const oldCache=globalThis.caches;
  globalThis.caches={default:{match:async()=>undefined,put:async()=>{}}};
  try{
    const db={prepare(){assert.fail('shared counter must stop SQL');}};
    for(const [counter,status] of [[undefined,503],
      [{idFromName:ip=>ip,get:()=>({fetch:async()=>Response.json({success:false})})},429],
      [{idFromName:ip=>ip,get:()=>({fetch:async()=>new Response('',{status:503})})},503],
      [{idFromName:ip=>ip,get:()=>({fetch:async()=>{throw new Error('unavailable');}})},503]]){
      const response=await worker.fetch(referenceRequest(),{API_RATE_LIMITER:permit,SEARCH_RATE_LIMITER:permit,SEARCH_COUNTER:counter,DB:db});
      assert.equal(response.status,status);
      if(status===429) assert.match((await response.json()).message,/しばらくお待ちください/);
    }
  }finally{globalThis.caches=oldCache;}
});
