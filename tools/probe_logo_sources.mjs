// Diagnostic only: verify live HTTP accessibility of images actually selected
// by the logo catalog. This is intentionally non-blocking because remote hosts
// may intermittently refuse automated traffic or disallow hotlinking.
import {representativeMark} from '../representative-marks.js';
import {readFile} from 'node:fs/promises';
const manifest=JSON.parse(await readFile(new URL('../data/issuers/index.json',import.meta.url),'utf8'));
const hotels=JSON.parse(await readFile(new URL('../data/features/index.json',import.meta.url),'utf8'));
const marks=[
  ...manifest.issuers.filter(x=>x.status==='public').map(x=>['dining',x.id]),
  ...hotels.features.filter(x=>x.section==='hotel').map(x=>['hotel',x.id])
].map(([section,id])=>({section,id,info:representativeMark(section,id)}));
const external=marks.filter(({info})=>info?.asset?.startsWith('https://'));
async function probe(entry){
 const {section,id,info}=entry;
 const ctl=new AbortController();
 const timer=setTimeout(()=>ctl.abort(),8000);
 try{
   // GET rather than HEAD: some image hosts explicitly reject HEAD.
   const res=await fetch(info.asset,{signal:ctl.signal,headers:{'User-Agent':'Mozilla/5.0 (compatible; brand-logo-audit/1.0)','Accept':'image/avif,image/webp,image/png,image/svg+xml,image/jpeg,image/*;q=0.8,*/*;q=0.5','Range':'bytes=0-1023'}});
   const ctype=res.headers.get('content-type')||'';
   return {section,id,brand:info.name,status:res.status,ok:res.ok && /^image\//.test(ctype),contentType:ctype,url:info.asset};
 } catch(e){return {section,id,brand:info.name,status:String(e.cause?.code||e.name||e),ok:false,url:info.asset}}
 finally{clearTimeout(timer)}
}
const result=[];
for(let i=0;i<external.length;i+=6){
 result.push(...await Promise.all(external.slice(i,i+6).map(probe)));
}
console.log('REMOTE LOGO SOURCE CHECK (HTTP access, not a guarantee of display in every browser):');
for(const r of result) console.log([r.ok?'OK ':'BAD',r.section,r.id,r.status,r.contentType||'',r.url].join(' | '));
const unavailable=result.filter(x=>!x.ok);
console.log('Summary: '+result.filter(x=>x.ok).length+'/'+result.length+' external URLs reachable; '+unavailable.length+' unreliable.');
