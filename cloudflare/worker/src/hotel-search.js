import {getSearchSnapshot} from './search-snapshot.js';
import {fingerprint,issueCursor,readCursor} from './search-cursor.js';
const WORLD=Math.PI*6371000;
export async function hotelCatalog(env){
 const {index}=await getSearchSnapshot(env,'hotel');
 return {features:index.metadata.features,index_revision:index.metadata.generated_at};
}
export async function searchHotels(env,{lat,lng,radius,features,requestedCursor}){
 const {index,revision}=await getSearchSnapshot(env,'hotel');
 const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Tokyo',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
 const visible=index.metadata.features.filter(f=>f.status==='public'&&(f.availability==='continuous'||f.validFrom<=today&&today<=f.validThrough));
 const allowed=new Set(visible.map(f=>f.id));
 if(features.some(id=>!allowed.has(id)))return {status:400,body:{error:'invalid_features'}};
 const q=await fingerprint(['hotel',lat,lng,radius,features.slice().sort()]);
 const cursor=requestedCursor===null?null:await readCursor(index.metadata.cursor_signing_key,requestedCursor,q,WORLD);
 if(requestedCursor!==null&&!cursor)return {status:400,body:{error:'invalid_cursor'}};
 if(cursor&&cursor.r!==revision)return {status:409,body:{error:'catalog_changed'}};
 const page=index.query({lat,lng,radius:radius==='all'?WORLD:radius,issuers:features,maxRadius:WORLD,cursor:cursor?{distance:cursor.d,issuer_id:cursor.i,store_id:cursor.s}:null});
 const total=page.counts.all,displayed=(cursor?.n||0)+page.results.length,more=displayed<Math.min(total,60)&&page.results.length>0,last=page.results.at(-1);
 const next=more?await issueCursor(index.metadata.cursor_signing_key,{q,r:revision,d:last.distance,i:last.issuer_id,s:last.store_id,n:displayed,c:[total,0,0,0,0,total]}):null;
 return {status:200,body:{results:page.results.map(r=>({...index.store(r.record_index),distance:Math.round(r.distance)})),count:page.results.length,total,limit:30,display_limit:60,limited:total>60,has_more:more,next_cursor:next,coverage:{d1_rows_read:0,external_requests:0,index_revision:revision}}};
}
