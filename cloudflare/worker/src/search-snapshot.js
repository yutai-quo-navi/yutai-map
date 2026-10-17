import {SpatialIndex} from './spatial-index.js';
// Shared immutable store data only: never user coordinates, selections or results.
const entries=new WeakMap(),MAX_BYTES=24*1024*1024;
const cacheUrl=key=>'https://yutai-map-api.yutaisamurai.workers.dev/__snapshot/'+key;
async function readCached(key){try{return await globalThis.caches?.default?.match(cacheUrl(key));}catch{return null;}}
async function saveCached(key,body,seconds){try{await globalThis.caches?.default?.put(cacheUrl(key),new Response(body,{headers:{'Content-Length':String(body.byteLength??new TextEncoder().encode(body).length),'Cache-Control':'public, max-age='+seconds}}));}catch{/* Caching is optional; correctness never relies on it. */}}
export async function getSearchSnapshot(env,scope='dining'){
 const prefix=scope==='hotel'?'hotel-index':'search-index',MANIFEST_KEY=prefix+'/active.json';
 const bucket=env.SEARCH_INDEX_BUCKET;if(!bucket)throw Error('Search snapshot unavailable');
 let scoped=entries.get(bucket);if(!scoped){scoped=new Map();entries.set(bucket,scoped);}let entry=scoped.get(scope);if(entry?.snapshot&&entry.until>Date.now())return entry.snapshot;
 if(entry?.loading)return entry.loading;
 if(!entry){entry={};scoped.set(scope,entry);}
 entry.loading=(async()=>{
  // At most two R2 GETs per request, including a completely cold cache.
  let cached=await readCached(MANIFEST_KEY),text;
  if(cached){if(Number(cached.headers.get('Content-Length'))>4096)throw Error('Oversized search manifest');text=await cached.text();}
  else{const object=await bucket.get(MANIFEST_KEY);if(!object||object.size>4096)throw Error('Missing search manifest');text=await object.text();await saveCached(MANIFEST_KEY,text,60);}
  const m=JSON.parse(text);
  if(m.version!==1||!/^([a-f0-9]{64})$/.test(m.sha256)||m.key!==`${prefix}/versions/${m.sha256}.bin`||!Number.isSafeInteger(m.size)||m.size<64||m.size>MAX_BYTES)throw Error('Invalid search manifest');
  if(entry.snapshot?.revision===m.sha256){entry.until=Date.now()+30000;return entry.snapshot;}
  cached=await readCached(m.key);let buffer;
  if(cached){if(Number(cached.headers.get('Content-Length'))!==m.size)throw Error('Invalid cached snapshot');buffer=await cached.arrayBuffer();}
  else{const object=await bucket.get(m.key);if(!object||object.size!==m.size||object.customMetadata?.sha256!==m.sha256)throw Error('Invalid search snapshot');buffer=await object.arrayBuffer();if(buffer.byteLength!==m.size)throw Error('Truncated search snapshot');await saveCached(m.key,buffer,86400);}
  if(buffer.byteLength!==m.size)throw Error('Invalid snapshot size');
  const index=new SpatialIndex(buffer);
  if(typeof index.metadata.cursor_signing_key!=='string'||index.metadata.cursor_signing_key.length<32)throw Error('Missing snapshot signing key');
  const snapshot={index,revision:m.sha256};entry.snapshot=snapshot;entry.until=Date.now()+30000;return snapshot;
 })();
 try{return await entry.loading;}finally{entry.loading=null;}
}
