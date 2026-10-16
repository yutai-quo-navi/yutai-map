// Small synthetic single-leaf binary fixtures, not a store collection/build tool.
import {createHash} from 'node:crypto';
export function snapshotFixture(rows,metadata={}){
 const groups=[],ids=new Map();rows=rows.map(r=>{const key=JSON.stringify([r.issuer_id,r.brand_name||'',r.category||'restaurant']);if(!ids.has(key)){ids.set(key,groups.length);groups.push(JSON.parse(key));}return {...r,g:ids.get(key)};});
 const meta=Buffer.from(JSON.stringify({groups,issuers:[...new Set(rows.map(r=>r.issuer_id))],coverage:{},health:{stores:rows.length,referenceStores:0},brands:[],cursor_signing_key:'fixture-only-snapshot-signing-key-32-characters',generated_at:new Date().toISOString(),...metadata}));
 const nodeBase=Math.ceil((64+meta.length)/8)*8,pointBase=nodeBase+72,aggregateBase=pointBase+rows.length*64,stringBase=aggregateBase+groups.length*8;
 const keys=rows.map(r=>Buffer.from(r.store_id)),records=rows.map(({g,...r})=>Buffer.from(JSON.stringify(r)));
 const buf=Buffer.alloc(stringBase+keys.reduce((s,k)=>s+k.length,0)+records.reduce((s,k)=>s+k.length,0));
 [0x31515359,1,1,rows.length,meta.length,nodeBase,pointBase,aggregateBase,stringBase,buf.length].forEach((n,i)=>buf.writeUInt32LE(n,i*4));meta.copy(buf,64);
 const lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];let offset=0;const counts=groups.map(()=>0);
 rows.forEach((r,i)=>{const p=pointBase+i*64,a=r.lat*Math.PI/180,b=r.lng*Math.PI/180,xyz=[Math.cos(a)*Math.cos(b),Math.cos(a)*Math.sin(b),Math.sin(a)];xyz.forEach((x,j)=>{buf.writeDoubleLE(x,p+j*8);lo[j]=Math.min(lo[j],x);hi[j]=Math.max(hi[j],x);});buf.writeDoubleLE(r.lat,p+24);buf.writeDoubleLE(r.lng,p+32);buf.writeUInt32LE(offset,p+40);buf.writeUInt32LE(keys[i].length,p+44);buf.writeUInt32LE(r.g,p+48);keys[i].copy(buf,stringBase+offset);offset+=keys[i].length;buf.writeUInt32LE(offset,p+56);buf.writeUInt32LE(records[i].length,p+60);records[i].copy(buf,stringBase+offset);offset+=records[i].length;counts[r.g]++;});
 for(let i=0;i<3;i++){buf.writeDoubleLE(lo[i],nodeBase+i*8);buf.writeDoubleLE(hi[i],nodeBase+24+i*8);}buf.writeUInt32LE(rows.length,nodeBase+60);buf.writeUInt32LE(groups.length,nodeBase+68);counts.forEach((n,i)=>{buf.writeUInt32LE(i,aggregateBase+i*8);buf.writeUInt32LE(n,aggregateBase+i*8+4);});
 const sha=createHash('sha256').update(buf).digest('hex'),manifest={version:1,sha256:sha,key:'search-index/versions/'+sha+'.bin',size:buf.length};let gets=0;
 const bucket={get:async key=>{gets++;if(key==='search-index/active.json'){const text=JSON.stringify(manifest);return {size:Buffer.byteLength(text),text:async()=>text};}if(key!==manifest.key)return null;return {size:buf.length,customMetadata:{sha256:sha},arrayBuffer:async()=>buf.buffer.slice(buf.byteOffset,buf.byteOffset+buf.byteLength)};}};
 return {bucket,bytes:buf,get gets(){return gets;},manifest};
}
