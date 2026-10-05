import {initExpiry} from './expiry.js';

const API = 'https://api.openpoiapi.com/v1/search';
const SUGGEST_API = 'https://api.openpoiapi.com/v1/suggest';
const STORE_API = 'https://yutai-map-api.yutaisamurai.workers.dev/v1/stores/search';
let visibleCompanyIds = new Set();
const qs = (s) => document.querySelector(s);
function readSetting(key, fallback=null){ try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; } }
function readJSON(key, fallback){ try { return JSON.parse(readSetting(key)) ?? fallback; } catch { return fallback; } }
function writeSetting(key, value){
  try { localStorage.setItem(key, value); document.querySelectorAll('.storage-status').forEach(el=>el.textContent=''); return true; }
  catch { const message='このブラウザでは保存できません。保存領域の設定や空き容量をご確認ください。'; setStatus(message); document.querySelectorAll('dialog[open] .storage-status').forEach(el=>el.textContent=message); return false; }
}

const els = {
  locate: qs('#locateButton'), status: qs('#status'), chips: qs('#companyChips'),
  radius: qs('#radiusSelect'), results: qs('#results'), count: qs('#resultCount'),
  picker: qs('#companyPickerDialog'), pickerButton: qs('#companyPickerButton'),
  pickerSearch: qs('#companyPickerSearch'), pickerList: qs('#companyPickerList'),
  pickerCount: qs('#companyPickerCount'), pickerApply: qs('#companyPickerApply'),
  privacy: qs('#privacyDialog'),
  privacyButton: qs('#privacyButton'), privacyClose: qs('#privacyClose'),
  headerSearchButton: qs('#headerSearchButton'), menuButton: qs('#menuButton'),
  navMenu: qs('#navMenu'), menuFeedbackButton: qs('#menuFeedbackButton'),
  history: qs('#historyDialog'), historyButton: qs('#historyButton'),
  historyClose: qs('#historyClose'), historyCompanyFilter: qs('#historyCompanyFilter'),
  historyTypeFilter: qs('#historyTypeFilter'), historyStatus: qs('#historyStatus'),
  historyList: qs('#historyList'), historyPrev: qs('#historyPrev'),
  historyNext: qs('#historyNext'), historyPageLabel: qs('#historyPageLabel'),
  feedback: qs('#feedbackDialog'), feedbackButton: qs('#feedbackButton'),
  feedbackClose: qs('#feedbackClose'), feedbackForm: qs('#feedbackForm'),
  feedbackType: qs('#feedbackType'), feedbackCompany: qs('#feedbackCompany'),
  feedbackStore: qs('#feedbackStore'), feedbackUrl: qs('#feedbackUrl'),
  feedbackNote: qs('#feedbackNote'), categoryFilters: qs('#categoryFilters'),
  searchMode: qs('#searchMode'), currentSearchPanel: qs('#currentSearchPanel'),
  placeSearchPanel: qs('#placeSearchPanel'), placeInput: qs('#placeInput'),
  placeSuggestions: qs('#placeSuggestions'),
  brandSearch: qs('#brandSearch'), brandSelect: qs('#brandSelect'),
  favorites: qs('#favoritesDialog'), favoritesList: qs('#favoritesList'),
  favoritesButton: qs('#favoritesButton'), favoritesCount: qs('#favoritesCount'),
  memo: qs('#memoDialog'), memoForm: qs('#memoForm'), memoList: qs('#memoList'),
  memoCompany: qs('#memoCompany'), memoDate: qs('#memoDate'), memoAmount: qs('#memoAmount'),
  memoNote: qs('#memoNote'), memoId: qs('#memoId'), memoSummary: qs('#memoSummary')
};

let companies = [];
let draftSelection = new Set();
let pickerCompanies = [];
let lastPosition = null;
let lastCenterLabel = '現在地';
let searching = false;
let pendingSearch = null;
let lastResults = [];
let categoryCounts = null;
let suggestTimer = null;
// Category is a temporary refinement; do not carry a hidden restriction across visits.
let activeCategory = 'all';
let historyEvents = [];
let historyLoaded = false;
let historyPage = 1;
const HISTORY_PAGE_SIZE = 20;
const categoryLabels = {
  all:'すべて',
  restaurant:'食事',
  cafe:'カフェ',
  bakery:'パン',
  foodcourt:'フードコート',
  other:'その他'
};
const selectedSaved = readJSON('yutai-selected', ['create','skylark']);
const selected = new Set(Array.isArray(selectedSaved) ? selectedSaved.filter(x => typeof x==='string') : ['create','skylark']);
let brandCatalog = [];
let activeBrand = readSetting('yutai-brand', '');
let brandRequest = 0;
const savedFavorites = readJSON('yutai-favorites', []);
let favorites = Array.isArray(savedFavorites) ? savedFavorites.filter(x => x && typeof x.key==='string' && typeof x.name==='string').slice(0,500) : [];
const savedMemos = readJSON('yutai-memos', []);
let memos = Array.isArray(savedMemos) ? savedMemos.filter(x => x && typeof x.id==='string' && typeof x.issuer==='string' && /^\d{4}-\d{2}-\d{2}$/.test(x.date)).slice(0,200) : [];
els.radius.value = readSetting('yutai-radius') || '3000';

const expiryUI = initExpiry({
  resolveIssuer: entry => companies.find(c => visibleCompanyIds.has(c.id) && (entry.issuer_id ? c.id === entry.issuer_id : c.code === entry.code)),
  search: (entry, issuer) => {
    selected.clear(); selected.add(issuer.id);
    activeBrand=''; els.brandSearch.value='';
    if(entry.search_brand){
      const brand=brandCatalog.find(b => b.issuer_id === issuer.id && b.name === entry.search_brand);
      if(brand) activeBrand=brandKey(brand);
    }
    writeSetting('yutai-brand', activeBrand); resetCategoryFilter();
    persistSelection(); renderChips(); renderBrandOptions();
    qs('.hero').scrollIntoView({behavior:'smooth',block:'start'});
    if(lastPosition) searchNearby(lastPosition,lastCenterLabel);
    else setStatus('優待を選択しました。場所を指定するか、現在地から探してください');
  }
});
init();

