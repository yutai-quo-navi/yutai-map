import fs from 'node:fs';import path from 'node:path';
const base='https://yutai-quo-navi.github.io/yutai-map/';
const ledger=JSON.parse(fs.readFileSync('data/expiry.json','utf8'));
const all=(ledger.entries||[]).filter(e=>e.status==='confirmed'&&e.expiry_date&&/^\d{4}-\d{2}-\d{2}$/.test(e.expiry_date)&&e.company_name);
const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Tokyo',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const slug=e=>String(e.code||'unknown').replace(/[^a-zA-Z0-9-]/g,'');
const days=(d)=>Math.round((Date.parse(d+'T00:00:00Z')-Date.parse(today+'T00:00:00Z'))/86400000);
const root='guides/expiry';fs.mkdirSync(root,{recursive:true});
function write(rel,title,h1,description,entries,links=''){
 const url=base+rel,rows=entries.map(e=>{const n=days(e.expiry_date);return '<li><strong>'+esc(e.company_name)+'（'+esc(e.code)+'）</strong> '+esc(e.benefit_name)+' ／ '+esc(e.expiry_type||'利用期限')+'：<time datetime="'+esc(e.expiry_date)+'">'+esc(e.expiry_date)+'</time> ／ <span data-date="'+esc(e.expiry_date)+'">'+(n<0?'期限終了':n===0?'本日期限':'あと'+n+'日')+'</span></li>';}).join('');
 const html='<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+esc(title)+'</title><meta name="description" content="'+esc(description)+'"><meta name="robots" content="index,follow"><link rel="canonical" href="'+esc(url)+'"><style>body{font-family:system-ui,sans-serif;max-width:850px;margin:auto;padding:22px;line-height:1.8;color:#24302b}a{color:#145b65}li{padding:12px 0;border-bottom:1px solid #ddd}nav a{margin-right:12px}small{color:#555}</style></head><body><nav><a href="'+base+'">優待店舗検索</a><a href="'+base+root+'/">優待期限一覧</a></nav><main><h1>'+esc(h1)+'</h1><p>'+esc(description)+'</p><p><small>表示基準日：<time id="today">'+today+'</time>（日本時間）。期限情報は変更される場合があります。利用前に発行会社の公式案内をご確認ください。</small></p>'+links+'<ul>'+rows+'</ul><p><a href="'+base+'">保有優待の期限管理・失効検索はこちら</a></p></main><script>function j(){return new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Tokyo",year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date())}function d(x){return Math.round((Date.parse(x+"T00:00:00Z")-Date.parse(j()+"T00:00:00Z"))/86400000)}document.getElementById("today").textContent=j();document.querySelectorAll("[data-date]").forEach(e=>{const n=d(e.dataset.date);e.textContent=n<0?"期限終了":n===0?"本日期限":"あと"+n+"日"});</script></body></html>';
 const dest=path.join(rel,'index.html');fs.mkdirSync(path.dirname(dest),{recursive:true});fs.writeFileSync(dest,html);return url;
}
const upcoming=all.filter(e=>e.expiry_date>=today).sort((a,b)=>a.expiry_date.localeCompare(b.expiry_date));
const months=[...new Set(upcoming.map(e=>e.expiry_date.slice(0,7)))].sort();
const monthLinks='<h2>月別に優待期限を調べる</h2><ul>'+months.map(m=>'<li><a href="'+base+root+'/'+m+'/">'+esc(m.replace('-','年')+'月')+'期限の株主優待</a></li>').join('')+'</ul>';
const urls=[write(root+'/','株主優待の有効期限一覧・失効防止｜優待期限を調べる','株主優待の期限一覧と失効防止','株主優待の利用期限・申込期限を調べるための一覧。期限切れ防止に役立つ最新の確認済みデータを掲載。',upcoming.slice(0,150),monthLinks)];
for(const m of months){const subset=upcoming.filter(e=>e.expiry_date.startsWith(m));urls.push(write(root+'/'+m+'/','株主優待の期限一覧 '+m+'｜失効防止・期限調査',m.replace('-','年')+'月に期限を迎える株主優待','株主優待券の利用期限やカタログ申込期限を確認。失効防止のための月別一覧。',subset));}
const byCode=new Map();for(const e of upcoming){const code=slug(e);if(!code)continue;if(!byCode.has(code))byCode.set(code,[]);byCode.get(code).push(e);}
for(const [code,entries] of byCode){const name=entries[0].company_name;urls.push(write(root+'/companies/'+code+'/',name+'の株主優待期限｜失効防止・有効期限調査',name+'の株主優待 有効期限',name+'の株主優待券・申込期限を確認。失効防止のための期限情報。',entries));}
const mapPath='sitemap.xml';const old=fs.readFileSync(mapPath,'utf8').replace(/<url><loc>https:\/\/yutai-quo-navi\.github\.io\/yutai-map\/guides\/expiry\/[^<]*<\/loc>(?:<lastmod>[^<]*<\/lastmod>)?<\/url>\s*/g,'');
const additions=urls.map(url=>'<url><loc>'+url+'</loc><lastmod>'+today+'</lastmod></url>').join('\n');
fs.writeFileSync(mapPath,old.replace('</urlset>',additions+'\n</urlset>'));console.log('Generated '+urls.length+' expiry pages.');
