import {japanDay, deadlineDays} from './expiry.js?v=20261009-benefit-order';

export const EXPIRY_GROUPS = [
  ['dining','外食優待'], ['hotel','ホテル優待'], ['leisure','レジャー・交通'],
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
export function upcomingExpiries(entries, now = new Date()) {
  const today = japanDay(now);
  const end = new Date(`${today}T00:00:00Z`); end.setUTCDate(end.getUTCDate()+60);
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
export function dueExpiryAlerts(entries, settings, now=new Date()) {
  return upcomingExpiries(entries,now).filter(entry=> {
    const setting=settings[entry.id];
    return entry.expiry_date && setting?.owned && setting.days.includes(deadlineDays(entry.expiry_date,now));
  });
}
const esc = value=>String(value ?? '').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const STORAGE_KEY='yutai-expiry-holdings-v1';
export function initExpirySearch({root, alertsRoot, read, write, now=()=>new Date()}) {
  let entries=[], settings=cleanExpirySettings(read(STORAGE_KEY,{})), query='', ownedOnly=false, loaded=false, failed=false;
  root.innerHTML='<p class="expiry-note">期限情報を読み込んでいます…</p>';
  const renderAlerts=()=> {
    const due=dueExpiryAlerts(entries,settings,now());
    alertsRoot.hidden=!due.length;
    alertsRoot.replaceChildren();
    if(!due.length) return;
    const title=document.createElement('p'); title.className='expiry-alert-title'; title.textContent='持っている優待の期限が近づいています'; alertsRoot.append(title);
    const list=document.createElement('ul');
    for(const entry of due) {
      const days=deadlineDays(entry.expiry_date,now());
      const item=document.createElement('li');
      item.textContent=`${entry.company_name}：${entry.benefit_name} ／ ${days===0 ? '本日' : days+'日後'}が${entry.expiry_type}（${entry.expiry_date.replaceAll('-','/')}）`;
      list.append(item);
    }
    alertsRoot.append(list);
    const button=document.createElement('button');button.type='button';button.className='text-button';button.textContent='失効検索で確認';button.addEventListener('click',()=>{document.getElementById('expiryTab').click();root.scrollIntoView({block:'start',behavior:'smooth'});});alertsRoot.append(button);
  };
  const save=()=>write(STORAGE_KEY,JSON.stringify(settings));
  const render=()=> {
    if(!loaded) return;
    const visible=upcomingExpiries(entries,now()).filter(entry=>(!ownedOnly || settings[entry.id]?.owned) &&
      `${entry.code} ${entry.company_name} ${entry.benefit_name} ${(entry.brands || []).join(' ')}`.normalize('NFKC').toLocaleLowerCase('ja').includes(query.normalize('NFKC').toLocaleLowerCase('ja')));
    root.innerHTML=`<div class="expiry-toolbar"><label class="expiry-search-label">銘柄・優待名から探す<input type="search" id="expiryKeyword" autocomplete="off" placeholder="会社名・証券コード・優待名" value="${esc(query)}"></label><label class="expiry-owned-filter"><input id="expiryOwnedOnly" type="checkbox" ${ownedOnly?'checked':''}>持ってるだけ</label></div><p class="expiry-note">今後60日以内の期限を表示。持ってる優待は、当日・1日前・2日前・3日前からアラートを複数選択できます。設定はこのブラウザに保存します。</p><p class="expiry-save-status" role="status"></p><div class="expiry-groups"></div>`;
    const groups=root.querySelector('.expiry-groups');
    if(failed) {groups.innerHTML='<p class="expiry-note">期限情報を読み込めませんでした。ページを再読み込みしてください。</p>';return;}
    if(!visible.length) groups.innerHTML='<p class="expiry-note">条件に合う期限情報はありません。</p>';
    for(const [key,title] of EXPIRY_GROUPS) {
      const rows=visible.filter(entry=>expiryGroup(entry)===key);if(!rows.length) continue;
      const section=document.createElement('section');section.className='expiry-group';
      section.innerHTML=`<h2>${title}<span>${rows.length}件</span></h2><table class="expiry-table"><caption class="visually-hidden">${title}の期限一覧</caption><thead><tr><th scope="col">持ってる</th><th scope="col">期限</th><th scope="col">銘柄・優待内容</th><th scope="col" class="expiry-alert-column">アラート</th></tr></thead><tbody></tbody></table>`;
      for(const entry of rows) {
        const setting=settings[entry.id] || {owned:false,days:[]};
        const days=entry.expiry_date ? deadlineDays(entry.expiry_date,now()) : null;
        const date=entry.expiry_date ? entry.expiry_date.replaceAll('-','/') : entry.research_month.replace('-','/')+'（日付未定）';
        const row=document.createElement('tr');row.dataset.expiry=entry.id;
        row.innerHTML=`<td class="expiry-owned-cell"><input type="checkbox" class="expiry-owned" aria-label="${esc(entry.company_name+' '+entry.benefit_name+'を持ってる')}" ${setting.owned?'checked':''}></td><td class="expiry-date"><span>${esc(date)}</span><small>${days===null ? 'アラート設定不可' : days===0 ? '本日まで' : 'あと'+days+'日'}</small><small>${esc(entry.expiry_type)}</small></td><td class="expiry-benefit"><span class="expiry-company">${esc(entry.company_name)}<small>${esc(entry.code)}</small></span><span>${esc(entry.benefit_name)}</span>${entry.issue?`<small>${esc(entry.issue)}</small>`:''}${entry.notes?`<details><summary>補足</summary><p>${esc(entry.notes)}</p></details>`:''}</td><td class="expiry-reminder-cell"><fieldset ${!setting.owned || days===null ? 'disabled':''}><legend>アラート</legend>${[0,1,2,3].map(day=>`<label><input type="checkbox" data-alert-day="${day}" ${setting.days.includes(day)?'checked':''}>${day===0?'当日':day+'日前'}</label>`).join('')}</fieldset></td>`;
        row.querySelector('.expiry-owned').addEventListener('change',event=> {
          const previous=settings[entry.id]; settings[entry.id]={owned:event.target.checked,days:previous?.days || (days===null ? [] : [0,1,2,3])};
          if(!save()) {settings[entry.id]=previous || {owned:false,days:[]}; event.target.checked=previous?.owned || false;root.querySelector('.expiry-save-status').textContent='保存できませんでした。ブラウザの保存設定をご確認ください。';return;}
          if(ownedOnly) render(); else row.querySelector('fieldset').disabled=!settings[entry.id].owned || days===null;
          row.querySelectorAll('[data-alert-day]').forEach(input=>input.checked=settings[entry.id].days.includes(Number(input.dataset.alertDay)));
          renderAlerts();
        });
        row.querySelectorAll('[data-alert-day]').forEach(input=>input.addEventListener('change',()=> {
          const previous=settings[entry.id];settings[entry.id]={...previous,days:[...row.querySelectorAll('[data-alert-day]:checked')].map(box=>Number(box.dataset.alertDay))};
          if(!save()) {settings[entry.id]=previous;input.checked=!input.checked;root.querySelector('.expiry-save-status').textContent='保存できませんでした。ブラウザの保存設定をご確認ください。';return;}renderAlerts();
        }));
        section.querySelector('tbody').append(row);
      }
      groups.append(section);
    }
    root.querySelector('#expiryKeyword').addEventListener('input',event=> {
      query=event.target.value;if(event.isComposing) return;const caret=event.target.selectionStart;render();const input=root.querySelector('#expiryKeyword');input.focus();try{input.setSelectionRange(caret,caret);}catch{}
    });
    root.querySelector('#expiryKeyword').addEventListener('compositionend',event=>{query=event.target.value;render();root.querySelector('#expiryKeyword').focus();});
    root.querySelector('#expiryOwnedOnly').addEventListener('change',event=>{ownedOnly=event.target.checked;render();});
  };
  return {
    setEntries(value) {entries=Array.isArray(value)?value:[];loaded=true;failed=false;render();renderAlerts();},
    fail() {loaded=true;failed=true;render();},
    refresh() {render();renderAlerts();},
    storageChanged(key) {if(key===STORAGE_KEY) {settings=cleanExpirySettings(read(STORAGE_KEY,{}));render();renderAlerts();}}
  };
}