async function init(){
  try {
    const manifest = await fetch('./data/issuers/index.json', {cache:'no-store'}).then(r => r.json());
    const dev = new URLSearchParams(location.search).get('dev');
    const visibleIssuers = manifest.issuers.filter(x =>
      x.status === 'public' || (x.status === 'development' && (dev === x.id || dev === 'all'))
    );
    companies = await Promise.all(
      visibleIssuers.map(async x => {
        const c = await fetch(x.config, {cache:'no-store'}).then(r => r.json());
        if(c.storeDataPath && !['official_coordinates','worker_reference'].includes(c.locationMode)){
          try{
            const db = await fetch(c.storeDataPath, {cache:'no-store'}).then(r => r.json());
            c.officialStores = db.stores || [];
          }catch(e){
            console.warn(`公式店舗DBを読み込めませんでした: ${c.id}`, e);
            c.officialStores = [];
          }
        }else{
          c.officialStores = [];
        }
        return c;
      })
    );
    visibleCompanyIds = new Set(companies.map(c => c.id));
    for(const id of [...selected]) if(!visibleCompanyIds.has(id)) selected.delete(id);
    if(!selected.size && readSetting('yutai-selected') === null){
      companies.filter(c => c.status === 'public').forEach(c => selected.add(c.id));
    }
    persistSelection();
    renderChips();
    renderCategoryFilters();
    await loadBrandCatalog();
    renderMemoCompanies(); renderMemos(); updateFavoritesCount(); expiryUI.refresh();
  } catch(e){
    setStatus('優待データを読み込めませんでした');
  }

  els.locate.addEventListener('click', requestLocation);
  els.searchMode?.querySelectorAll('.search-mode-button').forEach(btn => btn.addEventListener('click', () => setSearchMode(btn.dataset.mode)));
  els.placeSearchPanel?.addEventListener('submit', submitPlaceSearch);
  els.placeInput?.addEventListener('input', () => {
    clearTimeout(suggestTimer);
    suggestTimer = setTimeout(loadPlaceSuggestions, 220);
  });
  els.radius.addEventListener('change', () => {
    writeSetting('yutai-radius', els.radius.value);
    if(lastPosition) searchNearby(lastPosition, lastCenterLabel);
  });
  els.pickerButton.addEventListener('click', openCompanyPicker);
  qs('#companyPickerClose').addEventListener('click', () => els.picker.close());
  els.pickerSearch.addEventListener('input', renderCompanyPicker);
  qs('#companyPickerAll').addEventListener('click', () => {
    pickerCompanies.forEach(c => draftSelection.add(c.id)); renderCompanyPicker();
  });
  qs('#companyPickerClear').addEventListener('click', () => {
    draftSelection.clear(); renderCompanyPicker();
  });
  els.pickerApply.addEventListener('click', () => {
    selected.clear(); draftSelection.forEach(id => selected.add(id));
    resetCategoryFilter();
    persistSelection(); renderChips(); renderBrandOptions(); els.picker.close();
    if(lastPosition) searchNearby(lastPosition, lastCenterLabel);
  });
  els.headerSearchButton?.addEventListener('click', () => {
    closeNavMenu();
    expiryUI.showStore();
    qs('.hero')?.scrollIntoView({behavior:'smooth', block:'start'});
    setTimeout(() => { if(!els.placeSearchPanel.hidden) els.placeInput?.focus(); }, 350);
  });
  els.menuButton?.addEventListener('click', (event) => {
    event.stopPropagation();
    const opening = els.navMenu.hidden;
    els.navMenu.hidden = !opening;
    els.menuButton.setAttribute('aria-expanded', opening ? 'true' : 'false');
  });
  els.navMenu?.addEventListener('click', event => event.stopPropagation());
  document.addEventListener('click', closeNavMenu);
  document.addEventListener('keydown', event => { if(event.key === 'Escape') closeNavMenu(); });
  els.privacyButton.addEventListener('click', () => { closeNavMenu(); els.privacy.showModal(); });
  els.privacyClose.addEventListener('click', () => els.privacy.close());
  els.historyButton?.addEventListener('click', () => { closeNavMenu(); openHistory(); });
  els.historyClose?.addEventListener('click', () => els.history.close());
  els.historyCompanyFilter?.addEventListener('change', () => { historyPage=1; renderHistory(); });
  els.historyTypeFilter?.addEventListener('change', () => { historyPage=1; renderHistory(); });
  els.historyPrev?.addEventListener('click', () => { if(historyPage>1){ historyPage--; renderHistory(); } });
  els.historyNext?.addEventListener('click', () => { historyPage++; renderHistory(); });
  els.feedbackButton.addEventListener('click', () => openFeedback());
  els.menuFeedbackButton?.addEventListener('click', () => { closeNavMenu(); openFeedback(); });
  els.feedbackClose.addEventListener('click', () => els.feedback.close());
  els.feedbackForm.addEventListener('submit', submitFeedback);
  els.brandSearch.addEventListener('input', renderBrandOptions);
  els.brandSelect.addEventListener('change', () => {
    activeBrand=els.brandSelect.value; writeSetting('yutai-brand',activeBrand);
    resetCategoryFilter();
    if(lastPosition) searchNearby(lastPosition,lastCenterLabel);
  });
  els.favoritesButton.addEventListener('click', () => { renderFavorites(); els.favorites.showModal(); });
  qs('#favoritesClose').addEventListener('click', () => els.favorites.close());
  qs('#memoButton').addEventListener('click', () => { renderMemos(); els.memo.showModal(); });
  qs('#memoClose').addEventListener('click', () => els.memo.close());
  qs('#memoCancel').addEventListener('click', resetMemoForm);
  els.memoForm.addEventListener('submit', saveMemo);
  window.addEventListener('storage', event => {
    if(event.key==='yutai-favorites'){
      const next=readJSON('yutai-favorites',[]);
      if(Array.isArray(next)) favorites=next.filter(x=>x && typeof x.key==='string' && typeof x.name==='string').slice(0,500);
      updateFavoritesCount(); renderFavorites(); updateFavoriteButtons();
    }
    if(event.key==='yutai-memos'){
      const next=readJSON('yutai-memos',[]);
      if(Array.isArray(next)) memos=next.filter(x=>x && typeof x.id==='string' && typeof x.issuer==='string' && /^\d{4}-\d{2}-\d{2}$/.test(x.date)).slice(0,200);
      renderMemos();
    }
  });
}

