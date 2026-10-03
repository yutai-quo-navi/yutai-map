const API = 'https://api.openpoiapi.com/v1/search';
const qs = (s) => document.querySelector(s);

const els = {
  locate: qs('#locateButton'), status: qs('#status'), chips: qs('#companyChips'),
  radius: qs('#radiusSelect'), results: qs('#results'), count: qs('#resultCount'),
  selectAll: qs('#selectAllButton'), privacy: qs('#privacyDialog'),
  privacyButton: qs('#privacyButton'), privacyClose: qs('#privacyClose'),
  feedback: qs('#feedbackDialog'), feedbackButton: qs('#feedbackButton'),
  feedbackClose: qs('#feedbackClose'), feedbackForm: qs('#feedbackForm'),
  feedbackType: qs('#feedbackType'), feedbackCompany: qs('#feedbackCompany'),
  feedbackStore: qs('#feedbackStore'), feedbackUrl: qs('#feedbackUrl'),
  feedbackNote: qs('#feedbackNote'), categoryFilters: qs('#categoryFilters')
};

let companies = [];
let lastPosition = null;
let searching = false;
let lastResults = [];
let activeCategory = localStorage.getItem('yutai-category') || 'all';
const categoryLabels = {
  all:'すべて',
  restaurant:'食事',
  cafe:'カフェ',
  bakery:'パン',
  foodcourt:'フードコート',
  other:'その他'
};
const selected = new Set(JSON.parse(localStorage.getItem('yutai-selected') || '["create","colowide","skylark"]'));
els.radius.value = localStorage.getItem('yutai-radius') || '3000';

init();

async function init(){
  try {
    companies = await fetch('./data/companies.json', {cache:'no-store'}).then(r => r.json());
    renderChips();
    renderCategoryFilters();
  } catch(e){
    setStatus('優待データを読み込めませんでした');
  }

  els.locate.addEventListener('click', requestLocation);
  els.radius.addEventListener('change', () => {
    localStorage.setItem('yutai-radius', els.radius.value);
    if(lastPosition) searchNearby(lastPosition);
  });
  els.selectAll.addEventListener('click', toggleAll);
  els.privacyButton.addEventListener('click', () => els.privacy.showModal());
  els.privacyClose.addEventListener('click', () => els.privacy.close());
  els.feedbackButton.addEventListener('click', () => openFeedback());
  els.feedbackClose.addEventListener('click', () => els.feedback.close());
  els.feedbackForm.addEventListener('submit', submitFeedback);
  document.querySelectorAll('.bottom-nav__item').forEach(btn => btn.addEventListener('click', () => {
    const action = btn.dataset.action;
    if(action === 'nearby') window.scrollTo({top:0,behavior:'smooth'});
    if(action === 'filter') document.querySelector('.controls').scrollIntoView({behavior:'smooth'});
    if(action === 'privacy') els.privacy.showModal();
  }));
}

function renderChips(){
  els.chips.innerHTML = '';
  for(const c of companies){
    const isSelected = selected.has(c.id);
    const b = document.createElement('button');
    b.className='chip';
    b.type='button';
    b.setAttribute('aria-pressed', isSelected ? 'true' : 'false');
    b.setAttribute('aria-label', `${c.name}：${isSelected ? '選択中' : '未選択'}`);
    b.innerHTML = `
      <span class="chip-name">${esc(c.name)}</span>
      <span class="chip-state">${isSelected ? '選択中' : '未選択'}</span>
    `;
    b.addEventListener('click', () => {
      selected.has(c.id) ? selected.delete(c.id) : selected.add(c.id);
      persistSelection(); renderChips();
      updateSelectionSummary();
      if(lastPosition) searchNearby(lastPosition);
    });
    els.chips.appendChild(b);
  }
  updateSelectionSummary();
}

function updateSelectionSummary(){
  const summary = document.querySelector('#selectionSummary');
  if(summary) summary.textContent = `${selected.size} / ${companies.length} 選択中`;
  if(els.selectAll){
    els.selectAll.textContent = selected.size === companies.length ? 'すべて解除' : 'すべて選択';
  }
}

function toggleAll(){
  if(selected.size === companies.length) selected.clear(); else companies.forEach(c => selected.add(c.id));
  persistSelection(); renderChips();
  if(lastPosition) searchNearby(lastPosition);
}
function persistSelection(){ localStorage.setItem('yutai-selected', JSON.stringify([...selected])); }

