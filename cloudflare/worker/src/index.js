export {SearchCounter} from './search-counter.js';
import {hotelCatalog,searchHotels} from './hotel-search.js';
import {searchSnapshot} from './spatial-search.js';
import {getSearchSnapshot} from './search-snapshot.js';

const FEATURE_IDS = new Set(['vision-hotels','wakita-hotels','tkp-hotels','wealth-hotels','greens-hotels','tosei-hotels','sunfrontier-hotels','resol-hotels','seibu-free-hotels', 'daiwa-house-hotels', 'balnibarbi-dining', 'kyoritsu-hotel-discount', 'kyoritsu-resort-plan']);
const MAX_RADIUS = 30000;
const SEARCH_LOCK_SECONDS = 60;
const API_RETRY_SECONDS = 60;
const MAX_REQUEST_URL_LENGTH = 2048;

export default {
  async fetch(request, env) {
    return handleRequest(request, env);
  }
};

async function handleRequest(request, env) {
    const url = new URL(request.url);
    const cors = corsHeaders(env, request);

    const origin = request.headers.get('Origin');
    if (origin && env.ALLOWED_ORIGIN && env.ALLOWED_ORIGIN !== '*' && origin !== env.ALLOWED_ORIGIN)
      return json({error:'origin_not_allowed'},403,cors);
    if (request.url.length > MAX_REQUEST_URL_LENGTH) return json({error:'request_too_long'},414,cors);

    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
    if (request.method !== 'GET') return json({ error: 'method_not_allowed' }, 405, cors);

    const databasePath = ['/health','/v1/brands','/v1/stores/search','/v1/hotels/catalog','/v1/hotels/search'].includes(url.pathname) || FEATURE_IDS.has(url.pathname.replace(/^\/v1\/features\//, ''));
    if (databasePath) {
      const limited = await enforceApiRateLimit(env, request, cors);
      if (limited) return limited;
    }

    if (url.pathname === '/health') {
      try {
        const {index}=await getSearchSnapshot(env);
        return json({ok:true,...index.metadata.health,search_engine:'spatial_index',d1_search_rows:0},200,cors);
      } catch (error) {
        return json({ ok: false, error: 'db_unavailable' }, 503, cors);
      }
    }

    if(url.pathname==='/v1/hotels/catalog'){
      try{return json(await hotelCatalog(env),200,{...cors,'Cache-Control':'public, max-age=300'});}
      catch{return json({error:'hotel_index_unavailable'},503,cors);}
    }
    if(url.pathname==='/v1/hotels/search'){
      const features=parseIssuers(url.searchParams.get('features'));
      const lat=Number(url.searchParams.get('lat')),lng=Number(url.searchParams.get('lng'));
      const rawRadius=url.searchParams.get('radius'),radius=rawRadius==='all'?'all':Number(rawRadius);
      if(!url.searchParams.get('lat')?.trim()||!url.searchParams.get('lng')?.trim()||!Number.isFinite(lat)||!Number.isFinite(lng)||Math.abs(lat)>90||Math.abs(lng)>180||
         !(radius==='all'||Number.isFinite(radius)&&radius>0&&radius<=4000000)||!features.length)
        return json({error:'invalid_hotel_search'},400,cors);
      const requestedCursor=url.searchParams.get('cursor');
      if(requestedCursor===null){try{const limited=await enforceSearchRateLimit(env,request,cors);if(limited)return limited;}catch{return json({error:'rate_limit_unavailable'},503,cors);}}
      try{const result=await searchHotels(env,{lat,lng,radius,features,requestedCursor});return json(result.body,result.status,cors);}
      catch{return json({error:'hotel_index_unavailable'},503,cors);}
    }
    if(url.pathname.startsWith('/v1/features/'))return json({error:'use_indexed_search'},FEATURE_IDS.has(url.pathname.slice('/v1/features/'.length))?410:404,cors);

    if (url.pathname === '/v1/brands') {
      const ids=parseIssuers(url.searchParams.get('issuers'));
      if(!ids.length) return json({brands:[]},200,cors);
      try {
        const {index}=await getSearchSnapshot(env);
        return json({brands:index.metadata.brands.filter(r=>ids.includes(r.issuer_id))},200,{...cors,'Cache-Control':'public, max-age=300'});
      } catch { return json({error:'brands_unavailable'},503,cors); }
    }

    if (url.pathname !== '/v1/stores/search') return json({ error: 'not_found' }, 404, cors);

    const rawLat = url.searchParams.get('lat'), rawLng = url.searchParams.get('lng');
    if (!rawLat?.trim() || !rawLng?.trim()) return json({error:'invalid_coordinates'},400,cors);
    const lat = Number(rawLat);
    const lng = Number(rawLng);
    const radius = Math.min(Number(url.searchParams.get('radius') || 3000), MAX_RADIUS);
    const issuers = parseIssuers(url.searchParams.get('issuers'));
    const requestedCursor = url.searchParams.get('cursor');
    const brand=(url.searchParams.get('brand') || '').trim().slice(0,200);
    const requestedCategory = (url.searchParams.get('category') || '').trim();
    const category = ['restaurant','cafe','bakery','foodcourt','other'].includes(requestedCategory)
      ? requestedCategory : '';

    if (!Number.isFinite(lat) || !Number.isFinite(lng) || lat < -90 || lat > 90 || lng < -180 || lng > 180)
      return json({ error: 'invalid_coordinates' }, 400, cors);
    if (!Number.isFinite(radius) || radius <= 0)
      return json({ error: 'invalid_radius' }, 400, cors);
    if (!issuers.length) return json({ results: [], count: 0 }, 200, cors);

    if(requestedCursor === null) {
      try {
        const limited=await enforceSearchRateLimit(env,request,cors);
        if(limited)return limited;
      } catch {return json({error:'rate_limit_unavailable'},503,cors);}
    }
    try {
      const result=await searchSnapshot(env,{lat,lng,radius,issuers,brand,category,requestedCursor});
      return json(result.body,result.status,{...cors,'Cache-Control':'no-store'});
    } catch {
      return json({error:'search_index_unavailable',message:'店舗検索データを読み込めませんでした。時間をおいて再検索してください。'},503,cors);
    }
}

async function enforceApiRateLimit(env, request, cors){
  if (!env.API_RATE_LIMITER) return json({error:'rate_limit_unavailable'},503,cors);
  try {
    const ip = request.headers.get('CF-Connecting-IP') || 'unknown';
    const {success} = await env.API_RATE_LIMITER.limit({key:ip});
    if (success) return null;
    return json({error:'rate_limited',message:'短時間にアクセスが集中しています。少し待ってから再度お試しください。',retry_after:API_RETRY_SECONDS},429,{
      ...cors,'Retry-After':String(API_RETRY_SECONDS),'Cache-Control':'no-store'
    });
  } catch { return json({error:'rate_limit_unavailable'},503,cors); }
}

async function enforceSearchRateLimit(env, request, cors){
  if (!env.SEARCH_RATE_LIMITER || !env.SEARCH_COUNTER) return json({error:'rate_limit_unavailable'},503,cors);

  const ip = request.headers.get('CF-Connecting-IP') || 'unknown';
  const lockUrl = new URL(request.url);
  lockUrl.pathname = '/__rate_limit/search/' + encodeURIComponent(ip);
  lockUrl.search = '';
  const lockKey = new Request(lockUrl.toString(), { method: 'GET' });
  const cache = caches.default;

  const locked = await cache.match(lockKey);
  if (locked) {
    return json({
      error: 'rate_limited',
      message: '短時間に検索が集中しています。しばらくお待ちください。',
      retry_after: SEARCH_LOCK_SECONDS
    }, 429, {
      ...cors,
      'Retry-After': String(SEARCH_LOCK_SECONDS),
      'Cache-Control': 'no-store'
    });
  }

  const { success } = await env.SEARCH_RATE_LIMITER.limit({ key: ip });
  if (success) {
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(ip));
    const key = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2,'0')).join('');
    const id = env.SEARCH_COUNTER.idFromName(key);
    const response = await env.SEARCH_COUNTER.get(id).fetch('https://search-counter.internal/');
    if (!response.ok) throw new Error('Search counter unavailable');
    const result = await response.json();
    if (result.success === true) return null;
    if (result.success !== false) throw new Error('Invalid search counter response');
  }

  await cache.put(lockKey, new Response('locked', {
    headers: { 'Cache-Control': `public, max-age=${SEARCH_LOCK_SECONDS}` }
  }));

  return json({
    error: 'rate_limited',
    message: '短時間に検索が集中しています。しばらくお待ちください。',
    retry_after: SEARCH_LOCK_SECONDS
  }, 429, {
    ...cors,
    'Retry-After': String(SEARCH_LOCK_SECONDS),
    'Cache-Control': 'no-store'
  });
}

function corsHeaders(env, request){
  const allowed=env.ALLOWED_ORIGIN || '*';
  const origin=request.headers.get('Origin') || '';
  const value=allowed==='*' ? '*' : (origin===allowed ? origin : allowed);
  return {
    'Access-Control-Allow-Origin':value,
    'Access-Control-Allow-Methods':'GET, OPTIONS',
    'Access-Control-Allow-Headers':'Content-Type',
    'Vary':'Origin'
  };
}

function json(body,status,headers){
  return new Response(JSON.stringify(body),{
    status,
    headers:{'Content-Type':'application/json; charset=utf-8','X-Content-Type-Options':'nosniff','Cache-Control':'no-store',...headers}
  });
}

function parseIssuers(raw){
  return [...new Set((raw || '').split(',').map(x=>x.trim()).filter(x=>/^[a-z0-9_-]{1,40}$/.test(x)))].slice(0,60);
}
