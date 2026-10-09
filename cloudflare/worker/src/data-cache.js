// Only public catalogs and private issuer reference rows are cached here.
// Search coordinates and IP addresses are never part of these keys or values.
export async function cachedData(key, seconds, load, usage){
  const request = new Request('https://yutai-data-cache.internal/' + encodeURIComponent(key));
  let cache;
  try {
    cache = globalThis.caches?.default;
    const hit = await cache?.match(request);
    if (hit?.ok) {
      const value = await hit.json();
      if (usage) usage.cache_hits++;
      return value;
    }
  } catch { /* A cache failure must not prevent a fresh database read. */ }
  const value = await load();
  try {
    await cache?.put?.(request, Response.json(value, {
      headers:{'Cache-Control':`public, max-age=${seconds}`}
    }));
  } catch { /* The database result remains valid without a cache write. */ }
  return value;
}

export async function readRows(env, sql, params=[], usage){
  const statement = env.DB.prepare(sql);
  const result = await (params.length ? statement.bind(...params) : statement).all();
  if (usage) {
    usage.queries++;
    usage.rows_read += Number(result.meta?.rows_read || 0);
    usage.rows_written += Number(result.meta?.rows_written || 0);
  }
  return result.results || [];
}