async function requestLocation(){
  if(!navigator.geolocation){
    showError('このブラウザでは現在地取得に対応していません。');
    return;
  }

  els.locate.disabled = true;
  setStatus('現在地を確認しています…');

  let permissionState = '確認不可';
  try {
    if(navigator.permissions?.query){
      const permission = await navigator.permissions.query({name:'geolocation'});
      permissionState = permission.state;
    }
  } catch(e){
    permissionState = 'Safariでは取得不可';
  }

  navigator.geolocation.getCurrentPosition(
    p => {
      lastPosition = {lat:p.coords.latitude, lng:p.coords.longitude};
      searchNearby(lastPosition);
    },
    err => {
      els.locate.disabled = false;

      const codeName =
        err.code === 1 ? 'PERMISSION_DENIED' :
        err.code === 2 ? 'POSITION_UNAVAILABLE' :
        err.code === 3 ? 'TIMEOUT' :
        'UNKNOWN';

      const base =
        err.code === 1 ? '現在地の利用がブラウザ側から拒否されました。' :
        err.code === 2 ? '現在地を特定できませんでした。' :
        err.code === 3 ? '現在地の取得がタイムアウトしました。' :
        '現在地を取得できませんでした。';

      const detail = [
        `エラー: ${codeName}（code ${err.code}）`,
        `権限状態: ${permissionState}`,
        err.message ? `ブラウザ応答: ${err.message}` : ''
      ].filter(Boolean).join('<br>');

      showError(`${base}<br><small>${detail}</small>`);
      setStatus('現在地は保存していません');
    },
    {enableHighAccuracy:true, timeout:15000, maximumAge:60000}
  );
}

async function searchNearby(pos){
  if(searching) return;
  const targets = companies.filter(c => selected.has(c.id));
  if(!targets.length){ showError('検索する優待を1つ以上選んでください。'); els.locate.disabled=false; return; }

  searching = true; els.locate.disabled = true;
  els.results.className='results';
  els.results.innerHTML='<div class="empty-state"><p>近くの優待店を探しています…</p></div>';
  setStatus('OpenPOIで近隣店舗を検索中…');

  try{
    const radius = Number(els.radius.value);
    const batches = targets.flatMap(company => chunk(company.aliases, 14).map(aliases => ({company, aliases})));
    const responses = await Promise.allSettled(batches.map(b => queryOpenPOI(b, pos, radius)));
    const raw = responses.filter(r => r.status==='fulfilled').flatMap(r => r.value);
    const normalized = dedupe(raw).sort((a,b) => a.distance - b.distance);
    lastResults = normalized;
    renderFilteredResults(radius);
    setStatus(`${radius/1000}km以内を検索しました・現在地は運営者側に保存していません`);
  } catch(e){
    console.error(e); showError('検索中にエラーが発生しました。時間をおいて再度お試しください。');
    setStatus('検索できませんでした');
  } finally { searching=false; els.locate.disabled=false; }
}

async function queryOpenPOI(batch, pos, radius){
  // /v1/search はスペース区切りがOR検索。検索後にクライアント側でブランド名を厳密寄りに再判定する。
  const params = new URLSearchParams({
    q: batch.aliases.join(' '), center: `${pos.lng},${pos.lat}`, radius: String(radius), limit: '200'
  });
  const res = await fetch(`${API}?${params}`);
  if(!res.ok) throw new Error(`OpenPOI ${res.status}`);
  const data = await res.json();
  return (data.results || []).map(p => classify(p, batch.company, pos)).filter(Boolean);
}

