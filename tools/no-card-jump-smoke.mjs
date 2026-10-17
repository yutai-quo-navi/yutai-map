import {chromium} from 'playwright';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve,extname,sep} from 'node:path';
import assert from 'node:assert/strict';

const root = resolve(import.meta.dirname,'..');
const publicIssuers = JSON.parse(await readFile(resolve(root,'data/issuers/index.json'),'utf8')).issuers.filter(issuer => issuer.status === 'public');
const mime = {'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json',
  '.svg':'image/svg+xml','.webp':'image/webp','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.gif':'image/gif'};
const sourceFeatures = JSON.parse(await readFile(resolve(root,'data/features/index.json'),'utf8')).features
  .filter(feature => feature.section === 'hotel');
const server=createServer(async(req,res)=>{
  const pathname=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
  const path=resolve(root,'.'+(pathname==='/'?'/index.html':pathname));
  if(!path.startsWith(root+sep)){res.writeHead(403).end();return;}
  try{const bytes=await readFile(path);res.writeHead(200,{'Content-Type':mime[extname(path)]||'application/octet-stream'}).end(bytes);}
  catch{res.writeHead(404).end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const origin='http://127.0.0.1:'+server.address().port;
let browser;
try{
  browser=await chromium.launch({headless:true,...(process.env.UI_CHROMIUM_EXECUTABLE ? {executablePath:process.env.UI_CHROMIUM_EXECUTABLE} : {})});
  const context=await browser.newContext({viewport:{width:390,height:844},locale:'ja-JP',timezoneId:'Asia/Tokyo',reducedMotion:'reduce',...(process.env.UI_CHROMIUM_EXECUTABLE ? {bypassCSP:true} : {})});
  const page=await context.newPage();
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',async route=>{
    const url=new URL(route.request().url());
    if(url.origin===origin){
      if(/^\/data\/issuers\/[^/]+\/config\.json$/.test(url.pathname))
        await new Promise(resolve=>setTimeout(resolve,850));
      await route.continue();return;
    }
    if(url.pathname==='/v1/brands'){
      await new Promise(resolve=>setTimeout(resolve,1400));
      const list=publicIssuers.map((issuer,i)=>({issuer_id:issuer.id,name:'テスト店'+i,count:99999-i*2500}));
      await route.fulfill({status:200,json:{brands:list}});return;
    }
    if(url.pathname==='/v1/hotels/catalog'){
      // The private spatial index exposes only verified counts, never hotel rows.
      // Delay its response so that the DOM stability check includes async hydration.
      await new Promise(resolve=>setTimeout(resolve,750));
      const features=sourceFeatures.map((feature,index)=>({
        id:feature.id,storeCount:Math.max(1,sourceFeatures.length-index),
        checkedOn:'2026-10-14',stores:[]
      }));
      await route.fulfill({status:200,json:{features}});return;
    }
    await route.abort();
  });
  await page.goto(origin+'/',{waitUntil:'domcontentloaded',timeout:20000});
  const baseline=await page.evaluate(()=>{
    const list=(s,attr)=>[...document.querySelectorAll(s)].map(e=>e.dataset[attr]);
    const initial={dining:list('#companyChips [data-issuer]','issuer'),
      hotel:list('#hotelFeatures [data-feature]','feature')};
    const counts={dining:0,hotel:0};
    const observer=(selector,name)=>new MutationObserver(records=>{
      for(const record of records){
        counts[name]+=record.addedNodes.length+record.removedNodes.length;
      }
    }).observe(document.querySelector(selector),{childList:true});
    observer('#companyChips','dining');
    observer('#hotelFeatures .feature-buttons','hotel');
    window.__cardOrderMotion={initial,counts};
    return initial;
  });
  assert.equal(baseline.dining.length,publicIssuers.length);
  assert.equal(baseline.hotel.length,sourceFeatures.length);
  await page.waitForFunction(()=>document.body.dataset.appReady==='true',undefined,{timeout:25000});
  await page.waitForFunction(expected=>[...document.querySelectorAll('#hotelFeatures [data-feature] .benefit-choice-count')]
    .filter(x=>x.textContent.includes('件')).length===expected,sourceFeatures.length,{timeout:25000});
  await page.waitForTimeout(250);
  const after=await page.evaluate(()=>{
    const s=window.__cardOrderMotion;
    const list=(selector,key)=>[...document.querySelectorAll(selector)].map(b=>b.dataset[key]);
    return {...s,current:{
      dining:list('#companyChips [data-issuer]','issuer'),
      hotel:list('#hotelFeatures [data-feature]','feature')
    },logoNodes:[...document.querySelectorAll('#companyChips .representative-mark-image')].length};
  });
  assert.deepEqual(after.current.dining,baseline.dining,'dining cards must never change order after 2 remote data loads');
  assert.deepEqual(after.current.hotel,baseline.hotel,'hotel cards must never change order after the store counts load');
  assert.deepEqual(after.counts,{dining:0,hotel:0},'a hydrated logo card must never be moved or remounted');
  assert.ok(!errors.length,'no runtime exceptions: '+JSON.stringify(errors));
  console.log(JSON.stringify({event:'no_logo_jump',result:'success',dining_cards:after.logoNodes,
    hotel_cards:after.current.hotel.length,card_move_mutations:after.counts}));
  await context.close();
}finally{
  if(browser)await browser.close();
  await new Promise(resolve=>server.close(resolve));
}