function closeNavMenu(){
  if(!els.navMenu || els.navMenu.hidden) return;
  els.navMenu.hidden = true;
  els.menuButton?.setAttribute('aria-expanded', 'false');
}

// Stable issuer colors are shared by summary, picker and Google Maps buttons.
function issuerTone(id){
  const fixed = {skylark:0, colowide:1, create:2, monogatari:3, zensho:4, yoshinoya:5};
  if(Object.hasOwn(fixed, id)) return `issuer-tone-${fixed[id]}`;
  let hash = 0;
  for(const ch of String(id)) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return `issuer-tone-${hash % 8}`;
}
function renderChips(){
  els.chips.innerHTML = '';
  const chosen = companies.filter(c => visibleCompanyIds.has(c.id) && selected.has(c.id));
  for(const c of chosen.slice(0,3)){
    const badge = document.createElement('span');
    badge.className = `selected-issuer ${issuerTone(c.id)}`;
    badge.textContent = `✓ ${c.name}`;
    els.chips.appendChild(badge);
  }
  if(chosen.length > 3){
    const more = document.createElement('span'); more.className='selected-more';
    more.textContent = `＋${chosen.length - 3}社`; els.chips.appendChild(more);
  }
  if(!chosen.length) els.chips.textContent = '使いたい優待を選んでください';
  qs('#selectionSummary').textContent = `${chosen.length}社 選択中`;
}
function openCompanyPicker(){
  draftSelection = new Set(selected);
  // Sort once on opening so checkbox rows never move while selecting.
  pickerCompanies = companies.filter(c => visibleCompanyIds.has(c.id)).sort((a,b) =>
    Number(selected.has(b.id)) - Number(selected.has(a.id)) || a.name.localeCompare(b.name,'ja'));
  els.pickerSearch.value = ''; renderCompanyPicker(); els.picker.showModal();
  els.pickerList.scrollTop = 0;
}
function renderCompanyPicker(){
  const normalize = value => String(value).normalize('NFKC').toLocaleLowerCase('ja').replace(/\s+/g,'');
  const query = normalize(els.pickerSearch.value);
  const matches = pickerCompanies.filter(c => normalize([c.name,...(c.searchNames || []),...(c.aliases || [])].join(' ')).includes(query));
  els.pickerList.innerHTML = '';
  for(const c of matches){
    const row = document.createElement('label'); row.className=`picker-row ${issuerTone(c.id)}`;
    const box = document.createElement('input'); box.type='checkbox'; box.checked=draftSelection.has(c.id);
    const label = document.createElement('span'); label.className='picker-row-text';
    const title = document.createElement('strong'); title.textContent=c.name;
    const aliases = document.createElement('small');
    aliases.textContent = (c.aliases || []).slice(0,4).join('・') + ((c.aliases || []).length > 4 ? ' ほか' : '');
    label.append(title,aliases); row.append(box,label);
    box.addEventListener('change', () => {
      box.checked ? draftSelection.add(c.id) : draftSelection.delete(c.id);
      updatePickerCount();
    });
    els.pickerList.appendChild(row);
  }
  if(!matches.length){
    const empty=document.createElement('p'); empty.className='picker-empty';
    empty.textContent='一致する優待会社・系列店がありません'; els.pickerList.appendChild(empty);
  }
  updatePickerCount();
}
function updatePickerCount(){
  els.pickerCount.textContent = `${draftSelection.size} / ${pickerCompanies.length}社 選択中`;
  els.pickerApply.textContent = `選択を反映して戻る（${draftSelection.size}社）`;
}
function persistSelection(){ writeSetting('yutai-selected', JSON.stringify([...selected])); }

function setSearchMode(mode){
  const current = mode !== 'place';
  els.currentSearchPanel.hidden = !current;
  els.placeSearchPanel.hidden = current;
  els.searchMode.querySelectorAll('.search-mode-button').forEach(btn => {
    btn.setAttribute('aria-pressed', btn.dataset.mode === mode ? 'true' : 'false');
  });
  if(mode === 'place'){
    setStatus('地名・駅名・施設名を入力してください');
    setTimeout(() => els.placeInput.focus(), 0);
  }else{
    setStatus('ボタンを押すまで現在地は取得しません');
  }
}

async function loadPlaceSuggestions(){
  const q = els.placeInput.value.trim();
  if(q.length < 2){
    els.placeSuggestions.hidden = true;
    els.placeSuggestions.innerHTML = '';
    return;
  }
  try{
    const params = new URLSearchParams({q, limit:'8', fields:'minimal'});
    const res = await fetch(`${SUGGEST_API}?${params}`);
    if(!res.ok) return;
    const data = await res.json();
    const candidates = [];
    for(const v of (data.vocabulary || [])){
      if(v.type === 'place' && Array.isArray(v.center)){
        candidates.push({label:v.label, sub:[v.prefecture,v.city].filter(Boolean).join(' '), lat:Number(v.center[1]), lng:Number(v.center[0])});
      }
    }
    for(const s of (data.suggestions || [])){
      candidates.push({label:s.name, sub:s.address || '', lat:Number(s.lat), lng:Number(s.lng)});
    }
    renderPlaceSuggestions(candidates.slice(0,8));
  }catch(e){
    console.error(e);
  }
}

function renderPlaceSuggestions(items){
  els.placeSuggestions.innerHTML = '';
  if(!items.length){
    els.placeSuggestions.hidden = true;
    return;
  }
  for(const item of items){
    if(!Number.isFinite(item.lat) || !Number.isFinite(item.lng)) continue;
    const b = document.createElement('button');
    b.type='button';
    b.className='place-suggestion';
    b.innerHTML = `<span>${esc(item.label)}</span>${item.sub ? `<small>${esc(item.sub)}</small>` : ''}`;
    b.addEventListener('click', () => {
      els.placeInput.value = item.label;
      els.placeSuggestions.hidden = true;
      searchNearby({lat:item.lat,lng:item.lng}, item.label);
    });
    els.placeSuggestions.appendChild(b);
  }
  els.placeSuggestions.hidden = !els.placeSuggestions.children.length;
}

