// Read-only, versioned spatial index. No request positions or results are saved.
const R=6371000, K=Math.PI/180, EPS=1e-12;
export const distance=(a,b)=>2*R*Math.asin(Math.min(1,Math.sqrt(Math.sin((a.lat-b.lat)*K/2)**2+Math.cos(a.lat*K)*Math.cos(b.lat*K)*Math.sin((a.lng-b.lng)*K/2)**2)));
const compare=(a,b)=>a.distance-b.distance || (a.issuer_id<b.issuer_id?-1:a.issuer_id>b.issuer_id?1:0) || (a.store_id<b.store_id?-1:a.store_id>b.store_id?1:0);
export class SpatialIndex {
 constructor(buffer){
  this.v=new DataView(buffer);const v=this.v;
  if(v.byteLength<64 || v.getUint32(0,true)!==0x31515359 || v.getUint32(4,true)!==1 || v.getUint32(36,true)!==v.byteLength)throw Error('Invalid spatial index');
  this.nodes=v.getUint32(20,true);this.points=v.getUint32(24,true);this.aggregates=v.getUint32(28,true);this.strings=v.getUint32(32,true);
  this.metadata=JSON.parse(new TextDecoder().decode(new Uint8Array(buffer,64,v.getUint32(16,true))));
  if(this.nodes+v.getUint32(8,true)*72>this.points || this.points+v.getUint32(12,true)*64>this.aggregates || this.aggregates>this.strings || this.strings>v.byteLength)throw Error('Invalid spatial offsets');
  this.decoder=new TextDecoder();
 }
 store(id){
  if(!Number.isInteger(id)||id<0||id>=this.v.getUint32(12,true))throw Error('Invalid store index');
  const p=this.points+id*64,offset=this.v.getUint32(p+56,true),len=this.v.getUint32(p+60,true);
  return JSON.parse(this.decoder.decode(new Uint8Array(this.v.buffer,this.strings+offset,len)));
 }
 query({lat,lng,radius,issuers,brand='',category='',cursor=null,limit=30}){
  if(!Number.isFinite(lat)||!Number.isFinite(lng)||!Number.isFinite(radius)||radius<=0||radius>30000||Math.abs(lat)>90||Math.abs(lng)>180||!Number.isInteger(limit)||limit<1||limit>30)throw Error('Invalid spatial query');
  const v=this.v, selected=new Set(issuers),groups=this.metadata.groups;
  const allowed=groups.map(g=>selected.has(g[0])&&(!brand||brand===g[1]));
  const nearestAllowed=groups.map((g,i)=>allowed[i]&&(!category||category===g[2]));
  const center=[Math.cos(lat*K)*Math.cos(lng*K),Math.cos(lat*K)*Math.sin(lng*K),Math.sin(lat*K)];
  const chord=2*Math.sin(radius/(2*R)),counts={all:0,restaurant:0,cafe:0,bakery:0,foodcourt:0,other:0};
  const stats={nodes:0,points:0,aggregate_nodes:0},origin={lat,lng};
  const bounds=id=>{let min=0,max=0;const p=this.nodes+id*72;for(let i=0;i<3;i++){const lo=v.getFloat64(p+i*8,true),hi=v.getFloat64(p+24+i*8,true),x=center[i];min+=Math.max(lo-x,x-hi,0)**2;max+=Math.max(Math.abs(x-lo),Math.abs(x-hi))**2;}return [Math.sqrt(min),Math.sqrt(max)];};
  const point=i=>{const p=this.points+i*64;return {p,lat:v.getFloat64(p+24,true),lng:v.getFloat64(p+32,true),group:v.getUint32(p+48,true)};};
  const add=(g,n)=>{counts.all+=n;counts[groups[g][2]]=(counts[groups[g][2]]||0)+n;};
  const aggregate=id=>{const p=this.nodes+id*72,start=v.getUint32(p+64,true),n=v.getUint32(p+68,true);for(let j=0;j<n;j++){const a=this.aggregates+(start+j)*8,g=v.getUint32(a,true);if(allowed[g])add(g,v.getUint32(a+4,true));}};
  const stack=v.getUint32(8,true)?[0]:[];
  while(stack.length){const id=stack.pop(),p=this.nodes+id*72,[min,max]=bounds(id);stats.nodes++;
   if(min>chord+EPS)continue;
   if(max<chord-EPS){aggregate(id);stats.aggregate_nodes++;continue;}
   const n=v.getUint32(p+60,true);
   if(n){const start=v.getUint32(p+56,true);for(let j=0;j<n;j++){const r=point(start+j);if(!allowed[r.group])continue;stats.points++;if(distance(origin,r)<=radius)add(r.group,1);}}
   else stack.push(v.getUint32(p+48,true),v.getUint32(p+52,true));
  }
  // Best-first traversal. A small sorted frontier avoids scanning distant stores.
  const firstBounds=v.getUint32(8,true)?bounds(0):null;
  const queue=firstBounds?[{id:0,min:firstBounds[0],max:firstBounds[1]}]:[],best=[];
  const before=cursor?2*Math.sin(cursor.distance/(2*R)):0;
  while(queue.length){queue.sort((a,b)=>b.min-a.min);const {id,min,max}=queue.pop();
   if(cursor && max<before-EPS)continue;
   const cutoff=best.length===limit?2*Math.sin(best.at(-1).distance/(2*R)):chord;
   if(min>Math.min(chord,cutoff)+EPS)continue;
   const p=this.nodes+id*72,n=v.getUint32(p+60,true);stats.nodes++;
   if(n){const start=v.getUint32(p+56,true);for(let j=0;j<n;j++){const r=point(start+j);if(!nearestAllowed[r.group])continue;stats.points++;
     const d=distance(origin,r);if(d>radius)continue;
     const offset=v.getUint32(r.p+40,true),len=v.getUint32(r.p+44,true);
     const item={issuer_id:groups[r.group][0],store_id:this.decoder.decode(new Uint8Array(v.buffer,this.strings+offset,len)),distance:d,lat:r.lat,lng:r.lng,record_index:start+j};
     if(cursor&&compare(item,cursor)<=0)continue;
     best.push(item);best.sort(compare);if(best.length>limit)best.pop();
   }}else for(const child of [v.getUint32(p+48,true),v.getUint32(p+52,true)]){const [min,max]=bounds(child);queue.push({id:child,min,max});}
  }
  return {results:best,counts,stats};
 }
}
