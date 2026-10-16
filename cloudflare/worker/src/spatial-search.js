import {fingerprint,issueCursor,readCursor} from './search-cursor.js';
import {getSearchSnapshot} from './search-snapshot.js';
export async function searchSnapshot(env,{lat,lng,radius,issuers,brand,category,requestedCursor}){
 const {index,revision}=await getSearchSnapshot(env),secret=index.metadata.cursor_signing_key;
 if(issuers.some(id=>!index.metadata.issuers.includes(id)))return {status:400,body:{error:'invalid_issuers'}};
 const conditions=await fingerprint([lat,lng,radius,issuers.slice().sort(),category,brand]);
 const cursor=requestedCursor===null?null:await readCursor(secret,requestedCursor,conditions);
 if(requestedCursor!==null&&!cursor)return {status:400,body:{error:'invalid_cursor',message:'検索条件またはページの有効期限が変わりました。再検索してください。'}};
 if(cursor&&cursor.r!==revision)return {status:409,body:{error:'catalog_changed',message:'店舗情報が更新されました。再検索してください。'}};
 const page=index.query({lat,lng,radius,issuers,brand,category,cursor:cursor?{distance:cursor.d,issuer_id:cursor.i,store_id:cursor.s}:null});
 const total=page.counts[category||'all'],displayed=(cursor?.n||0)+page.results.length,hasMore=displayed<total&&page.results.length>0;
 const last=page.results.at(-1),next=hasMore?await issueCursor(secret,{q:conditions,r:revision,d:last.distance,i:last.issuer_id,s:last.store_id,n:displayed,c:['all','restaurant','cafe','bakery','foodcourt','other'].map(k=>page.counts[k])}):null;
 const unresolved=issuers.reduce((sum,id)=>sum+(index.metadata.coverage[id]?.unresolved||0),0),unverified=issuers.filter(id=>!index.metadata.coverage[id]?.verified),complete=!unresolved&&!unverified.length;
 return {status:200,body:{results:page.results.map(r=>({...index.store(r.record_index),distance:Math.round(r.distance)})),count:page.results.length,limit:30,category_counts:page.counts,next_cursor:next,has_more:hasMore,incomplete:!complete,coverage:{complete,unresolved_stores:unresolved,unverified_issuers:unverified,search_scope:'all_selected_indexed_stores',external_requests:0,d1_rows_read:0,index_revision:revision,index_generated_at:index.metadata.generated_at}}};
}