async function submitPlaceSearch(e){
  e.preventDefault();
  const q = els.placeInput.value.trim();
  if(!q) return;
  setStatus('場所を探しています…');
  try{
    const params = new URLSearchParams({q, limit:'8', fields:'minimal'});
    const res = await fetch(`${SUGGEST_API}?${params}`);
    if(!res.ok) throw new Error('suggest failed');
    const data = await res.json();
    const places = (data.vocabulary || []).filter(v => v.type === 'place' && Array.isArray(v.center));
    let pick = places.find(v => normalize(v.label) === normalize(q)) || places[0];
    if(pick){
      els.placeSuggestions.hidden = true;
      return searchNearby({lat:Number(pick.center[1]),lng:Number(pick.center[0])}, pick.label);
    }
    const s = (data.suggestions || [])[0];
    if(s && Number.isFinite(Number(s.lat)) && Number.isFinite(Number(s.lng))){
      els.placeSuggestions.hidden = true;
      return searchNearby({lat:Number(s.lat),lng:Number(s.lng)}, s.name || q);
    }
    showError('場所を特定できませんでした。地名・駅名・施設名を少し詳しく入力してください。');
    setStatus('場所を特定できませんでした');
  }catch(e){
    console.error(e);
    showError('場所の検索中にエラーが発生しました。');
    setStatus('場所を検索できませんでした');
  }
}

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
      lastCenterLabel = '現在地';
      searchNearby(lastPosition, lastCenterLabel);
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

async function searchNearby(pos, centerLabel='現在地'){
  if(searching){ pendingSearch={pos,centerLabel}; return; }
  lastPosition = pos;
  lastCenterLabel = centerLabel;
  const brand=brandCatalog.find(b=>brandKey(b)===activeBrand);
  const targets = companies.filter(c => visibleCompanyIds.has(c.id) && selected.has(c.id) && (!brand || brand.issuer_id===c.id));
  if(!targets.length){ showError('検索する優待を1つ以上選んでください。'); els.locate.disabled=false; return; }

  searching = true; els.locate.disabled = true;
  categoryCounts=null; renderCategoryFilters();
  els.count.textContent = '';
  els.results.className='results';
  els.results.innerHTML='<div class="empty-state"><p>近くの優待店を探しています…</p></div>';
  setStatus('近隣の優待店を検索中…');

  try{
    const radius = Number(els.radius.value);
    const d1Targets = targets.filter(company =>
      ['official_coordinates','worker_reference'].includes(company.locationMode)
    );
    const openPoiTargets = targets.filter(company => !d1Targets.includes(company));

    const d1Groups = d1Targets.length ? await Promise.all(chunk(d1Targets, 20).map(group => queryD1StoreApi(group, pos, radius))) : [];
    const d1Results=d1Groups.flatMap(g=>g.results);
    const batches = openPoiTargets.flatMap(company => chunk(company.aliases, 14).map(aliases => ({company, aliases})));
    const responses = await Promise.allSettled(batches.map(b => queryOpenPOI(b, pos, radius)));
    const raw = [
      ...d1Results,
      ...responses.filter(r => r.status==='fulfilled').flatMap(r => r.value)
    ];
    const normalized = dedupe(raw).sort((a,b) => a.distance - b.distance);
    categoryCounts=Object.fromEntries(Object.keys(categoryLabels).map(id=>[id,0]));
    for(const group of d1Groups){
      for(const id of Object.keys(categoryLabels)) categoryCounts[id]+=Number(group.categoryCounts[id] || 0);
    }
    for(const s of dedupe(responses.filter(r=>r.status==='fulfilled').flatMap(r=>r.value))){
      categoryCounts.all++; categoryCounts[s.category || 'restaurant']++;
    }
    lastResults = normalized;
    renderCategoryFilters();
    renderFilteredResults(radius);
    setStatus(`${centerLabel}から${radius/1000}km以内を検索しました${centerLabel==='現在地' ? '・現在地は運営者側に保存していません' : ''}`);
  } catch(e){
    console.error(e);
    if(e?.code === 'RATE_LIMIT'){
      showError('短時間に検索が集中しています。10分ほど待ってから再度お試しください。');
      setStatus('検索回数が上限に達しました');
    }else{
      showError('検索中にエラーが発生しました。時間をおいて再度お試しください。');
      setStatus('検索できませんでした');
    }
  } finally {
    searching=false;
    if(pendingSearch){ const next=pendingSearch; pendingSearch=null; searchNearby(next.pos,next.centerLabel); }
    setTimeout(() => { els.locate.disabled=false; }, 1500);
  }
}

