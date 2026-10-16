const encoder = new TextEncoder();
const MAX_AGE_SECONDS = 1800;
const base64 = bytes => btoa(String.fromCharCode(...new Uint8Array(bytes))).replaceAll('+','-').replaceAll('/','_').replace(/=+$/,'');
const unbase64 = text => Uint8Array.from(atob(text.replaceAll('-','+').replaceAll('_','/')), char=>char.charCodeAt(0));
async function key(secret){
  if (typeof secret !== 'string' || secret.length < 32) throw new Error('Missing cursor signing key');
  return crypto.subtle.importKey('raw',encoder.encode(secret),{name:'HMAC',hash:'SHA-256'},false,['sign','verify']);
}
export async function fingerprint(value){
  return base64(await crypto.subtle.digest('SHA-256',encoder.encode(JSON.stringify(value))));
}
export async function issueCursor(secret, value){
  const payload=base64(encoder.encode(JSON.stringify({...value,v:2,exp:Math.floor(Date.now()/1000)+MAX_AGE_SECONDS})));
  const signature=base64(await crypto.subtle.sign('HMAC',await key(secret),encoder.encode(payload)));
  return payload+'.'+signature;
}
export async function readCursor(secret, raw, conditions){
  if (!raw || raw.length>1200 || !/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]{43}$/.test(raw)) return null;
  try {
    const [payload,signature]=raw.split('.');
    if (!await crypto.subtle.verify('HMAC',await key(secret),unbase64(signature),encoder.encode(payload))) return null;
    const value=JSON.parse(new TextDecoder().decode(unbase64(payload)));
    if(value.v!==2 || value.q!==conditions || !Number.isFinite(value.exp) || value.exp<Math.floor(Date.now()/1000)) return null;
    if(!Number.isFinite(value.d) || value.d<0 || value.d>30000) return null;
    if(typeof value.i!=='string' || !/^[a-z0-9_-]{1,40}$/.test(value.i)) return null;
    if(typeof value.s!=='string' || !value.s || value.s.length>180) return null;
    if(typeof value.r!=='string' || !Number.isInteger(value.n) || value.n<1) return null;
    return value;
  } catch {return null;}
}
