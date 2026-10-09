import {japanDay, deadlineDays} from './expiry.js?v=20261009-benefit-order';

export const EXPIRY_GROUPS = [
  ['dining','外食優待'], ['hotel','ホテル優待'], ['leisure','遊び・鉄道'],
  ['shopping','買物優待'], ['service','サービス優待'], ['catalog','カタログ・申込み'], ['other','その他']
];
const hotelCodes = new Set(['1925','5261','8934','8923','6547','3772','3479','8125','9416','9616']);
const transportCodes = new Set(['9201','9202','9052','9046','9007','3232','9005','9024']);
const serviceCodes = new Set(['9731','6036','2305','4718','9404','3663']);
export function expiryGroup(entry) {
  if (['申込期限','登録期限','交換期限','受取期限'].includes(entry.expiry_type) || entry.category === 'catalog') return 'catalog';
  if (entry.category === 'hotel' || (hotelCodes.has(entry.code) && entry.category !== 'dining') || /宿泊|ホテル/.test(entry.benefit_name || '')) return 'hotel';
  if (entry.category === 'service' || serviceCodes.has(entry.code)) return 'service';
  if (transportCodes.has(entry.code) || /鉄道|乗車|航空/.test(entry.benefit_name || '')) return 'leisure';
  return EXPIRY_GROUPS.some(([key])=>key===entry.category) ? entry.category : 'other';
}
export function upcomingExpiries(entries, now = new Date(), windowDays = 60) {
  const today = japanDay(now);
  const end = new Date(`${today}T00:00:00Z`); end.setUTCDate(end.getUTCDate()+(Number.isFinite(windowDays)?windowDays:36500));
  const endDay=end.toISOString().slice(0,10);
  return entries.filter(entry=>entry.status==='confirmed' && entry.id && entry.company_name &&
    (entry.expiry_date ? deadlineDays(entry.expiry_date,now) !== null && entry.expiry_date>=today && entry.expiry_date<=endDay :
      /^\d{4}-\d{2}$/.test(entry.research_month || '') && entry.research_month>=today.slice(0,7) && entry.research_month<=endDay.slice(0,7)))
    .sort((a,b)=>(a.expiry_date || a.research_month+'-99').localeCompare(b.expiry_date || b.research_month+'-99') || a.code.localeCompare(b.code));
}
export function cleanExpirySettings(value) {
  const clean={};
  if (!value || typeof value!=='object' || Array.isArray(value)) return clean;
  for(const [id,item] of Object.entries(value).slice(0,1000)) {
    if (!/^[a-z0-9][a-z0-9_-]*$/.test(id) || !item || typeof item!=='object') continue;
    clean[id]={owned:item.owned===true, days:Array.isArray(item.days) ? [...new Set(item.days.filter(day=>Number.isInteger(day) && day>=0 && day<=3))] : []};
  }
  return clean;
}
export function dueExpiryAlerts(entries, settings, now=new Date(), commonDays=null) {
  return upcomingExpiries(entries,now).filter(entry=> {
    const setting=settings[entry.id];
    return entry.expiry_date && setting?.owned && (commonDays ?? setting.days).includes(deadlineDays(entry.expiry_date,now));
  });
}
export const ALERT_DAYS_KEY='yutai-expiry-alert-days-v1';
export function cleanAlertDays(value) {
  return Array.isArray(value) ? [...new Set(value.filter(v=>Number.isInteger(v)&&v>=0&&v<=3))] : [0,1,2,3];
}
const normalize=value=>String(value).normalize('NFKC').toUpperCase().replace(/株式会社|[\s・･]/g,'').replace(/ホールディングス/g,'HD');
export function parseHoldings(text, entries) {
  const source=String(text).normalize('NFKC').toUpperCase();
  const companies=new Map();
  for(const entry of entries) if(entry.code && entry.company_name) companies.set(entry.code.toUpperCase(),entry.company_name);
  const matches=new Set(), unknown=new Set();
  // Names may occur inside copied brokerage rows; prices alone are never enough.
  const compact=normalize(source);
  for(const [code,name] of companies) if(normalize(name).length>=3 && compact.includes(normalize(name))) matches.add(code);
  const simple=/^[\s,、;；0-9A-Z]+$/.test(source) && source.split(/[\s,、;；]+/).filter(Boolean).every(token=>/^[0-9]{3}[0-9A-Z]$/.test(token));
  if(simple) for(const code of source.split(/[\s,、;；]+/).filter(Boolean)) (companies.has(code)?matches:unknown).add(code);
  else {
    // A code immediately followed by a name is distinct from numeric portfolio columns.
    const pattern=/(?:^|[\s,、;；])([0-9]{3}[0-9A-Z])[\s]+([^\s,、;；]+)/gu;
    for(const match of source.matchAll(pattern)) {
      const [,code,following]=match;
      if(!/[\p{L}]/u.test(following) || /^(詳細|現買|現売|積立|メール)/.test(following)) continue;
      const name=companies.get(code);
      if(name && (normalize(following).startsWith(normalize(name)) || normalize(name).startsWith(normalize(following)))) matches.add(code);
      else unknown.add(code);
    }
  }
  for(const code of matches) unknown.delete(code);
  return {matches:[...matches].map(code=>({code,name:companies.get(code)})),unknown:[...unknown]};
}
const esc = value=>String(value ?? '').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const STORAGE_KEY='yutai-expiry-holdings-v1';
export function initExpirySearch({root, alertsRoot, read, write, now=()=>new Date()}) {
  let entries=[], settings=cleanExpirySettings(read(STORAGE_KEY,{})), alertDays=cleanAlertDays(read(ALERT_DAYS_KEY,null));
  let query='', ownedOnly=false, loaded=false, failed=false, bulkOpen=false, paste='', parsed=null, message='', farOpen=false;
  const eligible=()=>upcomingExpiries(entries,now(),Infinity);
  const status=text=>{message=text;const node=root.querySelector('.expiry-save-status');if(node)node.textContent=text;};
  const saveSettings=next=>{
    if(!write(STORAGE_KEY,JSON.stringify(next))) {status('保存できませんでした。ブラウザの保存設定をご確認ください。');return false;}
    settings=next;return true;
  };
  const renderAlerts=()=> {
    const due=dueExpiryAlerts(entries,settings,now(),alertDays);
    alertsRoot.hidden=!due.length;alertsRoot.replaceChildren();
    if(!due.length)return;
    const title=document.createElement('p');title.className='expiry-alert-title';title.textContent='持っている優待の期限が近づいています';alertsRoot.append(title);
    const list=document.createElement('ul');
    for(const entry of due) {const li=document.createElement('li');li.textContent=`あと${deadlineDays(entry.expiry_date,now())}日　${entry.benefit_name}（${entry.company_name}）`;list.append(li);}
    alertsRoot.append(list);
    const button=document.createElement('button');button.type='button';button.className='text-button';button.textContent='失効検索で確認';button.onclick=()=>{document.getElementById('expiryTab').click();root.scrollIntoView({block:'start',behavior:'smooth'});};alertsRoot.append(button);
  };
  const rowHTML=entry=>{
    const generic=/^(株主)?(ご)?優待券|^(株主)?食事券|^株主優待[0-9０-９]/.test(entry.benefit_name || '');
    const main=generic ? entry.company_name : entry.benefit_name;
    const sub=generic ? entry.benefit_name : ''; 
    const days=entry.expiry_date?deadlineDays(entry.expiry_date,now()):null;
    const date=entry.expiry_date?`${Number(entry.expiry_date.slice(5,7))}/${Number(entry.expiry_date.slice(8))}まで`:`${entry.research_month}（日付未定）`;
    return `<li class="expiry-row" data-expiry="${esc(entry.id)}"><div class="expiry-countdown ${days!==null&&days<=3?'is-critical':days!==null&&days<=7?'is-soon':''}">${days===null?'<small>日付未定</small>':`あと<strong>${days}</strong>日`}</div><div class="expiry-benefit"><span>${esc(main)}</span>${sub?`<span class="expiry-benefit-description">${esc(sub)}</span>`:''}<small>${esc(entry.company_name)}（${esc(entry.code)}）</small><small>${esc(date)}${entry.expiry_type&&entry.expiry_type!=='利用期限'?' · '+esc(entry.expiry_type):''}</small></div><label class="expiry-own-button"><input type="checkbox" class="expiry-owned" aria-label="${esc(entry.company_name+' '+entry.benefit_name+'を持ってる')}" ${settings[entry.id]?.owned?'checked':''}><span>持ってる</span></label></li>`;
  };
  const groupHTML=(title,rows)=>rows.length?`<section class="expiry-group"><h2>${title}</h2><ul class="expiry-list">${rows.map(rowHTML).join('')}</ul></section>`:'';
  const render=()=>{
    if(!loaded){root.innerHTML='<p class="expiry-note">期限情報を読み込んでいます…</p>';return;}
    const all=eligible();
    const visible=all.filter(e=>(!ownedOnly||settings[e.id]?.owned)&&normalize(`${e.code} ${e.company_name} ${e.benefit_name} ${(e.brands||[]).join(' ')}`).includes(normalize(query)));
    const near=visible.filter(e=>e.expiry_date&&deadlineDays(e.expiry_date,now())<=7);
    const usual=visible.filter(e=>!near.includes(e)&&(!e.expiry_date?e.research_month<=japanDay(new Date(now().getTime()+60*86400000)).slice(0,7):deadlineDays(e.expiry_date,now())<=60));
    const far=visible.filter(e=>!near.includes(e)&&!usual.includes(e));
    const owned=all.filter(e=>settings[e.id]?.owned).length;
    root.innerHTML=`<div class="expiry-heading"><h2>失効検索</h2><p>優待の期限を、ひと目で。</p></div>
      <div class="expiry-register"><span>持ち株一覧を、ざっくりコピペでOK。</span><button type="button" id="expiryBulkToggle" aria-expanded="${bulkOpen}" aria-controls="expiryBulk">まとめて登録</button></div>
      <div id="expiryBulk" ${bulkOpen?'':'hidden'}><label for="expiryPaste">証券会社や管理アプリの一覧を、そのまま貼り付け</label><textarea id="expiryPaste" maxlength="100000" rows="5" placeholder="銘柄名・コードだけでも、株価や損益が混ざっていてもOK">${esc(paste)}</textarea><button type="button" id="expiryParse">銘柄を読み取る</button><div id="expiryParseResult" aria-live="polite">${parsed?`<p>${parsed.matches.length}銘柄が期限DBと一致しました。</p><ul>${parsed.matches.map(m=>`<li>${esc(m.name)}（${esc(m.code)}）</li>`).join('')}</ul>${parsed.unknown.length?`<p>期限DB未登録・照合できないコード：${parsed.unknown.map(esc).join('、')}</p>`:''}${!parsed.matches.length?'<p>見つからない場合は、銘柄名やコードだけを貼り付けてください。</p>':''}<button type="button" id="expiryImport" ${parsed.matches.length?'':'disabled'}>${parsed.matches.length}銘柄の優待をまとめて登録</button>`:''}</div><p class="expiry-note">現在掲載されている未失効の優待を登録します。券を持っていないものは、登録後にチェックを外せます。貼り付けた内容は送信・保存しません。</p></div>
      <div class="expiry-common"><p>「持ってる」を選ぶと、期限前にお知らせ。</p><fieldset><legend>お知らせする日</legend><div class="expiry-day-options">${[3,2,1,0].map(day=>`<label><input type="checkbox" data-alert-day="${day}" ${alertDays.includes(day)?'checked':''}><span>${day===0?'当日':day+'日前'}</span></label>`).join('')}</div></fieldset><p class="expiry-note">このサイトを開いたときにお知らせします。${alertDays.length?'':'通知日は選択されていません。'}</p></div>
      <div class="expiry-view-tabs"><button type="button" data-view="all" aria-pressed="${!ownedOnly}">すべて</button><button type="button" data-view="owned" aria-pressed="${ownedOnly}">持ってる ${owned}</button></div>
      <label class="expiry-search-label"><span class="visually-hidden">銘柄・優待名から探す</span><input type="search" id="expiryKeyword" autocomplete="off" placeholder="銘柄名・コード・優待名で絞り込み" value="${esc(query)}"></label><p class="expiry-save-status" role="status">${esc(message)}</p>
      <div class="expiry-groups">${failed?'<p>期限情報を読み込めませんでした。ページを再読み込みしてください。</p>':groupHTML('あと7日以内',near)+EXPIRY_GROUPS.map(([key,title])=>groupHTML(title,usual.filter(e=>expiryGroup(e)===key))).join('')+(far.length?`<details class="expiry-future" ${farOpen?'open':''}><summary>もっと先の期限を見る（61日以降・${far.length}件）</summary>${EXPIRY_GROUPS.map(([key,title])=>groupHTML(title,far.filter(e=>expiryGroup(e)===key))).join('')}</details>`:'')+(!visible.length?'<p class="expiry-note">'+(ownedOnly?'「持ってる」を選ぶと、ここに表示されます。':'条件に合う期限情報はありません。')+'</p>':'')}</div><p class="expiry-note expiry-storage-note">選択はこのブラウザに保存されます。期限を過ぎた優待は自動で表示から外れます。</p>`;
    root.querySelector('#expiryBulkToggle').onclick=()=>{bulkOpen=!bulkOpen;render();if(bulkOpen)root.querySelector('#expiryPaste').focus();};
    root.querySelector('#expiryPaste').oninput=e=>{paste=e.target.value;parsed=null;root.querySelector('#expiryParseResult').replaceChildren();};
    root.querySelector('#expiryParse').onclick=()=>{parsed=parseHoldings(paste,entries);render();};
    root.querySelector('#expiryImport')?.addEventListener('click',()=>{
      const codes=new Set(parsed.matches.map(m=>m.code)),next={...settings};let count=0;
      for(const e of all)if(codes.has(e.code)){next[e.id]={owned:true,days:settings[e.id]?.days||[0,1,2,3]};count++;}
      if(!count){status('一致した銘柄に、現在掲載中の未失効の優待はありません。');return;}
      if(!saveSettings(next))return;
      bulkOpen=false;paste='';parsed=null;message=`${count}件の優待を「持ってる」に登録しました。`;render();renderAlerts();root.querySelector('#expiryBulkToggle').focus();
    });
    root.querySelectorAll('[data-alert-day]').forEach(input=>input.onchange=()=>{
      const next=[...root.querySelectorAll('[data-alert-day]:checked')].map(i=>Number(i.dataset.alertDay));
      if(!write(ALERT_DAYS_KEY,JSON.stringify(next))){input.checked=!input.checked;status('通知日の設定を保存できませんでした。');return;}
      alertDays=next;renderAlerts();const day=input.dataset.alertDay;render();root.querySelector(`[data-alert-day="${day}"]`).focus();
    });
    root.querySelectorAll('.expiry-owned').forEach(input=>input.onchange=()=>{
      const id=input.closest('[data-expiry]').dataset.expiry,next={...settings,[id]:{owned:input.checked,days:settings[id]?.days||[0,1,2,3]}};
      if(!saveSettings(next)){input.checked=!input.checked;return;}
      render();renderAlerts();root.querySelector(`[data-expiry="${id}"] .expiry-owned`)?.focus();
    });
    root.querySelectorAll('[data-view]').forEach(button=>button.onclick=()=>{ownedOnly=button.dataset.view==='owned';render();root.querySelector(`[data-view="${ownedOnly?'owned':'all'}"]`).focus();});
    const filter=event=>{query=event.target.value;if(event.isComposing)return;render();root.querySelector('#expiryKeyword').focus();};
    root.querySelector('#expiryKeyword').addEventListener('input',filter);root.querySelector('#expiryKeyword').addEventListener('compositionend',filter);
    root.querySelector('.expiry-future')?.addEventListener('toggle',event=>{farOpen=event.target.open;});
  };
  render();
  return {setEntries(value){entries=Array.isArray(value)?value:[];loaded=true;failed=false;render();renderAlerts();},fail(){loaded=true;failed=true;render();},refresh(){render();renderAlerts();},storageChanged(key){if(key===null||key===STORAGE_KEY||key===ALERT_DAYS_KEY){settings=cleanExpirySettings(read(STORAGE_KEY,{}));alertDays=cleanAlertDays(read(ALERT_DAYS_KEY,null));render();renderAlerts();}}};
}
