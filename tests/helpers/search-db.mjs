import {DatabaseSync} from 'node:sqlite';
import {readFileSync} from 'node:fs';
export function fixture(){
 const db=new DatabaseSync(':memory:');
 db.exec(readFileSync(new URL('../../cloudflare/schema.sql',import.meta.url),'utf8'));
 db.exec(readFileSync(new URL('../../cloudflare/migrations/0001_read_budget.sql',import.meta.url),'utf8'));
 db.exec(readFileSync(new URL('../../cloudflare/migrations/0002_search_completeness.sql',import.meta.url),'utf8'));
 const queries=[],permit={limit:async()=>({success:true})};
 const env={CURSOR_SIGNING_KEY:'test-only-signing-key-for-search-pagination',API_RATE_LIMITER:permit,SEARCH_RATE_LIMITER:permit,
  SEARCH_COUNTER:{idFromName:x=>x,get:()=>({fetch:async()=>Response.json({success:true})})},
  DB:{prepare(sql){const query={sql,args:[]};return {bind(...args){query.args=args;return this;},async all(){
   const rows=db.prepare(sql).all(...query.args);queries.push({...query,rows:rows.length});return {results:rows,meta:{rows_read:rows.length}};
  }};}}};
 globalThis.caches={default:{match:async()=>undefined,put:async()=>{}}};
 const insert=(issuer,id,distance=0,category='restaurant')=>db.prepare('INSERT INTO stores(issuer_id,store_id,name,address,brand_name,category,lat,lng,official_url,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)').run(
  issuer,id,'Store '+id,'東京都千代田区'+id,'Brand',category,35.6812+distance/6371000*180/Math.PI,139.7671,'https://example.com/'+id,new Date().toISOString());
 const audit=issuer=>db.prepare(`INSERT OR REPLACE INTO issuer_catalog_audit SELECT issuer_id,catalog_revision,reference_revision,geo_count+reference_count,0,0,0,'verified','https://example.com/official','hash',? FROM issuer_stats WHERE issuer_id=?`).run(new Date().toISOString(),issuer);
 return {db,queries,env,insert,audit};
}
export const request=(params={})=>new Request('https://api.example/v1/stores/search?'+new URLSearchParams({lat:'35.6812',lng:'139.7671',radius:'3000',issuers:'a',...params}),{headers:{'CF-Connecting-IP':'192.0.2.1'}});