function classify(p, company, origin){
  const hay = normalize(`${p.name||''} ${p.name_kana||''}`);
  const excludedLegacy = (company.excludedNames || []).some(x => hay.includes(normalize(x)));
  const excludedBrand = (company.excludedBrands || []).some(x => hay.includes(normalize(x)));
  const excludedStore = (company.excludedStores || []).some(x => hay.includes(normalize(x)));
  if(excludedLegacy || excludedBrand || excludedStore) return null;
  const alias = company.aliases.find(x => hay.includes(normalize(x)));
  if(!alias) return null;
  const category = company.categories?.[alias] || 'other';
  const lat = Number(p.lat), lng = Number(p.lng);
  if(!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
  return {
    ...p, lat, lng, company, matchedAlias: alias, category,
    distance: haversine(origin.lat, origin.lng, lat, lng)
  };
}
function normalize(s){ return String(s).normalize('NFKC').toLowerCase().replace(/[\s・･\-‐‑–—ー_]/g,''); }
function chunk(arr,n){ const out=[]; for(let i=0;i<arr.length;i+=n) out.push(arr.slice(i,i+n)); return out; }
function dedupe(items){
  const map=new Map();
  for(const x of items){
    const key=`${normalize(x.name)}|${x.lat.toFixed(5)}|${x.lng.toFixed(5)}`;
    const existing=map.get(key);
    if(!existing) map.set(key,x);
    else if(existing.company.id !== x.company.id){
      // 同一店舗が複数優待に該当する将来拡張用
      existing.also = [...(existing.also||[]), x.company];
    }
  }
  return [...map.values()];
}
function haversine(a,b,c,d){
  const R=6371000, rad=x=>x*Math.PI/180;
  const dLat=rad(c-a), dLng=rad(d-b);
  const q=Math.sin(dLat/2)**2+Math.cos(rad(a))*Math.cos(rad(c))*Math.sin(dLng/2)**2;
  return 2*R*Math.asin(Math.sqrt(q));
}
function distanceText(m){ return m < 1000 ? `${Math.round(m/10)*10}m` : `${(m/1000).toFixed(m<10000?1:0)}km`; }

function renderCategoryFilters(){
  if(!els.categoryFilters) return;
  els.categoryFilters.innerHTML='';
  for(const [id,label] of Object.entries(categoryLabels)){
    const b=document.createElement('button');
    b.type='button';
    b.className='category-filter';
    b.textContent=label;
    b.setAttribute('aria-pressed', activeCategory===id ? 'true' : 'false');
    b.addEventListener('click',()=>{
      activeCategory=id;
      localStorage.setItem('yutai-category',id);
      renderCategoryFilters();
      if(lastResults.length || lastPosition) renderFilteredResults(Number(els.radius.value));
    });
    els.categoryFilters.appendChild(b);
  }
}

function renderFilteredResults(radius){
  const items = activeCategory==='all' ? lastResults : lastResults.filter(x=>x.category===activeCategory);
  renderResults(items, radius);
}

function renderResults(items, radius){
  els.count.textContent = `${items.length}件`;
  if(!items.length){
    els.results.className='results empty-state';
    els.results.innerHTML=`<p>${radius/1000}km以内では<br>対象店舗を見つけられませんでした</p>`;
    return;
  }
  els.results.className='results'; els.results.innerHTML='';
  for(const x of items){
    const card=document.createElement('article'); card.className='card';
    const mapUrl=`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${x.lat},${x.lng}`)}`;
    card.innerHTML=`
      <div class="card-top">
        <div class="distance">${distanceText(x.distance)}<small>現在地から</small></div>
        <div class="store"><h3 class="store-name">${esc(x.name||x.matchedAlias)}</h3><p class="store-address">${esc(x.address||[x.prefecture,x.city].filter(Boolean).join(''))}</p></div>
      </div>
      <div class="badges">
        <span class="badge company">${esc(x.company.name)}優待</span>
        <span class="badge">${esc(x.matchedAlias)}</span>
        <span class="badge category">${esc(categoryLabels[x.category] || 'その他')}</span>
        <span class="badge beta">β 要公式確認</span>
      </div>
      <div class="card-actions">
        <a href="${esc(x.company.sourceUrl)}" target="_blank" rel="noopener">優待公式</a>
        <a class="map-link" href="${mapUrl}" target="_blank" rel="noopener">地図</a>
        <button class="feedback-link" type="button">情報修正</button>
      </div>`;
    card.querySelector('.feedback-link').addEventListener('click', () => openFeedback({
      company: x.company.name,
      store: x.name || x.matchedAlias
    }));
    els.results.appendChild(card);
  }
}

function openFeedback(prefill={}){
  els.feedbackCompany.value = prefill.company || '';
  els.feedbackStore.value = prefill.store || '';
  els.feedbackUrl.value = '';
  els.feedbackNote.value = '';
  els.feedbackType.value = prefill.store ? 'used' : 'missing-brand';
  els.feedback.showModal();
}

function submitFeedback(e){
  e.preventDefault();

  const typeLabels = {
    'used':'この店で優待を使えた',
    'not-used':'この店では優待を使えない',
    'missing-brand':'使えるブランドが抜けている',
    'wrong-company':'会社・ブランドの判定が違う',
    'other':'その他'
  };

  const type = typeLabels[els.feedbackType.value] || '情報提供';
  const company = els.feedbackCompany.value.trim();
  const store = els.feedbackStore.value.trim();
  const sourceUrl = els.feedbackUrl.value.trim();
  const note = els.feedbackNote.value.trim();

  const titleParts = ['[情報提供]', company, store].filter(Boolean);
  const title = titleParts.join(' ');
  const body = [
    '### 種別',
    type,
    '',
    '### 優待会社',
    company || '未入力',
    '',
    '### 店名・ブランド名',
    store || '未入力',
    '',
    '### 公式情報URL',
    sourceUrl || '未入力',
    '',
    '### 補足',
    note || 'なし',
    '',
    '---',
    '※この投稿には現在地の座標は含まれません。'
  ].join('\n');

  const url = new URL('https://github.com/yutai-quo-navi/yutai-map/issues/new');
  url.searchParams.set('title', title);
  url.searchParams.set('body', body);
  window.open(url.toString(), '_blank', 'noopener');
  els.feedback.close();
}

function showError(msg){ els.results.className='results'; els.results.innerHTML=`<div class="error-box">${esc(msg)}</div>`; els.count.textContent='—'; }
function setStatus(msg){ els.status.textContent=msg; }
function esc(s){ return String(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])); }