function queryOfficialStoreDb(company, origin, radius){
  return (company.officialStores || []).map(s => {
    const lat = Number(s.lat ?? s.latitude);
    const lng = Number(s.lng ?? s.longitude);
    if(!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
    const distance = haversine(origin.lat, origin.lng, lat, lng);
    if(distance > radius) return null;
    return {
      name: s.name,
      address: s.address,
      phone: s.phone || '',
      lat,
      lng,
      company,
      matchedAlias: s.brand_name || company.name,
      category: s.category || 'restaurant',
      officialStore: s,
      officialVerified: true,
      distance
    };
  }).filter(Boolean);
}

async function queryD1StoreApi(targets, pos, radius){
  const companiesById = new Map(targets.map(c => [c.id, c]));
  const params = new URLSearchParams({
    lat: String(pos.lat),
    lng: String(pos.lng),
    radius: String(radius),
    issuers: targets.map(c => c.id).join(','),
    ...(activeCategory !== 'all' ? {category: activeCategory} : {}),
    ...(activeBrand && brandCatalog.some(b=>brandKey(b)===activeBrand) ? {brand:brandCatalog.find(b=>brandKey(b)===activeBrand).name} : {})
  });
  const res = await fetch(`${STORE_API}?${params}`, {cache:'no-store'});
  if(res.status === 429){
    let data = {};
    try { data = await res.json(); } catch {}
    const error = new Error(data.message || '短時間に検索が集中しています。10分ほど待ってから再度お試しください。');
    error.code = 'RATE_LIMIT';
    throw error;
  }
  if(!res.ok) throw new Error(`Store API ${res.status}`);
  const data = await res.json();

  const results=(data.results || []).map(s => {
    const company = companiesById.get(s.issuer_id);
    if(!company) return null;
    const lat = Number(s.lat), lng = Number(s.lng), distance = Number(s.distance);
    if(!Number.isFinite(lat) || !Number.isFinite(lng) || !Number.isFinite(distance)) return null;
    const officialStore = {
      store_id: s.store_id,
      name: s.name,
      address: s.address || '',
      phone: s.phone || '',
      brand_name: s.brand_name || '',
      category: s.category || 'restaurant',
      lat,
      lng,
      official_url: s.official_url || ''
    };
    return {
      name: s.name,
      address: s.address || '',
      phone: s.phone || '',
      lat,
      lng,
      company,
      matchedAlias: s.brand_name || company.name,
      category: s.category || 'restaurant',
      officialStore,
      officialVerified: true,
      distance
    };
  }).filter(Boolean);
  const counts=data.category_counts || results.reduce((out,s)=>{out.all++;out[s.category]=(out[s.category] || 0)+1;return out;},{all:0});
  return {results,categoryCounts:counts};
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
  if(company.domesticOnly){
    const country = normalize(p.country || p.country_code || p.countryCode || '');
    if(country && !['japan','jp','日本'].includes(country)) return null;
  }

  if(company.storeDataPath && company.locationMode !== 'official_coordinates'){
    const country = normalize(p.country || p.country_code || p.countryCode || '');
    if(country && !['japan','jp','日本'].includes(country)) return null;

    const officialStore = matchOfficialStore(p, company.officialStores || []);
    if(!officialStore) return null;

    const alias = officialStore.brand_name || [...(company.aliases || [])]
      .sort((a,b) => normalize(b).length - normalize(a).length)
      .find(x => normalize(officialStore.name).includes(normalize(x))) || company.name;

    const lat = Number(p.lat), lng = Number(p.lng);
    if(!Number.isFinite(lat) || !Number.isFinite(lng)) return null;

    return {
      ...p,
      lat,
      lng,
      company,
      matchedAlias: alias,
      category: officialStore.category || company.categories?.[alias] || 'restaurant',
      officialStore,
      officialVerified: true,
      distance: haversine(origin.lat, origin.lng, lat, lng)
    };
  }

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

function matchOfficialStore(p, stores){
  if(!stores.length) return null;

  const poiName = normalize(p.name || '');
  const poiAddress = normalize(p.address || [p.prefecture,p.city].filter(Boolean).join(''));
  const poiPhone = String(p.phone || p.tel || '').replace(/\D/g,'');

  let best = null;
  let bestScore = 0;

  for(const s of stores){
    const officialName = normalize(s.name || '');
    const officialAddress = normalize(s.address || '');
    const officialPhone = String(s.phone || '').replace(/\D/g,'');

    let score = 0;

    if(poiPhone && officialPhone && poiPhone === officialPhone) score += 100;

    if(poiName && officialName){
      if(poiName === officialName) score += 80;
      else if(poiName.length >= 6 && officialName.includes(poiName)) score += 50;
      else if(officialName.length >= 6 && poiName.includes(officialName)) score += 50;
    }

    if(poiAddress && officialAddress){
      if(poiAddress === officialAddress) score += 40;
      else if(poiAddress.length >= 8 && officialAddress.includes(poiAddress)) score += 25;
      else if(officialAddress.length >= 8 && poiAddress.includes(officialAddress)) score += 25;
    }

    if(score > bestScore){
      best = s;
      bestScore = score;
    }
  }

  return bestScore >= 50 ? best : null;
}
function normalize(s){ return String(s).normalize('NFKC').toLowerCase().replace(/[\s・･\-‐‑–—ー_]/g,''); }
function chunk(arr,n){ const out=[]; for(let i=0;i<arr.length;i+=n) out.push(arr.slice(i,i+n)); return out; }
function dedupe(items){
  const map=new Map();
  for(const x of items){
    const key = x.officialVerified && x.officialStore?.store_id
      ? `official|${x.company.id}|${x.officialStore.store_id}`
      : `${normalize(x.name)}|${x.lat.toFixed(5)}|${x.lng.toFixed(5)}`;
    const existing=map.get(key);
    if(!existing) map.set(key,x);
    else if(existing.company.id !== x.company.id){
      // 同一店舗が複数優待に該当する将来拡張用
      existing.also = [...(existing.also||[]), x.company];
    }else if(x.officialVerified && existing.officialVerified){
      // 公式店舗IDが同じなら、住所情報が豊富な方を残す
      const existingAddress = existing.officialStore?.address || existing.address || '';
      const newAddress = x.officialStore?.address || x.address || '';
      if(newAddress.length > existingAddress.length) map.set(key,x);
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
function safeExternalUrl(value){
  try{
    const u = new URL(String(value || ''), location.href);
    return ['https:','http:'].includes(u.protocol) ? u.href : '#';
  }catch(e){
    return '#';
  }
}

function resetCategoryFilter(){
  activeCategory='all';
  writeSetting('yutai-category','all');
  renderCategoryFilters();
}

function renderCategoryFilters(){
  if(!els.categoryFilters) return;
  els.categoryFilters.innerHTML='';
  for(const [id,label] of Object.entries(categoryLabels)){
    const b=document.createElement('button');
    b.type='button';
    b.className='category-filter';
    b.textContent=label;
    if(categoryCounts){
      const badge=document.createElement('span'); badge.className='category-count'; badge.textContent=`${categoryCounts[id] || 0}件`; b.prepend(badge);
      b.setAttribute('aria-label',`${label} ${categoryCounts[id] || 0}件`);
      b.dataset.empty=categoryCounts[id] ? 'false' : 'true';
    }
    b.setAttribute('aria-pressed', activeCategory===id ? 'true' : 'false');
    b.addEventListener('click',()=>{
      activeCategory=id;
      writeSetting('yutai-category',id);
      renderCategoryFilters();
      if(lastPosition) searchNearby(lastPosition, lastCenterLabel);
      else if(lastResults.length) renderFilteredResults(Number(els.radius.value));
    });
    els.categoryFilters.appendChild(b);
  }
}

function renderFilteredResults(radius){
  const brand=brandCatalog.find(b=>brandKey(b)===activeBrand);
  const items = lastResults.filter(x=>(activeCategory==='all' || x.category===activeCategory) && (!brand || (x.company.id===brand.issuer_id && x.matchedAlias===brand.name)));
  renderResults(items, radius);
}

function renderResults(items, radius){
  const total=Number(categoryCounts?.[activeCategory] || 0);
  els.count.textContent = total>items.length ? `${items.length}件表示／対象${total}件` : `${items.length}件`;
  if(!items.length){
    els.results.className='results empty-state';
    const restricted=activeCategory!=='all' || activeBrand;
    els.results.innerHTML=`<p>${radius/1000}km以内では<br>${activeCategory!=='all' ? `「${esc(categoryLabels[activeCategory])}」の条件に一致する店舗がありません` : '対象店舗を見つけられませんでした'}</p>${restricted ? '<button type="button" class="category-filter" id="clearResultFilters">絞り込みを解除して探す</button>' : ''}`;
    qs('#clearResultFilters')?.addEventListener('click',()=>{
      activeBrand=''; writeSetting('yutai-brand',''); els.brandSearch.value=''; renderBrandOptions(); resetCategoryFilter();
      if(lastPosition) searchNearby(lastPosition,lastCenterLabel);
    });
    return;
  }
  els.results.className='results'; els.results.innerHTML='';
  for(const x of items){
    const card=document.createElement('article'); card.className=`card ${issuerTone(x.company.id)}`;
    const storeName = x.officialStore?.name || x.name || x.matchedAlias;
    const storeAddress = x.officialStore?.address || x.address || [x.prefecture,x.city].filter(Boolean).join('');
    const mapQuery = [storeName, storeAddress].filter(Boolean).join(' ');
    const mapUrl=`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(mapQuery)}`;
    const officialUrl = safeExternalUrl(x.company.sourceUrl);
    card.innerHTML=`
      <div class="card-top">
        <div class="distance">${distanceText(x.distance)}<small>${esc(lastCenterLabel)}から</small></div>
        <div class="store">
          <h3 class="store-name"><a class="store-link" href="${mapUrl}" target="_blank" rel="noopener">${esc(storeName)}</a></h3>
          <p class="store-address">${esc(storeAddress)}</p>
        </div>
      </div>
      <div class="badges">
        <span class="badge company">${esc(x.company.name)}優待</span>
        <span class="badge">${esc(x.matchedAlias)}</span>
        <span class="badge category">${esc(categoryLabels[x.category] || 'その他')}</span>
        <span class="badge beta">${x.officialVerified ? '公式DB確認' : 'β 要公式確認'}</span>
      </div>
      <div class="card-actions">
        <a class="issuer-map-button" href="${mapUrl}" target="_blank" rel="noopener">Googleマップで見る</a>
        <a href="${esc(officialUrl)}" target="_blank" rel="noopener">優待公式</a>
        <button class="favorite-toggle" type="button" aria-pressed="false">☆ 保存</button>
        <button class="feedback-link" type="button">情報修正</button>
      </div>`;
    const favorite=card.querySelector('.favorite-toggle');
    favorite.dataset.favoriteKey=storeKey(x);
    favorite.addEventListener('click',()=>toggleFavorite(x));
    card.querySelector('.feedback-link').addEventListener('click', () => openFeedback({
      company: x.company.name,
      store: x.name || x.matchedAlias
    }));
    els.results.appendChild(card);
  }
  updateFavoriteButtons();
}

async function openHistory(){
  historyPage = 1;
  els.history.showModal();
  if(!historyLoaded){
    await loadHistory();
  }else{
    renderHistory();
  }
}

async function loadHistory(){
  els.historyStatus.textContent = '更新履歴を読み込んでいます…';
  els.historyList.innerHTML = '';
  try{
    const data = await fetch('./data/updates.json', {cache:'no-store'}).then(r => {
      if(!r.ok) throw new Error('history fetch failed');
      return r.json();
    });
    historyEvents = Array.isArray(data.events) ? data.events : [];
    historyLoaded = true;
    renderHistoryCompanyOptions();
    renderHistory();
  }catch(e){
    console.error(e);
    els.historyStatus.textContent = '更新履歴を読み込めませんでした';
    els.historyList.innerHTML = '<div class="history-empty">時間をおいて再度お試しください</div>';
    els.historyPrev.disabled = true;
    els.historyNext.disabled = true;
    els.historyPageLabel.textContent = '—';
  }
}

function renderHistoryCompanyOptions(){
  const current = els.historyCompanyFilter.value || 'all';
  els.historyCompanyFilter.innerHTML = '<option value="all">すべて</option>';
  for(const c of companies.filter(c => visibleCompanyIds.has(c.id))){
    const o = document.createElement('option');
    o.value = c.id;
    o.textContent = c.name;
    els.historyCompanyFilter.appendChild(o);
  }
  els.historyCompanyFilter.value = [...els.historyCompanyFilter.options].some(o => o.value===current) ? current : 'all';
}

function filteredHistoryEvents(){
  const company = els.historyCompanyFilter.value;
  const type = els.historyTypeFilter.value;
  return historyEvents.filter(e => {
    if(!visibleCompanyIds.has(e.issuer_id)) return false;
    if(company !== 'all' && e.issuer_id !== company) return false;
    if(type !== 'all' && e.kind !== type) return false;
    return true;
  });
}

function renderHistory(){
  const items = filteredHistoryEvents();
  const totalPages = Math.max(1, Math.ceil(items.length / HISTORY_PAGE_SIZE));
  if(historyPage > totalPages) historyPage = totalPages;
  const start = (historyPage - 1) * HISTORY_PAGE_SIZE;
  const pageItems = items.slice(start, start + HISTORY_PAGE_SIZE);

  els.historyStatus.textContent = items.length ? `${items.length}件の更新履歴` : '該当する更新履歴はまだありません';
  els.historyList.innerHTML = '';

  if(!pageItems.length){
    els.historyList.innerHTML = '<div class="history-empty">今後の公式DB更新から履歴を蓄積します</div>';
  }else{
    for(const e of pageItems){
      const item = document.createElement('article');
      item.className = 'history-item';
      const kindLabel =
        e.kind === 'added' ? '新店・追加' :
        e.kind === 'removed' ? '閉店・対象外' :
        '対象・情報変更';
      const changed = Array.isArray(e.changed_fields) ? e.changed_fields.map(x => x.label).filter(Boolean) : [];
      const detail =
        e.kind === 'added' ? '公式店舗DBに新規掲載' :
        e.kind === 'removed' ? '公式店舗DBから掲載終了' :
        (changed.length ? `${changed.join(' / ')}を変更` : '店舗情報を変更');
      const brand = e.brand_name ? `<span class="history-brand">${esc(e.brand_name)}</span>` : '';
      item.innerHTML = `
        <div class="history-item-head">
          <time>${esc(formatHistoryDate(e.run_date || e.at))}</time>
          <span class="history-kind ${esc(e.kind)}">${kindLabel}</span>
        </div>
        <div class="history-store">${esc(e.name || '店舗名不明')}</div>
        <div class="history-address">${esc(e.address || '')}</div>
        <div class="history-meta">
          <span>${esc(companies.find(c => c.id === e.issuer_id)?.name || e.issuer_name || e.issuer_id)}${e.issuer_code ? `（${esc(e.issuer_code)}）` : ''}</span>
          ${brand}
        </div>
        <div class="history-detail">${esc(detail)}</div>`;
      els.historyList.appendChild(item);
    }
  }

  els.historyPageLabel.textContent = items.length ? `${historyPage} / ${totalPages}` : '—';
  els.historyPrev.disabled = historyPage <= 1 || !items.length;
  els.historyNext.disabled = historyPage >= totalPages || !items.length;
}

function formatHistoryDate(value){
  const s = String(value || '');
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${Number(m[1])}/${Number(m[2])}/${Number(m[3])}` : s;
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

function showError(msg){ els.results.className='results'; els.results.innerHTML=`<div class="error-box">${esc(msg)}</div>`; els.count.textContent=''; }
function setStatus(msg){ els.status.textContent=msg; }
function esc(s){ return String(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])); }


// Only a small brand catalog is returned; the private store DB stays on D1.
function brandKey(b){ return JSON.stringify([b.issuer_id,b.name]); }
async function loadBrandCatalog(){
  const request=++brandRequest;
  try {
    const groups=await Promise.all(chunk(companies,20).map(async group=>{
      const params=new URLSearchParams({issuers:group.map(c=>c.id).join(',')});
      const res=await fetch(`${STORE_API.replace('/stores/search','/brands')}?${params}`);
      if(!res.ok) throw new Error('brand catalog unavailable');
      return (await res.json()).brands || [];
    }));
    if(request!==brandRequest) return;
    brandCatalog=groups.flat().filter(b=>visibleCompanyIds.has(b.issuer_id) && typeof b.name==='string' && b.name);
    renderBrandOptions();
  } catch {
    els.brandSelect.disabled=true;
    els.brandSearch.disabled=true;
    els.brandSelect.innerHTML='<option value="">ブランド一覧を取得できませんでした</option>';
    activeBrand='';
  }
}
function renderBrandOptions(){
  const available=brandCatalog.filter(b=>selected.has(b.issuer_id));
  if(activeBrand && !available.some(b=>brandKey(b)===activeBrand)){
    activeBrand=''; writeSetting('yutai-brand','');
  }
  const query=normalize(els.brandSearch.value);
  els.brandSelect.innerHTML='<option value="">選択した優待の全ブランド</option>';
  for(const c of companies.filter(c=>selected.has(c.id))){
    const matches=available.filter(b=>b.issuer_id===c.id && (!query || normalize(b.name+' '+c.name).includes(query) || brandKey(b)===activeBrand));
    if(!matches.length) continue;
    const group=document.createElement('optgroup'); group.label=c.name;
    for(const b of matches.sort((a,b)=>a.name.localeCompare(b.name,'ja'))){
      const option=document.createElement('option'); option.value=brandKey(b); option.textContent=b.name; group.appendChild(option);
    }
    els.brandSelect.appendChild(group);
  }
  els.brandSelect.value=activeBrand;
  els.brandSelect.disabled=!available.length; els.brandSearch.disabled=!available.length;
}
function storeKey(x){ return JSON.stringify([x.company.id,x.officialStore?.store_id || [x.name,x.address].join('|')]); }
function toggleFavorite(x){
  const key=storeKey(x), exists=favorites.some(f=>f.key===key);
  if(!exists && favorites.length>=500){ setStatus('お気に入りは500件まで保存できます。不要な店舗を解除してください。'); return; }
  // Never persist origin, store coordinates, distance, or an entire search response.
  const next=exists ? favorites.filter(f=>f.key!==key) : [...favorites,{
    key,issuer:x.company.id,name:x.officialStore?.name || x.name,address:x.officialStore?.address || x.address || '',brand:x.matchedAlias || ''
  }];
  if(!writeSetting('yutai-favorites',JSON.stringify(next))) return;
  favorites=next; updateFavoritesCount(); updateFavoriteButtons();
}
function updateFavoritesCount(){ els.favoritesCount.textContent=String(favorites.length); }
function updateFavoriteButtons(){
  for(const button of document.querySelectorAll('.favorite-toggle')){
    const saved=favorites.some(f=>f.key===button.dataset.favoriteKey);
    button.setAttribute('aria-pressed',String(saved)); button.textContent=saved ? '★ 保存済み' : '☆ 保存';
  }
}
function renderFavorites(){
  els.favoritesList.innerHTML='';
  if(!favorites.length){ els.favoritesList.innerHTML='<p class="personal-empty">検索結果の「☆ 保存」で、行きたい店を残せます。</p>'; return; }
  for(const f of [...favorites].reverse()){
    const c=companies.find(c=>c.id===f.issuer);
    const map='https://www.google.com/maps/search/?api=1&query='+encodeURIComponent([f.name,f.address].filter(Boolean).join(' '));
    const card=document.createElement('article'); card.className=`personal-card ${issuerTone(f.issuer)}`;
    card.innerHTML=`<h3>${esc(f.name)}</h3><p>${esc(f.address)}</p><p class="personal-meta">${esc(c?.name || f.issuer)} · ${esc(f.brand || '')}</p><div class="card-actions"><a class="issuer-map-button" href="${map}" target="_blank" rel="noopener">Googleマップで見る</a>${c ? `<a href="${esc(safeExternalUrl(c.sourceUrl))}" target="_blank" rel="noopener">優待公式</a>` : ''}<button type="button" class="remove-favorite">保存を解除</button></div>`;
    card.querySelector('button').addEventListener('click',()=>{
      const next=favorites.filter(v=>v.key!==f.key);
      if(!writeSetting('yutai-favorites',JSON.stringify(next))) return;
      favorites=next; renderFavorites(); updateFavoritesCount(); updateFavoriteButtons();
    });
    els.favoritesList.appendChild(card);
  }
}
function renderMemoCompanies(){
  els.memoCompany.innerHTML='';
  for(const c of companies){ const option=document.createElement('option'); option.value=c.id; option.textContent=c.name; els.memoCompany.appendChild(option); }
}
function resetMemoForm(){ els.memoForm.reset(); els.memoId.value=''; qs('#memoSave').textContent='メモを保存'; qs('#memoCancel').hidden=true; }
function saveMemo(event){
  event.preventDefault();
  const issuer=els.memoCompany.value,date=els.memoDate.value,amount=els.memoAmount.value;
  if(!visibleCompanyIds.has(issuer) || !/^\d{4}-\d{2}-\d{2}$/.test(date)) return;
  if(amount && (!Number.isFinite(Number(amount)) || Number(amount)<0 || Number(amount)>100000000)) return;
  if(!els.memoId.value && memos.length>=200){ setStatus('期限メモは200件まで保存できます。'); return; }
  const entry={id:els.memoId.value || (globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`),issuer,date,amount:amount==='' ? null : Number(amount),note:els.memoNote.value.trim().slice(0,120)};
  const next=[...memos.filter(m=>m.id!==entry.id),entry];
  if(!writeSetting('yutai-memos',JSON.stringify(next))) return;
  memos=next; resetMemoForm(); renderMemos();
}
function daysUntil(date){
  const today=new Date();
  const [y,m,d]=date.split('-').map(Number);
  return Math.round((Date.UTC(y,m-1,d)-Date.UTC(today.getFullYear(),today.getMonth(),today.getDate()))/86400000);
}
function renderMemos(){
  els.memoList.innerHTML='';
  const ordered=[...memos].sort((a,b)=>a.date.localeCompare(b.date));
  const upcoming=ordered.filter(m=>daysUntil(m.date)>=0 && (m.amount===null || m.amount>0));
  els.memoSummary.textContent=upcoming.length ? `次の期限 ${upcoming[0].date.replaceAll('-','/')} · ${upcoming.length}件` : '期限・残高を手入力で記録';
  if(!ordered.length){ els.memoList.innerHTML='<p class="personal-empty">手持ちの優待の期限を、手入力で記録できます。</p>'; return; }
  for(const m of ordered){
    const c=companies.find(c=>c.id===m.issuer),days=daysUntil(m.date);
    const state=days<0 ? '期限経過' : days===0 ? '今日まで' : `あと${days}日`;
    const card=document.createElement('article'); card.className=`personal-card ${issuerTone(m.issuer)}`;
    card.innerHTML=`<div class="memo-deadline${days>=0 && days<=30 ? ' soon' : ''}">${esc(m.date.replaceAll('-','/'))} · ${state}</div><h3>${esc(c?.name || m.issuer)}</h3>${m.amount!==null ? `<p>残高メモ ${Number(m.amount).toLocaleString('ja-JP')}円</p>` : ''}${m.note ? `<p>${esc(m.note)}</p>` : ''}<div class="card-actions"><button class="memo-search" type="button" ${c ? '' : 'disabled'}>この優待で探す</button><button class="memo-edit" type="button">編集</button><button class="memo-delete" type="button">削除</button></div>`;
    card.querySelector('.memo-edit').addEventListener('click',()=>{
      els.memoId.value=m.id; els.memoCompany.value=m.issuer; els.memoDate.value=m.date; els.memoAmount.value=m.amount ?? ''; els.memoNote.value=m.note || '';
      qs('#memoSave').textContent='変更を保存'; qs('#memoCancel').hidden=false; els.memoForm.scrollIntoView({block:'start'}); els.memoDate.focus();
    });
    card.querySelector('.memo-delete').addEventListener('click',()=>{
      const next=memos.filter(v=>v.id!==m.id); if(!writeSetting('yutai-memos',JSON.stringify(next))) return;
      memos=next; if(els.memoId.value===m.id) resetMemoForm(); renderMemos();
    });
    card.querySelector('.memo-search').addEventListener('click',()=>{
      selected.clear(); selected.add(m.issuer); activeBrand=''; els.brandSearch.value=''; activeCategory='all';
      writeSetting('yutai-brand',''); writeSetting('yutai-category','all'); persistSelection(); renderChips(); renderBrandOptions(); renderCategoryFilters();
      els.memo.close(); qs('.hero').scrollIntoView({behavior:'smooth',block:'start'});
      if(lastPosition) searchNearby(lastPosition,lastCenterLabel); else setStatus('検索する場所を指定するか、現在地から探してください');
    });
    els.memoList.appendChild(card);
  }
}
