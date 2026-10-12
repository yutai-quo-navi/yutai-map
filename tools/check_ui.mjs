// Local-only browser fixtures avoid production API reads and retain real UI logic.
import {createServer} from 'node:http';
import {readFile, mkdir, writeFile} from 'node:fs/promises';
import {resolve, extname, sep} from 'node:path';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {checkPage} from 'lintapple';

const root=resolve(import.meta.dirname,'..');
const output=resolve(root,'ui-reports');
const policy=JSON.parse(await readFile(resolve(root,'ui-policy.json'),'utf8'));
const manifest=JSON.parse(await readFile(resolve(root,'data/issuers/index.json'),'utf8'));
const publicIssuerCount=manifest.issuers.filter(issuer=>issuer.status==='public').length;
const strict=process.argv.includes('--strict');
const fontDir=process.env.UI_TEST_FONT_DIRECTORY;
const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.svg':'image/svg+xml','.png':'image/png','.woff2':'font/woff2'};
const server=createServer(async(req,res)=>{
  const pathname=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
  if(fontDir&&pathname.startsWith('/__ui-font/')){
    const file=resolve(fontDir,pathname.slice('/__ui-font/'.length));
    if(!file.startsWith(resolve(fontDir)+sep)){res.writeHead(403).end();return;}
    try{let body=await readFile(file);if(extname(file)==='.css')body=body.toString().replaceAll("'Noto Sans JP'","'Meiryo'");res.writeHead(200,{'Content-Type':mime[extname(file)]||'application/octet-stream'}).end(body);}
    catch{res.writeHead(404).end();}return;
  }
  const file=resolve(root,'.'+(pathname==='/'?'/index.html':pathname));
  if(!file.startsWith(root+sep)){res.writeHead(403).end();return;}
  try{const body=await readFile(file);res.writeHead(200,{'Content-Type':mime[extname(file)]||'application/octet-stream'}).end(body);}
  catch{res.writeHead(404).end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const url=`http://127.0.0.1:${server.address().port}`;
await mkdir(output,{recursive:true});
const stores=[
  {issuer_id:'skylark',store_id:'ui-1',brand_name:'ガスト',name:'ガスト 表示検証用の長い店舗名・駅前ショッピングセンター店',address:'東京都○○区○○町1丁目（テスト用）',lat:35.681,lng:139.767,distance:350,category:'restaurant'},
  {issuer_id:'yoshinoya',store_id:'ui-2',brand_name:'吉野家',name:'吉野家 表示検証用店舗',address:'東京都○○区○○町2丁目（テスト用）',lat:35.682,lng:139.768,distance:800,category:'restaurant'}
];
const reports=[];
let browser;
try{
  browser=await chromium.launch(process.env.UI_CHROMIUM_EXECUTABLE?{executablePath:process.env.UI_CHROMIUM_EXECUTABLE}:{});
  for(const viewport of policy.viewports){
    const context=await browser.newContext({viewport,locale:'ja-JP',timezoneId:'Asia/Tokyo',reducedMotion:'reduce',geolocation:{latitude:35.681,longitude:139.767},permissions:['geolocation']});
    const page=await context.newPage();
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.route('**/*',async route=>{
      const requestUrl=new URL(route.request().url());
      if(requestUrl.origin===url){
        // Keep local issuer configs and the expiry ledger, stub remote hotel datasets.
        if(requestUrl.pathname==='/data/features/index.json') return route.fulfill({json:{features:[]}});
        return route.continue();
      }
      if(requestUrl.pathname==='/v1/brands')return route.fulfill({json:{brands:stores.map(s=>({issuer_id:s.issuer_id,name:s.brand_name,count:1}))}});
      if(requestUrl.pathname==='/v1/stores/search'){
        const issuers=(requestUrl.searchParams.get('issuers')||'').split(',');
        return route.fulfill({json:{results:stores.filter(s=>issuers.includes(s.issuer_id))}});
      }
      if(requestUrl.pathname==='/v1/suggest')return route.fulfill({json:{vocabulary:[{type:'place',label:'テスト地点',center:[139.767,35.681]}]}});
      if(requestUrl.pathname==='/v1/search')return route.fulfill({json:{results:[]}});
      return route.abort();
    });
    const audit=async state=>{
      const report=await checkPage(page,policy);
      reports.push({viewport,state,...report});
      const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
      assert.equal(overflow,false,`${viewport.width}px ${state}: horizontal overflow`);
      await page.screenshot({path:resolve(output,`${viewport.width}-${state}.png`),fullPage:!['picker','favorites'].includes(state)});
      console.log(`${viewport.width}px ${state}: ${report.findings.length} findings`);
    };
    await page.goto(url);
    // Optional test-only font for containers without any Japanese system fonts.
    if(fontDir){
      for(const weight of [400,600,700,800]){
        await page.addStyleTag({url:`${url}/__ui-font/${weight}.css`});
      }
    }
    await page.locator('body[data-app-ready=true]').waitFor();
    await audit('home');
    await page.locator('#companyPickerButton').click();
    await page.locator('#companyPickerDialog').waitFor({state:'visible'});
    assert.equal(await page.locator('#companyPickerList input:checked').count(),publicIssuerCount);
    await audit('picker');
    await page.locator('#companyPickerClear').click();
    await page.locator('#companyPickerSearch').fill('すかいらーく');
    await page.locator('#companyPickerList input').first().check();
    await page.locator('#companyPickerApply').click();
    assert.equal(await page.locator('#companyChips [aria-pressed=true]').count(),1);
    await page.locator('#locateButton').click();
    await page.locator('#results .card').first().waitFor();
    await audit('results');
    const routeHref=await page.locator('#results .issuer-map-button').first().getAttribute('href');
    assert.match(routeHref,/maps\/dir\/\?api=1&destination=/);
    await page.locator('#results .favorite-toggle').first().click();
    await page.locator('#favoritesButton').click();
    await page.locator('#favoritesDialog .personal-card').first().waitFor();
    await page.locator('#favoritesDialog .personal-card').first().scrollIntoViewIfNeeded();
    await audit('favorites');
    await page.locator('#favoritesClose').click();
    await page.locator('#expiryTab').click();
    await page.locator('#expiryKeyword').waitFor();
    if(await page.locator('.expiry-row').count())await page.locator('.expiry-row').first().scrollIntoViewIfNeeded();
    await audit('expiry');
    // The current ledger may have no near deadlines: test an actual future holding.
    const owned=page.locator('.expiry-owned').first();
    if(await owned.count()){
      await owned.check();
      await page.locator('[data-view=owned]').click();
      assert.ok(await page.locator('.expiry-row').count()>0);
      assert.equal(await page.locator('.expiry-owned:checked').count(),await page.locator('.expiry-row').count());
    }
    await page.locator('#expiryBulkToggle').click();
    await audit('expiry-register');
    assert.deepEqual(errors,[],`${viewport.width}px runtime errors`);
    await context.close();
  }
  await writeFile(resolve(output,'lintapple.json'),JSON.stringify(reports,null,2));
  const findings=reports.flatMap(r=>r.findings.map(f=>({width:r.viewport.width,state:r.state,...f})));
  console.log(`${reports.length} UI states checked; ${findings.length} findings recorded in ui-reports/lintapple.json.`);
  if(strict&&findings.length)process.exitCode=1;
}finally{await browser?.close();await new Promise(resolve=>server.close(resolve));}
