import {chromium} from 'playwright';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve,extname,sep} from 'node:path';
import assert from 'node:assert/strict';
const root=resolve(import.meta.dirname,'..');
const publicIssuerCount=JSON.parse(await readFile(resolve(root,'data/issuers/index.json'),'utf8')).issuers.filter(x=>x.status==='public').length;
const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.png':'image/png','.webp':'image/webp','.svg':'image/svg+xml','.jpg':'image/jpeg','.jpeg':'image/jpeg','.gif':'image/gif'};
const server=createServer(async(req,res)=>{
  const pathname=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
  const path=resolve(root,'.'+(pathname==='/'?'/index.html':pathname));
  if(!path.startsWith(root+sep)){res.writeHead(403).end();return;}
  try{const bytes=await readFile(path);res.writeHead(200,{'content-type':mime[extname(path)]||'application/octet-stream'}).end(bytes);}
  catch{res.writeHead(404).end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const origin='http://127.0.0.1:'+server.address().port;
let browser;
try {
  browser=await chromium.launch({headless:true,...(process.env.UI_CHROMIUM_EXECUTABLE?{executablePath:process.env.UI_CHROMIUM_EXECUTABLE}:{})});
  const context=await browser.newContext({viewport:{width:390,height:844},locale:'ja-JP',timezoneId:'Asia/Tokyo'});
  const page=await context.newPage();
  const pageErrors=[];
  page.on('pageerror',e=>pageErrors.push(e.message));
  let configRequests=0;
  await page.route('**/*',async route=>{
    const url=new URL(route.request().url());
    if(url.origin!==origin){await route.abort();return;}
    if(/^\/data\/issuers\/[^/]+\/config\.json$/.test(url.pathname)){
      configRequests++;
      // Model a very slow first visit: store data cannot finish for six seconds.
      await new Promise(resolve=>setTimeout(resolve,6000));
    }
    await route.continue();
  });
  const start=performance.now();
  await page.goto(origin+'/',{waitUntil:'domcontentloaded',timeout:12000});
  await page.waitForFunction(()=>[...document.querySelectorAll('#companyChips .representative-mark-image')].slice(0,9)
    .every(img=>img.complete&&img.naturalWidth>0),undefined,{timeout:3500});
  const metrics=await page.evaluate(()=>{
    const cards=[...document.querySelectorAll('#companyChips [data-issuer]')];
    const imgs=[...document.querySelectorAll('#companyChips .representative-mark-image')];
    return {cards:cards.length,loaded:imgs.filter(img=>img.complete&&img.naturalWidth>0).length,
      appReady:document.body.dataset.appReady||'',firstLogo:imgs[0]?.currentSrc||''};
  });
  const ms=Math.round(performance.now()-start);
  console.log(JSON.stringify({event:'first_logo_render',elapsed_ms:ms,configRequests,...metrics}));
  assert.equal(metrics.cards,publicIssuerCount,'All issuer cards must appear without waiting for config responses');
  assert.ok(metrics.loaded>=9,'the first three rows of logos should already be loaded');
  assert.equal(metrics.appReady,'','first paint should precede async API completion');
  assert.ok(ms<4500,'first logos should appear even while config responses take 6 seconds');
  const first=page.locator('#companyChips [data-issuer="yoshinoya"]');
  const was=await first.getAttribute('aria-pressed');
  await first.click();
  assert.notEqual(await first.getAttribute('aria-pressed'),was,'card can respond before config loads');
  await page.locator('#hotelTab').click();
  assert.equal(await page.locator('#hotelFeatures [data-feature]').count(),12);
  assert.equal(pageErrors.length,0,JSON.stringify(pageErrors));
  await context.close();
} finally {if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
