import {numberHTML} from './number-motion.js?v=20261013-reel';
import {createBrandMark} from './representative-marks.js?v=20261014-restaurants';
// Feature search uses independent radii and either manual or scheduled data.
import {track} from './analytics.js?v=20261011';
import {compareBenefitPriority, countdownDays} from './expiry.js?v=20261017-inclusive-countdown';
export const FEATURE_RADIUS_METERS = 3_000_000;
const MAX_FEATURE_RADIUS_METERS = 4_000_000;
const validRadius = radius => radius === 'all' || (Number.isFinite(radius) && radius > 0 && radius <= MAX_FEATURE_RADIUS_METERS);
export function featureRadius(feature) { return feature.radiusMeters ?? FEATURE_RADIUS_METERS; }
export function featureRadiusOptions(feature) { return feature.radiusOptionsMeters ?? [featureRadius(feature)]; }

function validDate(value) {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) &&
    Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;
}
function safeUrl(value) {
  try { const url = new URL(value); return url.protocol === 'https:' ? url.href : ''; }
  catch { return ''; }
}
export function validateFeature(feature) {
  if (!feature || !/^[a-z0-9-]+$/.test(feature.id) || !feature.title ||
      !feature.issuer?.id || !/^\d{4}$/.test(feature.issuer.code) || !feature.issuer.name ||
      !['manual', 'scheduled'].includes(feature.updateMode) || !['draft', 'public', 'ended'].includes(feature.status) ||
      !Array.isArray(feature.stores)) throw new Error('Invalid feature');
  if (!validRadius(featureRadius(feature)))
    throw new Error('Invalid feature radius');
  if (feature.deadlineExpiryType && !['利用期限', '申込期限'].includes(feature.deadlineExpiryType))
    throw new Error('Invalid feature deadline type');
  const radii = featureRadiusOptions(feature);
  if (!Array.isArray(radii) || !radii.includes(featureRadius(feature)) ||
      new Set(radii).size !== radii.length || radii.some(radius => !validRadius(radius)))
    throw new Error('Invalid feature radius options');
  const ids = new Set();
  for (const store of feature.stores) {
    if (!store.id || ids.has(store.id) || !store.name || !store.address || !store.conditions)
      throw new Error('Invalid or duplicate feature store');
    ids.add(store.id);
    const hasLat = store.lat != null, hasLng = store.lng != null;
    if (hasLat !== hasLng || (hasLat && (!Number.isFinite(store.lat) || !Number.isFinite(store.lng) ||
        Math.abs(store.lat) > 90 || Math.abs(store.lng) > 180))) throw new Error('Invalid coordinates');
  }
  if (feature.status === 'ended' && (feature.updateMode !== 'manual' ||
      !validDate(feature.validThrough) || !validDate(feature.checkedOn) || !safeUrl(feature.sourceUrl)))
    throw new Error('Unverified ended feature');
  if (feature.status === 'public' && (!(feature.indexed === true ? Number.isSafeInteger(feature.storeCount) && feature.storeCount > 0 && feature.stores.length === 0 : feature.stores.length) || !safeUrl(feature.sourceUrl) ||
      !validDate(feature.checkedOn) || (feature.availability !== 'continuous' &&
      (!validDate(feature.validFrom) || !validDate(feature.validThrough) ||
      feature.validFrom > feature.validThrough || feature.checkedOn > feature.validThrough)) ||
      feature.stores.some(store => store.verified !== true || store.lat == null))) throw new Error('Unverified public feature');
  return feature;
}
export function visibleFeatures(features, today, preview = false) {
  return features.map(validateFeature).filter(feature =>
    (feature.status === 'public' && (feature.availability === 'continuous' || (feature.validFrom <= today && today <= feature.validThrough))) ||
    (feature.status === 'ended' && feature.validThrough < today) ||
    (preview && feature.status === 'draft'))
    .sort((a, b) => Number(Boolean(a.displayLast)) - Number(Boolean(b.displayLast)));
}
function distance(origin, store) {
  if (!origin || !Number.isFinite(origin.lat) || !Number.isFinite(origin.lng) ||
      store.lat == null || store.lng == null) return null;
  const rad = value => value * Math.PI / 180;
  const dLat = rad(store.lat - origin.lat), dLng = rad(store.lng - origin.lng);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(rad(origin.lat)) * Math.cos(rad(store.lat)) * Math.sin(dLng / 2) ** 2;
  return 6_371_000 * 2 * Math.asin(Math.sqrt(Math.min(1, a)));
}
export function featureStores(feature, origin) {
  return feature.stores.map(store => ({...store, distance: distance(origin, store)}))
    .filter(store => featureRadius(feature) === 'all' || !origin || (store.distance != null && store.distance <= featureRadius(feature)))
    .sort((a, b) => (a.distance ?? Infinity) - (b.distance ?? Infinity));
}
export function featureDistanceLabel(meters) {
  return meters < 1000 ? `${Math.round(meters)}m` : `${(meters / 1000).toLocaleString('ja-JP', {maximumFractionDigits:1})}km`;
}
const featureCount = feature => feature.indexed ? feature.storeCount : feature.stores.length;
const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));

