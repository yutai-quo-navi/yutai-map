import {chromium} from 'playwright';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve,extname,sep} from 'node:path';
import assert from 'node:assert/strict';

const root = resolve(import.meta.dirname,'..');
const mime = {'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json',
  '.svg':'image/svg+xml','.webp':'image/webp','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.gif':'image/gif'};
const sourceFeatures = JSON.parse(await readFile(resolve(root,'data/features/index.json'),'utf8')).features
  .filter(feature => feature.section === 'hotel');
const hotelOrder = sourceFeatures.map(feature => feature.id);
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
  browser=await chromium.launch({headless:true});
  const context=await browser.newContext({viewport:{width:390,height:844},locale:'ja-JP',timezoneId:'Asia/Tokyo',reducedMotion:'reduce'});
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
      const list=Array.from({length:31},(_,i)=>({issuer_id:[
        'skylark','colowide','create','zensho','toridoll','yoshinoya','mcd','monogatari','matsuya',
        'royal','balnibarbi','daiichikosho','fujio','srs','arclands','kineya','saintmarc','chimney',
        'ringerhut','hiday','ichibanya','komeda','dnh','mos','yamaokaya','chikaranomoto','ohsho',
        'joyfull','yossix','foodlife','kura'][i],name:'テスト店'+i,count:99999-i*3311}));
      await route.fulfill({status:200,json:{brands:list}});return;
    }
    const match=url.pathname.match(/^\/v1\/features\/([a-z0-9-]+)$/);
    if(match){
      const id=match[1],index=hotelOrder.indexOf(id);
      await new Promise(resolve=>setTimeout(resolve,750));
      const stores=Array.from({length:Math.max(1,sourceFeatures.length-index)},(_,i)=>({
        id:id+'-store-'+i,name:'検証用施設'+i,address:'東京都千代田区千代田1-1',
        conditions:'利用可能',lat:35.68,lng:139.76,verified:true
      }));
      await route.fulfill({status:200,json:{id,stores,checkedOn:'2026-10-14'}});return;
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
  assert.equal(baseline.dining.length,31);
  assert.equal(baseline.hotel.length,12);
  await page.waitForFunction(()=>document.body.dataset.appReady==='true',undefined,{timeout:25000});
  await page.waitForFunction(()=>[...document.querySelectorAll('#hotelFeatures [data-feature] .benefit-choice-count')]
    .filter(x=>x.textContent.includes('件')).length>=10,undefined,{timeout:25000});
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
