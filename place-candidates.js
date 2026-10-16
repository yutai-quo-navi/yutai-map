// Prefer an exact named facility to an aggregate regional centroid.
const normalize=s=>String(s||'').normalize('NFKC').replace(/\s/g,'').toLowerCase();
const prefecture=/^(北海道|東京都|京都府|大阪府|.{2,3}県)$/;
const valid=(lat,lng)=>Number.isFinite(lat)&&Number.isFinite(lng)&&lat>=20&&lat<=46&&lng>=122&&lng<=154;
export function placeCandidates(data,query){
 const q=normalize(query),items=[];
 for(const s of data.suggestions||[]){
  const lat=Number(s.lat),lng=Number(s.lng);if(!s.name||!valid(lat,lng))continue;
  items.push({label:s.name,sub:s.address||'',lat,lng,rank:normalize(s.name)===q?0:3});
 }
 for(const v of data.vocabulary||[]){
  if(v.type!=='place'||!v.label||!Array.isArray(v.center)||v.center.length!==2||!prefecture.test(v.prefecture||''))continue;
  const lng=Number(v.center[0]),lat=Number(v.center[1]);if(!valid(lat,lng))continue;
  items.push({label:v.label,sub:[v.prefecture,v.city].filter(Boolean).join(' '),lat,lng,rank:normalize(v.label)===q?1:2});
 }
 return items.sort((a,b)=>a.rank-b.rank).map(({rank,...p})=>p);
}
