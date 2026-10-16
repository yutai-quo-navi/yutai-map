export {SearchCounter} from './search-counter.js';
import {cachedData, readRows} from './data-cache.js';
import {fingerprint,issueCursor,readCursor} from './search-cursor.js';

const FEATURE_IDS = new Set(['vision-hotels','wakita-hotels','tkp-hotels','wealth-hotels','greens-hotels','tosei-hotels','sunfrontier-hotels','resol-hotels','seibu-free-hotels', 'daiwa-house-hotels', 'balnibarbi-dining', 'kyoritsu-hotel-discount', 'kyoritsu-resort-plan']);
const MAX_RADIUS = 30000;
const MAX_RESULTS = 30;
const SEARCH_LOCK_SECONDS = 60;
const API_RETRY_SECONDS = 60;
const MAX_REQUEST_URL_LENGTH = 2048;

export default {
  async fetch(request, env) {
    const usage = {queries:0,rows_read:0,rows_written:0,cache_hits:0};
    try { return await handleRequest(request, env, usage); }
    finally {
      if (usage.queries || usage.cache_hits) console.log(JSON.stringify({event:'d1_usage',operation:new URL(request.url).pathname,...usage}));
    }
  }
};

async function handleRequest(request, env, usage) {
    const url = new URL(request.url);
    const cors = corsHeaders(env, request);

    const origin = request.headers.get('Origin');
    if (origin && env.ALLOWED_ORIGIN && env.ALLOWED_ORIGIN !== '*' && origin !== env.ALLOWED_ORIGIN)
      return json({error:'origin_not_allowed'},403,cors);
    if (request.url.length > MAX_REQUEST_URL_LENGTH) return json({error:'request_too_long'},414,cors);

    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
    if (request.method !== 'GET') return json({ error: 'method_not_allowed' }, 405, cors);

    const databasePath = ['/health','/v1/brands','/v1/stores/search'].includes(url.pathname) || FEATURE_IDS.has(url.pathname.replace(/^\/v1\/features\//, ''));
    if (databasePath) {
      const limited = await enforceApiRateLimit(env, request, cors);
      if (limited) return limited;
    }

    if (url.pathname === '/health') {
      try {
        const [totals] = await readRows(env,
          'SELECT COALESCE(SUM(geo_count),0) AS stores, COALESCE(SUM(reference_count),0) AS referenceStores FROM issuer_stats', [], usage);
        return json({
          ok: true,
          stores: Number(totals?.stores || 0),
          referenceStores: Number(totals?.referenceStores || 0)
        }, 200, cors);
      } catch (error) {
        return json({ ok: false, error: 'db_unavailable' }, 503, cors);
      }
    }

    if (url.pathname.startsWith('/v1/features/')) {
      const id = url.pathname.slice('/v1/features/'.length);
      if (!FEATURE_IDS.has(id)) return json({error:'not_found'},404,cors);
      try {
        const row = await cachedData(`feature:${id}`, 300, async () => {
          const [value] = await readRows(env, 'SELECT payload_json FROM feature_snapshots WHERE feature_id = ?', [id], usage);
          if (!value) throw new Error('Missing feature');
          return value;
        }, usage);
        if (!row) return json({error:'feature_unavailable'},503,cors);
        return json(JSON.parse(row.payload_json),200,{...cors,'Cache-Control':'public, max-age=300'});
      } catch { return json({error:'feature_unavailable'},503,cors); }
    }

    if (url.pathname === '/v1/brands') {
      const ids=parseIssuers(url.searchParams.get('issuers'));
      if(!ids.length) return json({brands:[]},200,cors);
      try {
        const placeholders=ids.map(()=>'?').join(',');
        const versions = await readRows(env, `SELECT issuer_id,catalog_revision FROM issuer_stats WHERE issuer_id IN (${placeholders}) ORDER BY issuer_id`, ids, usage);
        const key = `brands:${ids.slice().sort().join(',')}:${JSON.stringify(versions)}`;
        const results = await cachedData(key, 300, () => readRows(env,
          `SELECT issuer_id,brand_name AS name,store_count AS count FROM brand_catalog WHERE issuer_id IN (${placeholders}) AND store_count > 0 ORDER BY issuer_id,brand_name`, ids, usage), usage);
        return json({brands:results},200,{...cors,'Cache-Control':'public, max-age=300'});
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

    const conditions = await fingerprint([lat,lng,radius,issuers.slice().sort(),category,brand]);
    const cursor = requestedCursor === null ? null : await readCursor(env.CURSOR_SIGNING_KEY,requestedCursor,conditions);
    if(requestedCursor !== null && !cursor) return json({error:'invalid_cursor',message:'検索条件またはページの有効期限が変わりました。再検索してください。'},400,cors);
    // Initial searches retain both independent ten/minute guards. Signed,
    // condition-bound continuation pages retain the all-endpoint 60/min guard.
    // Forged cursors never reach D1 or bypass the initial-search allowance.
    if(!cursor) {
      try {
        const rateLimited = await enforceSearchRateLimit(env,request,cors);
        if(rateLimited) return rateLimited;
      } catch {return json({error:'rate_limit_unavailable'},503,cors);}
    }
    try {
      const coverage = await searchCoverage(env,issuers,brand,usage);
      const revision = await fingerprint(coverage.versions);
      if(cursor && cursor.r!==revision) return json({error:'catalog_changed',message:'店舗情報が更新されました。再検索してください。'},409,cors);
      const geo = await searchGeoStoresWide(env,issuers,lat,lng,radius,category,brand,usage,cursor);
      const after=await readRows(env,`SELECT s.issuer_id,s.catalog_revision,s.reference_revision,
        a.status AS audit_status,a.catalog_revision AS audited_catalog_revision,
        a.reference_revision AS audited_reference_revision,a.checked_at,
        a.official_count,a.missing_count,a.extra_count,a.identity_mismatch_count,
        (SELECT revision FROM location_revision WHERE id=1) AS location_revision
        FROM issuer_stats s LEFT JOIN issuer_catalog_audit a ON a.issuer_id=s.issuer_id
        WHERE s.issuer_id IN (${issuers.map(()=>'?').join(',')}) ORDER BY s.issuer_id`,issuers,usage);
      if(await fingerprint(after.map(catalogVersion))!==revision)
        return json({error:'catalog_changed',message:'検索中に店舗情報が更新されました。再検索してください。'},409,cors);
      const rows=geo.results;
      const displayed=(cursor?.n || 0)+rows.length;
      const total=geo.counts[category || 'all'];
      const hasMore=displayed<total && rows.length>0;
      const last=rows.at(-1);
      const next=hasMore ? await issueCursor(env.CURSOR_SIGNING_KEY,{
        q:conditions,r:revision,d:last.exact_distance,i:last.issuer_id,s:last.store_id,n:displayed,
        c:['all','restaurant','cafe','bakery','foodcourt','other'].map(key=>geo.counts[key])
      }) : null;
      return json({
        results:rows.map(({exact_distance,...row})=>row),count:rows.length,limit:MAX_RESULTS,
        category_counts:geo.counts,next_cursor:next,has_more:hasMore,
        incomplete:!coverage.complete,coverage:{
          complete:coverage.complete,unresolved_stores:coverage.unresolved,
          unverified_issuers:coverage.unverified,search_scope:'all_selected_d1_stores',
          external_requests:0
        }
      },200,{...cors,'Cache-Control':'no-store'});
    } catch (error) {
      console.error(error);
      return json({ error: 'search_failed' }, 502, cors);
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

function catalogVersion(r){
  return [r.issuer_id,r.catalog_revision,r.reference_revision,r.audit_status,
    r.audited_catalog_revision,r.audited_reference_revision,r.checked_at,r.official_count,
    r.missing_count,r.extra_count,r.identity_mismatch_count,r.location_revision];
}

async function searchCoverage(env,issuers,brand,usage){
  const placeholders=issuers.map(()=>'?').join(',');
  const rows=await readRows(env,`SELECT s.issuer_id,s.catalog_revision,s.reference_revision,
    a.status AS audit_status,a.catalog_revision AS audited_catalog_revision,
    a.reference_revision AS audited_reference_revision,a.checked_at,
    a.official_count,a.missing_count,a.extra_count,a.identity_mismatch_count,
    (SELECT revision FROM location_revision WHERE id=1) AS location_revision,
    (SELECT COUNT(*) FROM reference_stores r WHERE r.issuer_id=s.issuer_id
      ${brand ? 'AND r.brand_name=?' : ''}
      AND NOT EXISTS(SELECT 1 FROM coordinate_resolutions c WHERE c.issuer_id=r.issuer_id
        AND c.store_id=r.store_id AND c.status='verified'
        AND c.name=r.name AND c.address=r.address AND c.phone=r.phone)) AS unresolved_count
    FROM issuer_stats s LEFT JOIN issuer_catalog_audit a ON a.issuer_id=s.issuer_id
    WHERE s.issuer_id IN (${placeholders}) ORDER BY s.issuer_id`,[...(brand ? [brand] : []),...issuers],usage);
  const byId=new Map(rows.map(row=>[row.issuer_id,row]));
  const unverified=issuers.filter(id=>{
    const r=byId.get(id);
    return !r || r.audit_status!=='verified' || r.audited_catalog_revision!==r.catalog_revision ||
      r.audited_reference_revision!==r.reference_revision || r.official_count==null ||
      r.missing_count!==0 || r.extra_count!==0 || r.identity_mismatch_count!==0 ||
      !r.checked_at || Date.now()-Date.parse(r.checked_at)>7*86400000 || !Number.isFinite(Date.parse(r.checked_at));
  });
  const unresolved=rows.reduce((n,r)=>n+Number(r.unresolved_count || 0),0);
  return {complete:!unresolved && !unverified.length,unresolved,unverified,versions:rows.map(catalogVersion)};
}

async function searchGeoStoresWide(env, issuers, lat, lng, radius, category, brand, usage, cursor = null){
  if (!issuers.length) return {results:[],counts:{}};

  const angular = radius / 6371000;
  const latDelta = angular * 180 / Math.PI;
  const cos = Math.max(Math.cos(lat * Math.PI / 180), 0.1);
  const lngDelta = Math.asin(Math.min(1,Math.sin(angular) / cos)) * 180 / Math.PI;
  const placeholders = issuers.map(() => '?').join(',');
  // Calculate the precise great-circle distance in D1. A wide 44-issuer,
  // 30-km search can have tens of thousands of candidates. Returning all
  // candidates to the Worker before sorting can exhaust its CPU/memory budget.
  // A single CTE returns the nearest 30 *and* complete category counts,
  // including when the current category has no matching stores.
  const sql = `WITH candidates AS (
    SELECT issuer_id, store_id, name, address, phone, brand_name, category,
      lat, lng, official_url,
      2 * 6371000 * asin(min(1, sqrt(
        pow(sin(radians(lat - ?) / 2), 2)
        + cos(radians(?)) * cos(radians(lat))
        * pow(sin(radians(lng - ?) / 2), 2)
      ))) AS exact_distance
    FROM searchable_stores
    WHERE issuer_id IN (${placeholders})
      AND lat BETWEEN ? AND ?
      AND lng BETWEEN ? AND ?
      ${brand ? 'AND brand_name = ?' : ''}
  ), nearby AS (
    SELECT *, CAST(exact_distance + 0.5 AS INTEGER) AS rounded_distance
    FROM candidates WHERE exact_distance <= ?
  ), totals AS (
    ${cursor ? `SELECT ? AS all_count, ? AS restaurant_count, ? AS cafe_count,
      ? AS bakery_count, ? AS foodcourt_count, ? AS other_count` : `SELECT
      COUNT(*) AS all_count,
      COUNT(*) FILTER (WHERE COALESCE(category,'restaurant') = 'restaurant') AS restaurant_count,
      COUNT(*) FILTER (WHERE category = 'cafe') AS cafe_count,
      COUNT(*) FILTER (WHERE category = 'bakery') AS bakery_count,
      COUNT(*) FILTER (WHERE category = 'foodcourt') AS foodcourt_count,
      COUNT(*) FILTER (WHERE category = 'other') AS other_count
    FROM nearby`}
  ), closest AS (
    SELECT * FROM nearby
    WHERE 1=1
    ${category ? "AND category = ?" : ''}
    ${cursor ? `AND (
      exact_distance > ? OR
      (exact_distance = ? AND (
        issuer_id > ? OR (issuer_id = ? AND store_id > ?)
      ))
    )` : ''}
    ORDER BY exact_distance, issuer_id, store_id
    LIMIT ${MAX_RESULTS}
  )
  SELECT closest.*, totals.all_count AS __all_count,
    totals.restaurant_count AS __restaurant_count,
    totals.cafe_count AS __cafe_count,
    totals.bakery_count AS __bakery_count,
    totals.foodcourt_count AS __foodcourt_count,
    totals.other_count AS __other_count
  FROM totals LEFT JOIN closest ON 1=1
  ORDER BY closest.exact_distance, closest.issuer_id, closest.store_id`;

  const rows = await readRows(env, sql, [
    lat, lat, lng, ...issuers,
    lat-latDelta, lat+latDelta,
    lng-lngDelta, lng+lngDelta,
    ...(brand ? [brand] : []),
    radius,
    ...(cursor ? cursor.c : []),
    ...(category ? [category] : []),
    ...(cursor && !cursor.start ? [
      cursor.d, cursor.d, cursor.i, cursor.i, cursor.s
    ] : [])
  ], usage);

  const first = rows[0] || {};
  const counts = {
    all:Number(first.__all_count || 0),
    restaurant:Number(first.__restaurant_count || 0),
    cafe:Number(first.__cafe_count || 0),
    bakery:Number(first.__bakery_count || 0),
    foodcourt:Number(first.__foodcourt_count || 0),
    other:Number(first.__other_count || 0)
  };
  const results = rows.filter(row => row.store_id != null).map(row => ({
    issuer_id:row.issuer_id, store_id:row.store_id, name:row.name,
    address:row.address, phone:row.phone, brand_name:row.brand_name,
    category:row.category, lat:row.lat, lng:row.lng,
    official_url:row.official_url, distance:Number(row.rounded_distance),exact_distance:Number(row.exact_distance)
  }));
  return {counts,results};
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
