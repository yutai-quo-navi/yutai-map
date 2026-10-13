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
// Compare the real companion site's header with the same browser and viewport.
const gasBase='https://raw.githubusercontent.com/yutai-quo-navi/yutai-quo-navi.github.io/main/';
const gasFiles=new Map(await Promise.all(['index.html','assets/brand.css','assets/header-align.css'].map(async path=>{
  const response=await fetch(gasBase+path);
  assert.ok(response.ok,'Companion header source must be available: '+path);
  return [path,await response.text()];
})));
assert.equal(gasFiles.get('assets/header-align.css'),await readFile(resolve(root,'assets/header-align.css'),'utf8'),'Both sites must share identical header geometry rules');
const gasSource=gasFiles.get('index.html');
gasFiles.set('index.html','<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>'+gasSource.match(/<style>([\s\S]*?)<\/style>/)[1]+'</style><link rel="stylesheet" href="./assets/brand.css"><link rel="stylesheet" href="./assets/header-align.css"></head><body class="gs-tool">'+gasSource.match(/<header class="site-header">[\s\S]*?<\/header>/)[0]+'</body></html>');
const server=createServer(async(req,res)=>{
  const pathname=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
  if(pathname.startsWith('/__gas-header/')){
    const path=pathname.slice('/__gas-header/'.length),body=gasFiles.get(path);
    if(body==null){res.writeHead(404).end();return;}
    res.writeHead(200,{'Content-Type':mime[extname(path)]||'text/plain'}).end(body);return;
  }
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
const hotelFixture={id:'ui-hotel',section:'hotel',title:'テスト宿泊優待',shortName:'表示確認ホテル',subtitle:'宿泊券で泊まる',issuer:{id:'ui-hotel',code:'9999',name:'表示確認ホテル'},updateMode:'manual',status:'public',availability:'continuous',radiusMeters:'all',sourceUrl:'https://example.com/benefit',checkedOn:'2026-10-12',description:'表示確認用の宿泊優待です。',stores:[{id:'ui-hotel-1',name:'表示検証用ホテル・長いホテル名とリゾート施設',address:'東京都○○区○○町（テスト用）',lat:35.682,lng:139.768,conditions:'事前予約が必要です。宿泊券の対象プランと除外日を公式情報でご確認ください。',verified:true}]};
let browser;
try{
  browser=await chromium.launch(process.env.UI_CHROMIUM_EXECUTABLE?{executablePath:process.env.UI_CHROMIUM_EXECUTABLE}:{});
  for(const viewport of policy.viewports){
    const context=await browser.newContext({viewport,hasTouch:viewport.width<=390,locale:'ja-JP',timezoneId:'Asia/Tokyo',reducedMotion:'reduce',geolocation:{latitude:35.681,longitude:139.767},permissions:['geolocation']});
    const page=await context.newPage();
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.route('**/*',async route=>{
      const requestUrl=new URL(route.request().url());
      if(requestUrl.origin===url){
        // Keep local issuer configs and the expiry ledger, stub remote hotel datasets.
        if(requestUrl.pathname==='/data/features/index.json') return route.fulfill({json:{features:[hotelFixture]}});
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
    const headerGeometry=()=>{
      const rect=node=>{const r=node.getBoundingClientRect();return {x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height};};
      const name=document.querySelector('.site-header .site-brand-name');
      const {x,y,height}=rect(name.firstElementChild);
      return {logo:rect(document.querySelector('.site-header .site-logo')),nameStart:{x,y,height},nameFont:['fontFamily','fontSize','lineHeight','fontWeight','letterSpacing'].map(key=>getComputedStyle(name)[key])};
    };
    const foodHeader=await page.evaluate(headerGeometry);
    const gasPage=await context.newPage();
    await gasPage.goto(url+'/__gas-header/index.html');
    assert.deepEqual(await gasPage.evaluate(headerGeometry),foodHeader,`${viewport.width}px: both tools must align their header icon and first title line`);
    assert.equal(await gasPage.locator('.site-logo svg circle').count(),1,'gas identity includes a magnifying glass');
    await gasPage.screenshot({path:resolve(output,`${viewport.width}-gas-header.png`)});
    await gasPage.close();
    // Repeated toggles must retain decoded image nodes, including other cards.
    await page.evaluate(async()=>{
      const card=document.querySelector('#companyChips [data-issuer="foodlife"]');
      const image=card.querySelector('.representative-mark-image');
      const neighbor=document.querySelector('#companyChips [data-issuer="yossix"] .representative-mark');
      const rect=node=>{
        const {x,y,width,height}=node.getBoundingClientRect();
        return {x:x+scrollX,y:y+scrollY,width,height};
      };
      const geometry=()=>JSON.stringify([...document.querySelectorAll('#companyChips [data-issuer]')]
        .map(button=>[rect(button),rect(button.querySelector('.representative-mark'))]));
      const initialGeometry=geometry();
      const {makeDeadlineBadge}=await import('/notification-badge.js');
      const fixture=document.createElement('span');fixture.className='voucher-deadline-bubble';fixture.textContent='128日で失効';
      card.append(makeDeadlineBadge(fixture,'layout-regression'));fixture.dataset.open='true';
      const initialBadge=JSON.stringify(rect(fixture));
      if(fixture.offsetParent!==card)throw new Error('Deadline badge is not anchored to its card');
      if(fixture.getBoundingClientRect().top>=card.getBoundingClientRect().top)throw new Error('Deadline badge does not overhang the top edge');
      if(getComputedStyle(card).overflow!=='visible')throw new Error('Deadline badge is clipped by its card');
      const chipGrid=document.querySelector('#companyChips');
      if(getComputedStyle(chipGrid).gridTemplateColumns.split(' ').length!==3)throw new Error('Dining grid lost its three columns');
      for(let i=0;i<10;i++){
        card.click();
        if(geometry()!==initialGeometry)throw new Error('Selection moved a dining cell or logo: '+initialGeometry+' -> '+geometry());
        if(JSON.stringify(rect(fixture))!==initialBadge)throw new Error('Selection moved the deadline badge');
        if(getComputedStyle(card).borderTopWidth!=='1px')throw new Error('Selection changed the structural border width');
        const selected=card.getAttribute('aria-pressed')==='true';
        if(getComputedStyle(card).backgroundColor!==(selected?'rgb(255, 240, 219)':'rgb(255, 255, 255)'))throw new Error('Selection is not using the shared warm palette');
        if(card.querySelector('.representative-mark-image')!==image)throw new Error('Dining toggle replaced its logo');
        if(document.querySelector('#companyChips [data-issuer="yossix"] .representative-mark')!==neighbor)throw new Error('Dining toggle replaced another logo');
      }
      const badgeRect=fixture.getBoundingClientRect();
      if(badgeRect.left<0||badgeRect.right>innerWidth)throw new Error('Three-digit deadline badge overflows the screen');
      if(getComputedStyle(image.parentElement).opacity!=='1')throw new Error('Selection changes logo contrast');
      fixture.remove();
      const {createBrandMark}=await import('../representative-marks.js?v=20261014-stable-logos');
      const pending=createBrandMark('dining','foodlife');
      if(!pending.classList.contains('has-real-logo'))throw new Error('Loading image exposes text fallback');
      pending.querySelector('img').dispatchEvent(new Event('error'));
      if(pending.classList.contains('has-real-logo')||pending.querySelector('img'))throw new Error('Failed image does not reveal fallback');
      const {initSpecialFeatures}=await import('../special-features.js?v=20261014-stable-logos');
      const root=document.createElement('div');document.body.append(root);
      await initSpecialFeatures({root,section:'hotel',getOrigin:()=>null,getCenterLabel:()=>'',getRadius:()=>10000,
        getDeadline:()=>null,createDeadlineBubble:()=>null,
        catalog:Promise.resolve([{id:'kyoritsu-hotel-discount',section:'hotel',title:'Logo regression fixture',shortName:'ホテル',
          status:'public',availability:'continuous',updateMode:'manual',checkedOn:'2026-10-14',sourceUrl:'https://example.com/benefit',issuer:{id:'fixture',code:'9999',name:'ホテル'},stores:[{id:'fixture',name:'ホテル',address:'東京都',conditions:'検証用',lat:35,lng:139,verified:true}]}])});
      const hotelImage=root.querySelector('.representative-mark-image');
      if(!hotelImage)throw new Error('Hotel logo fixture did not render');
      for(let i=0;i<10;i++){
        root.querySelector('[data-feature]').click();
        if(root.querySelector('.representative-mark-image')!==hotelImage)throw new Error('Hotel toggle replaced its logo');
      }
      root.remove();
    });
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
    await page.locator('#hotelTab').click();
    await page.locator('#hotelFeatures [data-feature="ui-hotel"]').waitFor();
    await audit('hotel-selection');
    await page.locator('#hotelFeatures [data-feature="ui-hotel"]').scrollIntoViewIfNeeded();
    const hotelGeometry=await page.locator('#hotelFeatures [data-feature="ui-hotel"]').boundingBox();
    await page.locator('#hotelFeatures [data-feature="ui-hotel"]').click();
    assert.deepEqual(await page.locator('#hotelFeatures [data-feature="ui-hotel"]').boundingBox(),hotelGeometry,'hotel selection must not move or resize the cell');
    assert.equal(await page.locator('#hotelFeatures .issuer-check').first().isVisible(),false,'selection check must be absent');
    assert.equal(await page.locator('#hotelFeatures [aria-pressed=true]').count(),1);
    await page.locator('#locateButton').click();
    await page.locator('#hotelFeatures .feature-card').waitFor();
    assert.match(await page.locator('#hotelFeatures .issuer-map-button').getAttribute('href'),/maps\/dir\//);
    await audit('hotel-results');
    await page.locator('#expiryTab').click();
    await page.locator('#expiryKeyword').waitFor();
    if(await page.locator('.expiry-row').count())await page.locator('.expiry-row').first().scrollIntoViewIfNeeded();
    await audit('expiry');
    // The current ledger may have no near deadlines: test an actual future holding.
    const owned=page.locator('.expiry-owned').first();
    if(await owned.count()){
      const ownFrame=page.locator('.expiry-own-button').first();
      for(let i=0;i<4;i++){
        if(viewport.width<=390)await ownFrame.tap();
        else await ownFrame.click();
        assert.equal(await ownFrame.evaluate(node=>getComputedStyle(node).outlineStyle),'none','pointer toggles must not leave an outer selection-like ring');
      }
      // A keyboard user still needs visible focus and a working Space toggle.
      await owned.click();
      await page.keyboard.press('Tab');
      await owned.focus();
      assert.equal(await ownFrame.evaluate(node=>getComputedStyle(node).outlineStyle),'solid','keyboard focus remains visible');
      const before=await owned.isChecked();
      await page.keyboard.press('Space');
      assert.equal(await owned.isChecked(),!before,'keyboard Space toggles ownership');
      assert.equal(await owned.evaluate(node=>node===document.activeElement),true,'keyboard focus survives the ownership update');
      assert.equal(await ownFrame.evaluate(node=>getComputedStyle(node).outlineStyle),'solid','keyboard focus ring survives the ownership update');
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
  // Exercise real motion as well as the reduced-motion layout audits above.
  const motionContext=await browser.newContext({viewport:{width:390,height:844},reducedMotion:'no-preference'});
  const motionPage=await motionContext.newPage();
  await motionPage.route('**/*',route=>new URL(route.request().url()).origin===url?route.continue():route.abort());
  await motionPage.goto(url+'/privacy.html');
  await motionPage.addStyleTag({url:url+'/soft-ui.css'});
  const motionResult=await motionPage.evaluate(async()=>{
    const {numberHTML,initNumberMotion}=await import('/number-motion.js');
    document.body.replaceChildren();
    const root=document.createElement('main');document.body.append(root);
    const stop=initNumberMotion(root);
    let starts=0;
    const original=Element.prototype.animate;
    Element.prototype.animate=function(...args){starts++;return original.apply(this,args);};
    const frame=()=>new Promise(resolve=>setTimeout(resolve,100));
    root.innerHTML=numberHTML('test',128);await frame();
    const initial=starts, label=root.firstElementChild.getAttribute('aria-label');
    await new Promise(resolve=>setTimeout(resolve,700));
    const value=[...root.querySelectorAll('.motion-digit')].map(slot=>[...slot.querySelectorAll('.motion-glyph')].find(glyph=>{const r=glyph.getBoundingClientRect(),s=slot.getBoundingClientRect();return r.top+r.height/2>s.top && r.top+r.height/2<s.bottom;})?.textContent).join('');
    root.innerHTML=numberHTML('test',128);await frame();const repeated=starts;
    root.innerHTML=numberHTML('test',46);await frame();const changed=starts;
    root.innerHTML='<div hidden>'+numberHTML('hidden',7)+'</div>';await frame();const hidden=starts;
    root.firstElementChild.hidden=false;await frame();const revealed=starts;
    stop();Element.prototype.animate=original;
    return {initial,value,label,repeated,changed,hidden,revealed};
  });
  assert.ok(motionResult.initial>0,'first visible numbers animate');
  assert.equal(motionResult.value,'128');assert.equal(motionResult.label,'128');
  assert.equal(motionResult.repeated,motionResult.initial,'unchanged values do not replay');
  assert.ok(motionResult.changed>motionResult.repeated,'changed values animate');
  assert.equal(motionResult.hidden,motionResult.changed,'hidden values wait');
  assert.ok(motionResult.revealed>motionResult.hidden,'revealed values animate');
  await motionPage.addStyleTag({url:url+'/notification-badge.css'});
  const badgeResult=await motionPage.evaluate(async()=>{
    const {makeDeadlineBadge,initNotificationBadges}=await import('/notification-badge.js');
    const root=document.createElement('div');root.id='companyChips';document.body.replaceChildren(root);
    const stop=initNotificationBadges(root);
    const render=value=>{
      const cell=document.createElement('button');cell.className='benefit-choice';
      const badge=document.createElement('span');badge.className='voucher-deadline-bubble';badge.textContent=value+'日で失効';
      cell.append(makeDeadlineBadge(badge,'test'));root.replaceChildren(cell);return badge;
    };
    const frame=()=>new Promise(resolve=>setTimeout(resolve,100));
    let badge=render(48);await frame();
    const text=badge.textContent, first=badge.getAnimations().map(a=>a.animationName);
    const cellAnimations=root.firstElementChild.getAnimations().length;
    badge=render(48);await frame();const repeated=badge.getAnimations({subtree:true}).length;
    const dotStyle=getComputedStyle(badge.querySelector('.t-badge-dot'));
    const shape={width:dotStyle.width,height:dotStyle.height,radius:dotStyle.borderRadius,color:dotStyle.backgroundColor};
    badge=render(47);await frame();const changed=badge.getAnimations().map(a=>a.animationName);
    const reels=root.querySelectorAll('[data-motion-value]').length;stop();
    return {text,first,cellAnimations,repeated,changed,reels,shape};
  });
  assert.equal(badgeResult.text,'48日');
  assert.deepEqual(badgeResult.shape,{width:'20px',height:'20px',radius:'50%',color:'rgb(199, 53, 58)'});
  assert.ok(badgeResult.first.includes('t-badge-slide-in'),'official diagonal slide runs');
  assert.equal(badgeResult.cellAnimations,0,'choice cell itself does not animate');
  assert.equal(badgeResult.repeated,0,'unchanged badge does not replay');
  assert.ok(badgeResult.changed.includes('t-badge-slide-in'),'updated badge animates');
  assert.equal(badgeResult.reels,0,'badge uses its own motion, not the number reel');
  await motionPage.emulateMedia({reducedMotion:'reduce'});
  assert.deepEqual(await motionPage.evaluate(async()=>{
    const {numberHTML,initNumberMotion}=await import('/number-motion.js');
    const root=document.createElement('main');document.body.replaceChildren(root);
    const stop=initNumberMotion(root);root.innerHTML=numberHTML('reduced',1234);
    await new Promise(resolve=>setTimeout(resolve,100));
    const result={value:root.textContent,animations:document.getAnimations().length};stop();return result;
  }),{value:'1,234',animations:0});
  assert.deepEqual(await motionPage.evaluate(async()=>{
    const {makeDeadlineBadge,initNotificationBadges}=await import('/notification-badge.js');
    const root=document.createElement('div');root.id='companyChips';document.body.replaceChildren(root);
    const stop=initNotificationBadges(root),badge=document.createElement('span');badge.textContent='7日で失効';
    root.append(makeDeadlineBadge(badge,'reduced'));
    await new Promise(resolve=>setTimeout(resolve,100));
    const result={text:badge.textContent,open:badge.dataset.open,animations:badge.getAnimations({subtree:true}).length};stop();return result;
  }),{text:'7日',open:'true',animations:0});
  await motionContext.close();
  await writeFile(resolve(output,'lintapple.json'),JSON.stringify(reports,null,2));
  const findings=reports.flatMap(r=>r.findings.map(f=>({width:r.viewport.width,state:r.state,...f})));
  console.log(`${reports.length} UI states checked; ${findings.length} findings recorded in ui-reports/lintapple.json.`);
  if(strict&&findings.length)process.exitCode=1;
}finally{await browser?.close();await new Promise(resolve=>server.close(resolve));}
