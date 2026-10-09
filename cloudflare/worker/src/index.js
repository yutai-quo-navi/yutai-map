export {SearchCounter} from './search-counter.js';
import {cachedData, readRows} from './data-cache.js';

const FEATURE_IDS = new Set(['vision-hotels','wakita-hotels','tkp-hotels','wealth-hotels','greens-hotels','tosei-hotels','sunfrontier-hotels','resol-hotels','seibu-free-hotels', 'daiwa-house-hotels', 'balnibarbi-dining', 'kyoritsu-hotel-discount', 'kyoritsu-resort-plan']);
const MAX_RADIUS = 30000;
const MAX_RESULTS = 30;
const OPENPOI_API = 'https://api.openpoiapi.com/v1/search';
const OPENPOI_ALIAS_CHUNK = 14;
const OPENPOI_LIMIT = 200;
const OPENPOI_MAX_REQUESTS = 40;
const SEARCH_LOCK_SECONDS = 60;
const API_RETRY_SECONDS = 60;
const OPENPOI_TIMEOUT_MS = 8000;
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
    const brand=(url.searchParams.get('brand') || '').trim().slice(0,200);
    const requestedCategory = (url.searchParams.get('category') || '').trim();
    const category = ['restaurant','cafe','bakery','foodcourt','other'].includes(requestedCategory)
      ? requestedCategory : '';

    if (!Number.isFinite(lat) || !Number.isFinite(lng) || lat < -90 || lat > 90 || lng < -180 || lng > 180)
      return json({ error: 'invalid_coordinates' }, 400, cors);
    if (!Number.isFinite(radius) || radius <= 0)
      return json({ error: 'invalid_radius' }, 400, cors);
    if (!issuers.length) return json({ results: [], count: 0 }, 200, cors);

    try {
      const rateLimited = await enforceSearchRateLimit(env, request, cors);
      if (rateLimited) return rateLimited;
    } catch { return json({error:'rate_limit_unavailable'},503,cors); }

    try {
      const referenceConfigs = await findReferenceConfigs(env, issuers, usage);
      // One issuer can have both official coordinates and unlocated references.
      const geoIssuers = issuers;
      const referenceSearches = (await Promise.all(referenceConfigs.map(config =>
        prepareReferenceSearch(env, config, brand, usage)
      ))).filter(Boolean);
      const upstreamRequests = referenceSearches.reduce((total, search) => total + search.aliasChunks.length, 0);
      if (upstreamRequests > OPENPOI_MAX_REQUESTS) throw new Error('OpenPOI request budget exceeded');

      const [geo, referenceResults] = await Promise.all([
        searchGeoStores(env, geoIssuers, lat, lng, radius, category, brand, usage),
        Promise.all(referenceSearches.map(search =>
          searchReferenceIssuer(search, lat, lng, radius)
        )).then(groups => groups.flat())
      ]);

      const categoryCounts = {...geo.counts};
      for(const s of referenceResults){ const key=s.category || 'restaurant'; categoryCounts[key]=(categoryCounts[key] || 0)+1; }
      categoryCounts.all=Object.values(categoryCounts).reduce((a,b)=>a+b,0);
      const combined = dedupeResults([...geo.results, ...referenceResults.filter(s=>!category || s.category===category)])
        .sort((a,b) => a.distance - b.distance)
        .slice(0, MAX_RESULTS);

      return json({ results: combined, count: combined.length, limit: MAX_RESULTS, category_counts: categoryCounts }, 200, {
        ...cors,
        'Cache-Control': 'public, max-age=30'
      });
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

async function findReferenceConfigs(env, issuers, usage){
  if (!issuers.length) return [];
  const placeholders = issuers.map(() => '?').join(',');
  return readRows(env,
    `SELECT s.issuer_id,s.reference_revision,c.aliases_json,c.updated_at FROM issuer_stats s JOIN issuer_search_config c ON c.issuer_id=s.issuer_id WHERE s.issuer_id IN (${placeholders}) AND s.reference_count > 0`, issuers, usage);
}

async function searchGeoStores(env, issuers, lat, lng, radius, category, brand, usage){
  if (!issuers.length) return {results:[],counts:{}};

  const latDelta = radius / 111320;
  const cos = Math.max(Math.cos(lat * Math.PI / 180), 0.1);
  const lngDelta = radius / (111320 * cos);
  const placeholders = issuers.map(() => '?').join(',');
  const sql = `SELECT issuer_id, store_id, name, address, phone, brand_name, category, lat, lng, official_url
    FROM stores
    WHERE issuer_id IN (${placeholders})
      AND lat BETWEEN ? AND ?
      AND lng BETWEEN ? AND ?
      ${brand ? 'AND brand_name = ?' : ''}`;

  const results = await readRows(env, sql, [
    ...issuers,
    lat-latDelta, lat+latDelta,
    lng-lngDelta, lng+lngDelta,
    ...(brand ? [brand] : [])
  ], usage);

  const nearby = results
    .map(s => ({
      ...s,
      distance: haversine(lat, lng, Number(s.lat), Number(s.lng))
    }))
    .filter(s => s.distance <= radius)
    .map(s => ({...s,distance:Math.round(s.distance)}));
  const counts = {};
  for (const s of nearby) {
    const key=s.category || 'restaurant';
    counts[key]=(counts[key] || 0)+1;
  }
  return {counts, results:nearby
    .filter(s => !category || s.category === category)
    .sort((a,b) => a.distance - b.distance)
    .slice(0, MAX_RESULTS)};
}

async function prepareReferenceSearch(env, config, brand, usage){
  const issuer = config.issuer_id;

  let aliases = [];
  try { aliases = JSON.parse(config.aliases_json || '[]'); } catch {}
  aliases = aliases.map(x => String(x || '').trim()).filter(Boolean);
  if (!aliases.length) return null;

  const refSql = `SELECT issuer_id, store_id, name, address, phone,
      name_norm, address_norm, phone_norm, brand_name, category, official_url
    FROM reference_stores
    WHERE issuer_id = ?
      ${brand ? 'AND brand_name = ?' : ''}`;

  const key=`references:${issuer}:${config.reference_revision}:${config.updated_at}:${JSON.stringify(brand)}`;
  const refs = await cachedData(key, 600, () => readRows(env, refSql,
    [issuer, ...(brand ? [brand] : [])], usage), usage);
  if (!refs.length) return null;

  const aliasChunks = referenceAliasChunks(brand ? [brand] : aliases);
  return {issuer, refs, aliasChunks};
}

async function searchReferenceIssuer({issuer, refs, aliasChunks}, lat, lng, radius){
  const responses = await Promise.allSettled(aliasChunks.map(async group => {
    const params = new URLSearchParams({
      q: group.join(' '),
      center: `${lng},${lat}`,
      radius: String(radius),
      limit: String(OPENPOI_LIMIT)
    });
    const res = await fetch(`${OPENPOI_API}?${params}`, {
      signal: AbortSignal.timeout(OPENPOI_TIMEOUT_MS),
      // Return redirects without following them; the non-2xx guard below rejects them.
      redirect: 'manual',
      headers: { 'Accept': 'application/json' }
    });
    if (!res.ok) {
      await res.body?.cancel();
      throw new Error(`OpenPOI ${res.status}`);
    }
    const data = await res.json();
    if (!Array.isArray(data.results)) throw new Error('Invalid OpenPOI response');
    return data.results.slice(0, OPENPOI_LIMIT);
  }));
  if (responses.every(response => response.status === 'rejected')) throw new Error('OpenPOI unavailable');

  const candidates = dedupePois(
    responses
      .filter(r => r.status === 'fulfilled')
      .flatMap(r => r.value)
  );

  const matched = [];
  for (const p of candidates) {
    const country = normalize(p.country || p.country_code || p.countryCode || '');
    if (country && !['japan','jp','日本'].includes(country)) continue;

    const plat = Number(p.lat);
    const plng = Number(p.lng);
    if (!Number.isFinite(plat) || !Number.isFinite(plng)) continue;

    const distance = Math.round(haversine(lat, lng, plat, plng));
    if (distance > radius) continue;

    const ref = matchReferenceStore(p, refs);
    if (!ref) continue;

    matched.push({
      issuer_id: ref.issuer_id,
      store_id: ref.store_id,
      name: ref.name,
      address: ref.address || '',
      phone: ref.phone || '',
      brand_name: ref.brand_name || '',
      category: ref.category || 'restaurant',
      lat: plat,
      lng: plng,
      official_url: ref.official_url || '',
      distance
    });
  }

  return dedupeResults(matched)
    .sort((a,b) => a.distance - b.distance);
}

function matchReferenceStore(p, refs){
  const poiName = normalize(p.name || '');
  const rawPoiAddress = p.address || [p.prefecture,p.city].filter(Boolean).join('');
  const poiAddress = normalizeAddress(rawPoiAddress);
  const poiPhone = String(p.phone || p.tel || '').replace(/\D/g,'');
  const poiPrefecture = japanesePrefecture(rawPoiAddress || p.prefecture || '');

  let best = null;
  let bestScore = 0;

  for (const ref of refs) {
    const officialName = ref.name_norm || normalize(ref.name || '');
    const officialAddress = normalizeAddress(ref.address || ref.address_norm || '');
    const officialPhone = ref.phone_norm || String(ref.phone || '').replace(/\D/g,'');
    const officialPrefecture = japanesePrefecture(ref.address || '');

    if (poiPrefecture && officialPrefecture && poiPrefecture !== officialPrefecture) continue;

    const phoneExact = Boolean(poiPhone && officialPhone && poiPhone === officialPhone);

    let nameScore = 0;
    if (poiName && officialName) {
      if (poiName === officialName) nameScore = 100;
      else if (poiName.length >= 8 && officialName.includes(poiName)) nameScore = 60;
      else if (officialName.length >= 8 && poiName.includes(officialName)) nameScore = 60;
      else if (poiName === normalize(String(ref.name || '').match(/^(.+?店)\s+[A-Za-z]/)?.[1] || '')) nameScore = 60;
      else if (containsOfficialBrandAndBranch(poiName, officialName, ref.brand_name)) nameScore = 55;
    }

    let addressScore = 0;
    if (poiAddress && officialAddress) {
      if (poiAddress === officialAddress) addressScore = 60;
      else if (poiAddress.length >= 8 && officialAddress.includes(poiAddress)) addressScore = 35;
      else if (officialAddress.length >= 8 && poiAddress.includes(officialAddress)) addressScore = 35;
    }

    const acceptable =
      phoneExact ||
      nameScore === 100 ||
      (nameScore >= 60 && addressScore >= 35) ||
      (nameScore === 55 && addressScore === 60);

    if (!acceptable) continue;

    const score = (phoneExact ? 200 : 0) + nameScore + addressScore;
    if (score > bestScore) {
      best = ref;
      bestScore = score;
    }
  }

  return best;
}

function containsOfficialBrandAndBranch(poiName, officialName, brandName){
  const brand = normalize(brandName || '');
  if (!brand || !officialName.startsWith(brand)) return false;
  const branch = officialName.slice(brand.length);
  if (branch.length < 3) return false;
  const brandIndex = poiName.indexOf(brand);
  return brandIndex >= 0 && poiName.indexOf(branch, brandIndex + brand.length) >= 0;
}

function referenceAliasChunks(aliases){
  // OpenPOI searches names AND addresses with space-separated OR terms. A place
  // name (e.g. the brand 北海道) can fill the candidate limit with unrelated POIs.
  // Keep broad terms in their own requests so they cannot hide other brands.
  const unique = [...new Map(aliases.map(alias => [normalize(alias), alias])).values()];
  const broad = unique.filter(alias => japanesePrefecture(alias) === alias || /\s/.test(alias));
  const specific = unique.filter(alias => !broad.includes(alias));
  return [...chunk(specific, OPENPOI_ALIAS_CHUNK), ...broad.map(alias => [alias])];
}

function normalizeAddress(value){
  // Official pages and POI sources use different Unicode forms for address separators.
  return normalize(String(value || '').normalize('NFKC').replace(/[−﹣－]/g, '-').replace(/大字/g, '').replace(/字[^0-9\s]+(?=[0-9])/g, ''));
}

function japanesePrefecture(value){
  const s = String(value || '');
  const match = s.match(/(北海道|東京都|京都府|大阪府|.{2,3}県)/);
  return match ? match[1] : '';
}

function dedupePois(items){
  const map = new Map();
  for (const p of items) {
    const lat = Number(p.lat), lng = Number(p.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) continue;
    const key = `${normalize(p.name || '')}|${lat.toFixed(5)}|${lng.toFixed(5)}`;
    if (!map.has(key)) map.set(key, p);
  }
  return [...map.values()];
}

function dedupeResults(items){
  const map = new Map();
  for (const item of items) {
    const key = `${item.issuer_id}|${item.store_id}`;
    const old = map.get(key);
    if (!old || Number(item.distance) < Number(old.distance)) map.set(key, item);
  }
  return [...map.values()];
}

function normalize(s){
  return String(s || '')
    .normalize('NFKC')
    .toLowerCase()
    .replace(/[\s・･\-‐‑–—ー_]/g,'');
}

function chunk(arr,n){
  const out=[];
  for(let i=0;i<arr.length;i+=n) out.push(arr.slice(i,i+n));
  return out;
}

function haversine(a,b,c,d){
  const R=6371000, r=Math.PI/180;
  const x=(c-a)*r, y=(d-b)*r;
  const q=Math.sin(x/2)**2+Math.cos(a*r)*Math.cos(c*r)*Math.sin(y/2)**2;
  return 2*R*Math.asin(Math.sqrt(q));
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
  return [...new Set((raw || '').split(',').map(x=>x.trim()).filter(x=>/^[a-z0-9_-]{1,40}$/.test(x)))].slice(0,20);
}
