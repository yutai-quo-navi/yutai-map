// Publish the selection grid in its final order, before a visitor loads any API.
// Uses only public aggregates and the existing expiry ledger; no store scans or DB writes.
import {readFile,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';
import {nearestDeadline,voucherEntriesFromLedger,compareDiningPriority,japanDay} from '../expiry.js';
export async function publishDiningOrder(root=resolve(import.meta.dirname,'..'),now=new Date()){
  const read=async p=>JSON.parse(await readFile(resolve(root,p),'utf8'));
  const manifest=await read('data/issuers/index.json');
  const issuers=manifest.issuers.filter(x=>x.status==='public');
  const counts=await read('data/issuers/store-counts.json');
  const entries=[...(await read('data/voucher-deadlines.json')).entries,
    ...voucherEntriesFromLedger((await read('data/expiry.json')).entries,'利用期限',issuers)];
  const htmlPath=resolve(root,'index.html');
  const html=await readFile(htmlPath,'utf8');
  const region=html.match(/(<div id="companyChips"[^>]*>\s*)([\s\S]*?)(\s*<\/div>)/);
  if(!region)throw new Error('Missing dining selection grid');
  const cards=new Map(region[2].trim().split(/\n\s*/).map(line=>{
    const id=line.match(/data-issuer="([a-z0-9-]+)"/)?.[1];
    if(!id)throw new Error('Invalid static issuer card');
    return [id,line];
  }));
  for(const issuer of issuers){
    if(!cards.has(issuer.id)||!Number.isSafeInteger(counts[issuer.id])||counts[issuer.id]<0)
      throw new Error('Missing verified card/count: '+issuer.id);
  }
  if(cards.size!==issuers.length)throw new Error('Static issuer coverage mismatch');
  const order=issuers.map(x=>({id:x.id,days:nearestDeadline(entries,x.id,now)?.days,count:counts[x.id]}))
    .sort((a,b)=>compareDiningPriority(a,b)||a.id.localeCompare(b.id));
  const opening=region[1].replace(/ data-order-day="[^"]*"/,'').replace('aria-label="優待会社の選択"','aria-label="優待会社の選択" data-order-day="'+japanDay(now)+'"');
  const result=html.replace(region[0],opening+order.map(x=>cards.get(x.id)).join('\n          ')+region[3]);
  if(result!==html)await writeFile(htmlPath,result);
  console.log('Published dining order: '+order.map(x=>x.id).join(', '));
  return order;
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url))
  await publishDiningOrder(process.argv[2]);
