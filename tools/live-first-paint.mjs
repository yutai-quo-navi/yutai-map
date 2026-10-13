import {chromium} from 'playwright';
const url='https://yutai-quo-navi.github.io/yutai-map/';
const browser=await chromium.launch({headless:true});
try{
  for(const width of [390,1366]){
    const context=await browser.newContext({viewport:{width,height:width===390?844:900},locale:'ja-JP',timezoneId:'Asia/Tokyo'});
    const page=await context.newPage();
    const failed=[];
    page.on('requestfailed',req=>failed.push({url:req.url(),reason:req.failure()?.errorText}));
    const start=Date.now();
    const response=await page.goto(url,{waitUntil:'domcontentloaded',timeout:30000});
    const domMs=Date.now()-start;
    await page.waitForFunction(()=>[...document.querySelectorAll('#companyChips .representative-mark-image')].slice(0,9).every(img=>img.complete&&img.naturalWidth>0),undefined,{timeout:20000});
    const firstNineMs=Date.now()-start;
    await page.waitForFunction(()=>[...document.querySelectorAll('#companyChips .representative-mark-image')].every(img=>img.complete&&img.naturalWidth>0),undefined,{timeout:20000});
    const allMs=Date.now()-start;
    const assets=await page.evaluate(()=>{
      const imgs=[...document.querySelectorAll('#companyChips .representative-mark-image')];
      const entries=performance.getEntriesByType('resource').filter(x=>x.name.includes('/assets/'));
      return {logo_count:imgs.length,logo_loaded:imgs.filter(x=>x.complete&&x.naturalWidth>0).length,
        app_ready:document.body.dataset.appReady||'',asset_requests:entries.length,
        longest_asset_ms:Math.round(Math.max(...entries.map(x=>x.responseEnd),0))};
    });
    console.log(JSON.stringify({event:'cold_live_first_visit',viewport:width,status:response.status(),dom_ms:domMs,first_nine_ms:firstNineMs,all_logos_ms:allMs,...assets,failed:failed.slice(0,5)}));
    await context.close();
  }
} finally {await browser.close();}