// Merge voucher-specific results into one list ordered from the same search origin.
export function featureSearchResults(features, origin, getRadius = featureRadius) {
  return features.flatMap(feature => featureStores({...feature, radiusMeters:getRadius(feature)}, origin)
    .map(store => ({feature, store})))
    .sort((a,b) => (a.store.distance ?? Infinity) - (b.store.distance ?? Infinity));
}

export async function initSpecialFeatures({root, getOrigin, getCenterLabel, createDeadlineBubble, getDeadline, getRadius, preview = false, section = 'dining', catalog = null, initialFeature = ''}) {
  if (!root) return {refresh() {}, search() {}, invalidate() {}};
  let features = [], hasSearched = false, originUnavailable = false;
  let remotePage=null,remoteLoading=false,requestVersion=0,remoteController=null;
  const invalidateResults=()=>{hasSearched=false;remotePage=null;remoteLoading=false;requestVersion++;remoteController?.abort();};
  const selectedRadii = new Map();
  const selectedFeatures = new Set();
  const unit = section === 'hotel' ? '施設' : '店舗';
  const resultsId = `${root.id || 'specialFeature'}Results`;
  const heading = section === 'hotel' ? '宿泊・ホテル優待 特集' : 'レア優待店 特集';
  const currentRadius = feature => getRadius ? getRadius() : selectedRadii.get(feature.id) ?? featureRadius(feature);
  const today = () => new Intl.DateTimeFormat('sv-SE', {timeZone:'Asia/Tokyo'}).format(new Date());
  const render = () => {
    const existingItems = new Map([...root.querySelectorAll('.feature-buttons > .feature-item')]
      .map(item=>[item.querySelector('[data-feature]')?.dataset.feature,item]));
    // Static HTML determines the initial visual order. Never reshuffle mounted
    // hotel logos when the remote feature snapshots supply their store counts.
    // Future features not present in HTML still follow the original priority.
    const stableOrder = new Map([...root.querySelectorAll('[data-feature]')]
      .map((button,index) => [button.dataset.feature,index]));
    const displayed = visibleFeatures(features, today(), preview)
      .map(feature => ({feature,position:stableOrder.get(feature.id),priority:{
        days:getDeadline(feature.issuer.id, feature.deadlineBenefitPattern, feature.deadlineExpiryType)?.days,
        ended:feature.status === 'ended', count:featureCount(feature)
      }}))
      .sort((a,b) => {
        if (a.position != null && b.position != null) return a.position-b.position;
        if (a.position != null) return -1;
        if (b.position != null) return 1;
        return section === 'hotel'
          ? featureCount(b.feature)-featureCount(a.feature)
          : compareBenefitPriority(a.priority,b.priority);
      })
      .map(item => item.feature);
    const available = new Set(displayed.map(feature => feature.id));
    for (const id of selectedFeatures) if (!available.has(id)) selectedFeatures.delete(id);
    root.hidden = !displayed.length;
    if (!displayed.length) { root.replaceChildren(); return; }
    const integrated = root.hasAttribute('data-tab-panel');
    if (!root.querySelector('.feature-buttons')) {
      root.innerHTML = `${integrated ? `<div class="benefit-selection-meta"><span class="selection-summary" aria-live="polite">${numberHTML(section+':selected',selectedFeatures.size)}件 選択中</span><span class="selection-hint">複数選択できます</span></div>` : `<h2 class="selection-heading">${heading}</h2>`}<div class="feature-buttons"></div><div class="feature-results" aria-live="polite"></div>`;
    } else {
      const summary = root.querySelector('.selection-summary');
      if (summary) summary.innerHTML = numberHTML(section+':selected',selectedFeatures.size)+'件 選択中';
    }
    const buttons = root.querySelector('.feature-buttons');
    for (const [index,feature] of displayed.entries()) {
      const existing = existingItems.get(feature.id);
      if (existing) {
        const button = existing.querySelector('[data-feature]');
        button.setAttribute('aria-pressed',String(selectedFeatures.has(feature.id)));
        if (!button.dataset.logoCardHydrated) {
          button.addEventListener('click', () => {
            selectedFeatures.has(feature.id) ? selectedFeatures.delete(feature.id) : selectedFeatures.add(feature.id);
            track('benefit_select', {section, benefit_id: feature.id, selected: selectedFeatures.has(feature.id)});
            invalidateResults(); render();
            root.querySelector(`[data-feature="${feature.id}"]`)?.focus();
          });
          button.dataset.logoCardHydrated = 'true';
        }
        // The initial HTML intentionally omits a fabricated count; add verified
        // totals and deadline data when the feature snapshot actually arrives.
        const count = button.querySelector('.benefit-choice-count');
        if (count) count.innerHTML = numberHTML('feature:'+feature.id,featureCount(feature))+'<span class="number-unit">件</span>';
        const name = button.querySelector('.benefit-choice-name');
        if (name) name.textContent = feature.shortName || feature.issuer.name;
        const detail = button.querySelector('.benefit-choice-detail');
        if (detail) {
          const caption = detail.querySelector('.feature-caption');
          if (caption) caption.textContent = feature.subtitle || '';
          detail.querySelector('.feature-deadline')?.remove();
          const bubble = feature.status === 'ended' ? document.createElement('span') : createDeadlineBubble(feature.issuer.id,feature.deadlineBenefitPattern,feature.deadlineExpiryType);
          if (feature.status === 'ended') {
            bubble.className = 'voucher-deadline-bubble';
            bubble.textContent = '今回分は終了';
            bubble.setAttribute('aria-label', `利用期限終了：${feature.validThrough}`);
          }
          if (bubble) { bubble.classList.add('feature-deadline'); detail.append(bubble); }
        }
        if (buttons.children[index] !== existing) buttons.insertBefore(existing,buttons.children[index] || null);
        existingItems.delete(feature.id);
        continue;
      }
      const item = document.createElement('div'); item.className = 'feature-item';
      const button = document.createElement('button'); button.type = 'button';
      button.className = 'feature-button benefit-choice';
      const nameRow = document.createElement('span'); nameRow.className = 'benefit-choice-heading';
      const name = document.createElement('span'); name.className = 'benefit-choice-name';
      name.textContent = feature.shortName || feature.issuer.name;
      const count = document.createElement('span'); count.className = 'benefit-choice-count';
      count.innerHTML = numberHTML('feature:'+feature.id,featureCount(feature))+'<span class="number-unit">件</span>';
      const check=document.createElement('span'); check.className='issuer-check'; check.setAttribute('aria-hidden','true');
      const copy = document.createElement('span'); copy.className = 'benefit-choice-copy';
      nameRow.append(name,count); copy.append(nameRow);
      button.append(check,copy);
      if (section === 'hotel') {
        const mark=createBrandMark('hotel',feature.id);
        if (mark) button.append(mark);
      }
      count.setAttribute('data-ui-number','');
      button.title=feature.title;
      button.setAttribute('aria-controls', resultsId);
      const bubble = feature.status === 'ended' ? document.createElement('span') : createDeadlineBubble(feature.issuer.id, feature.deadlineBenefitPattern, feature.deadlineExpiryType);
      if (feature.status === 'ended') {
        bubble.className = 'voucher-deadline-bubble'; bubble.textContent = '今回分は終了';
        bubble.setAttribute('aria-label', `利用期限終了：${feature.validThrough}`);
      }
      if (bubble) bubble.classList.add('feature-deadline');
      button.setAttribute('aria-pressed', String(selectedFeatures.has(feature.id)));
      button.dataset.feature = feature.id;
      button.addEventListener('click', () => {
        selectedFeatures.has(feature.id) ? selectedFeatures.delete(feature.id) : selectedFeatures.add(feature.id);
        track('benefit_select', {section, benefit_id: feature.id, selected: selectedFeatures.has(feature.id)});
        invalidateResults(); render();
        root.querySelector(`[data-feature="${feature.id}"]`)?.focus();
      });
      button.dataset.logoCardHydrated = 'true';
      const detail = document.createElement('span'); detail.className = 'benefit-choice-detail';
      if (feature.subtitle) {
        const subtitle = document.createElement('span'); subtitle.className = 'feature-caption';
        subtitle.textContent = feature.subtitle;
        detail.append(subtitle);
      }
      if (bubble) detail.append(bubble);
      // The pressed state, checkmark and logo strength show hotel selection.
      if (detail.childElementCount) copy.append(detail);
      item.append(button);
      if (!getRadius) {
        const radiusLabel = document.createElement('label'); radiusLabel.className = 'feature-radius-label';
        radiusLabel.textContent = '検索範囲';
        const select = document.createElement('select'); select.className = 'feature-radius';
        select.dataset.featureRadius = feature.id;
        select.setAttribute('aria-label', `${feature.shortName || feature.issuer.name}の検索範囲`);
        for (const radius of featureRadiusOptions(feature)) {
          const option = document.createElement('option'); option.value = String(radius);
          option.textContent = radius === 'all' ? `全国・全${unit}` : `${(radius/1000).toLocaleString('ja-JP')} km`;
          select.append(option);
        }
        select.value = String(currentRadius(feature));
        select.addEventListener('change', () => {
          selectedRadii.set(feature.id, select.value === 'all' ? 'all' : Number(select.value));
          invalidateResults();
          if (selectedFeatures.has(feature.id)) {
            render(); root.querySelector(`[data-feature-radius="${feature.id}"]`)?.focus();
          }
        });
        radiusLabel.append(select); item.append(radiusLabel);
      }
      buttons.insertBefore(item,buttons.children[index] || null);
    }
    for (const oldItem of existingItems.values()) oldItem.remove();
    root.querySelector('.feature-results').id = resultsId;
    const chosen = displayed.filter(feature => selectedFeatures.has(feature.id));
    if (!chosen.length) {root.querySelector('.feature-results').replaceChildren();return;}
    if (!hasSearched) {
      root.querySelector('.feature-results').innerHTML = '<p class="feature-note">条件を選んで「現在地から探す」または「この場所で探す」を押してください</p>';
      return;
    }
    const nationwide = chosen.every(feature => currentRadius(feature) === 'all');
    const origin = originUnavailable ? null : getOrigin();
    const matches = section === 'hotel' ? (remotePage?.results || []).map(store=>({feature:features.find(f=>f.id===store.feature_id),store})).filter(x=>x.feature) : featureSearchResults(chosen, origin, currentRadius);
    const output = root.querySelector('.feature-results');
    if (!nationwide && (originUnavailable || !origin)) {
      output.innerHTML = '<p class="feature-note">距離を表示するには、現在地の利用を許可するか、場所を指定してください。</p>';
      return;
    }
    if(section==='hotel'&&remoteLoading&&!remotePage){output.innerHTML='<p class="feature-note">対象施設を検索中…</p>';return;}
    if(section==='hotel'&&!remotePage){output.innerHTML='<p class="feature-note">検索を完了できませんでした。条件を確認して再検索してください。</p>';return;}
    const label = getCenterLabel();
    const details = document.createElement('div');
    const total = chosen.reduce((sum, feature) => sum + featureCount(feature), 0);
    output.innerHTML = `<p class="feature-note">${origin ? `${nationwide ? `全国の対象${unit}` : `${esc(label)}から${(currentRadius(chosen[0])/1000).toLocaleString('ja-JP')}km以内`}・直線距離が近い順` : `全国の対象${unit}・掲載順（検索地点を指定すると距離を表示して近い順）`}／${numberHTML(section+':results',matches.length)}件表示・全${numberHTML(section+':total',section==='hotel' ? remotePage?.total || 0 : total)}${unit}</p>`;
    if (origin && !matches.length && total) output.innerHTML += `<p class="feature-note">この範囲に対象${unit}はありません。検索範囲を広げるか、別の場所を指定してください。</p>`;
    for (const active of chosen) {
      const info = document.createElement('div');
      if (section === 'hotel') info.innerHTML = `<p class="feature-note">${esc(active.description)}</p>`;
      if (active.status === 'public') info.innerHTML += `<p class="feature-note">${active.availability === 'continuous' ? '' : `特典提供期間：${esc(active.validFrom)}〜${esc(active.validThrough)}／`}確認日：${esc(active.checkedOn)}</p>`;
      if (active.voucherName) info.innerHTML += `<p class="feature-note">${esc(active.voucherName)}</p>`;
      const deadline = getDeadline(active.issuer.id, active.deadlineBenefitPattern, active.deadlineExpiryType);
      const deadlineType = active.deadlineExpiryType || '利用期限';
      if (active.status !== 'ended') info.innerHTML += `<p class="feature-note">${esc(active.issuer.name)}（${esc(active.issuer.code)}）<br>${deadline ? `優待券の${esc(deadlineType)}：${esc(deadline.date)}（${'あと' + countdownDays(deadline.days) + '日'}）／${esc(deadline.issue)}。お手持ちの券面をご確認ください。` : `優待券の${esc(deadlineType)}は、お手持ちの券面をご確認ください。`}</p>`;
      details.append(info);
    }
    for (const {feature: active, store} of matches) {
      const card = document.createElement('article'); card.className = 'card feature-card';
      const mapUrl = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(store.name + ' ' + store.address)}`;
      const sourceUrl = safeUrl(store.sourceUrl || active.sourceUrl);
      const routeUrl=store.lat!=null && store.lng!=null ? `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(store.lat+','+store.lng)}` : '';
      card.innerHTML = `<div class="hotel-issuer-label">${esc(active.shortName || active.issuer.name)}${active.voucherName ? '／'+esc(active.voucherName) : ''}</div><div class="card-top"><div class="store"><h3 class="store-name"><a class="store-link" href="${mapUrl}" target="_blank" rel="noopener noreferrer">${esc(store.name)}</a></h3><p class="store-address">${esc(store.address)}</p></div><div class="distance" data-ui-number>${store.distance == null ? '<span class="hotel-distance-unknown">距離未確認</span>' : `${featureDistanceLabel(store.distance)}<small>${esc(label)}から</small>`}</div></div><div class="hotel-benefit-conditions"><span class="hotel-condition-label">利用条件</span><p class="feature-conditions">${esc(store.conditions)}</p></div>${store.coordinateNote ? `<p class="feature-note">${esc(store.coordinateNote)}</p>` : ''}${store.menu ? `<p class="feature-note">${esc(store.menu)}</p>` : ''}<div class="card-actions">${routeUrl ? `<a class="issuer-map-button" href="${routeUrl}" target="_blank" rel="noopener noreferrer">経路を見る</a>` : `<a class="issuer-map-button" href="${mapUrl}" target="_blank" rel="noopener noreferrer">地図で確認</a>`}${sourceUrl ? `<a href="${esc(sourceUrl)}" target="_blank" rel="noopener noreferrer">公式情報を確認</a>` : ''}</div>`;
      output.append(card);
    }
    output.append(details);
    if(section==='hotel'){
      const more=document.createElement('button');more.type='button';more.className='search-repeat-button';more.textContent=remoteLoading?'追加の30件を読み込み中…':'さらに30件を見る';more.hidden=!remotePage?.next_cursor;more.disabled=remoteLoading;
      more.addEventListener('click',()=>runHotelSearch(undefined,true).catch(error=>{if(error.name!=='AbortError'){output.insertAdjacentHTML('beforeend','<p class="feature-note">追加取得できませんでした。再検索してください。</p>');}}));output.append(more);
      if(remotePage?.limited){const note=document.createElement('p');note.className='feature-note';note.textContent='表示は近い順に60件までです。ほかの候補を探すには、検索地点を変えるか、検索範囲を狭めて再検索してください。';output.append(note);}
    }
  };
  try {
    features = (await (catalog || loadFeatureCatalog())).filter(feature => (feature.section || 'dining') === section);
    if (visibleFeatures(features, today(), preview).some(feature => feature.id === initialFeature)) selectedFeatures.add(initialFeature);
    render();
  } catch (error) {
    root.hidden = true; console.warn('特集を読み込めませんでした', error);
  }
  async function runHotelSearch(signal,append=false){
    if(append&&(!remotePage?.next_cursor||remoteLoading))return;
    if(!append)invalidateResults();
    if(!selectedFeatures.size)visibleFeatures(features,today(),preview).forEach(f=>selectedFeatures.add(f.id));
    const chosen=visibleFeatures(features,today(),preview).filter(f=>selectedFeatures.has(f.id));
    const origin=getOrigin(),radius=getRadius?getRadius():currentRadius(chosen[0]);
    if(!chosen.length||!origin){hasSearched=true;originUnavailable=!origin;render();return;}
    const version=++requestVersion;remoteController=new AbortController();
    const abort=()=>remoteController?.abort();
    signal?.addEventListener('abort',abort,{once:true});
    if(signal?.aborted)remoteController.abort();
    hasSearched=true;originUnavailable=false;remoteLoading=true;render();
    try{
      const params=new URLSearchParams({lat:origin.lat,lng:origin.lng,radius,features:chosen.map(f=>f.id).join(','),...(append?{cursor:remotePage.next_cursor}:{})});
      const response=await fetch('https://yutai-map-api.yutaisamurai.workers.dev/v1/hotels/search?'+params,{signal:remoteController.signal,cache:'no-store'});
      if(!response.ok)throw new Error('Hotel search '+response.status);
      const page=await response.json();
      if(version!==requestVersion)return;
      remotePage={...page,results:[...(append?remotePage.results:[]),...page.results]};
      if(remotePage.results.length>60)throw new Error('Hotel display limit exceeded');
      if(!append)track('benefit_search',{section,mode:getCenterLabel()==='現在地'?'current':'place',result_count:page.total});
    }finally{
      signal?.removeEventListener('abort',abort);
      if(version===requestVersion){remoteLoading=false;render();}
    }
  }
  return {
    refresh() { render(); },
    invalidate() { invalidateResults(); render(); },
    async search(signal) {
      if(section==='hotel')return runHotelSearch(signal);
      if (!selectedFeatures.size) visibleFeatures(features, today(), preview).forEach(feature => selectedFeatures.add(feature.id));
      originUnavailable = !getOrigin(); hasSearched = true; render();
      const chosen = visibleFeatures(features, today(), preview).filter(feature => selectedFeatures.has(feature.id));
      if (chosen.length && (getOrigin() || chosen.every(feature => currentRadius(feature) === 'all'))) {
        track('benefit_search', {section, mode: getCenterLabel() === '現在地' ? 'current' : 'place', result_count: featureSearchResults(chosen, getOrigin(), currentRadius).length});
      }
    }
  };
}

export async function loadFeatureCatalog(fetcher = fetch) {
  const response = await fetcher('./data/features/index.json', {cache:'no-store'});
  if (!response.ok) throw new Error('Feature data unavailable');
  const data = await response.json();
  return loadFeatureData(data.features, fetcher);
}

// One unavailable remote feature must not hide other verified features.
export async function loadFeatureData(configs, fetcher = fetch) {
  const hotelConfigs=configs.filter(c=>c.section==='hotel');
  let hotelMetadata=[];
  if(hotelConfigs.length){
    try{const response=await fetcher('https://yutai-map-api.yutaisamurai.workers.dev/v1/hotels/catalog');if(response.ok)hotelMetadata=(await response.json()).features || [];}catch{}
  }
  const results = await Promise.allSettled(configs.map(async config => {
    if(config.section==='hotel'){
      const metadata=hotelMetadata.find(f=>f.id===config.id);
      if(!metadata||metadata.stores?.length)throw new Error('Hotel metadata unavailable');
      return validateFeature({...config,...metadata,stores:[],indexed:true});
    }
    if (config.updateMode !== 'scheduled') return validateFeature(config);
    if (!safeUrl(config.storeDataUrl)) throw new Error('Invalid feature data URL');
    const response = await fetcher(config.storeDataUrl, {signal:AbortSignal.timeout(10000)});
    if (!response.ok) throw new Error('Feature snapshot unavailable');
    const snapshot = await response.json();
    if (snapshot.id !== config.id) throw new Error('Feature snapshot mismatch');
    return validateFeature({...config, stores:snapshot.stores, checkedOn:snapshot.checkedOn});
  }));
  return results.flatMap(result => {
    if (result.status === 'fulfilled') return [result.value];
    console.warn('特集データを読み込めませんでした', result.reason);
    return [];
  });
}

