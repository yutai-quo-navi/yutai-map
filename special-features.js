// Feature search uses independent radii and either manual or scheduled data.
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
  if (feature.status === 'public' && (!feature.stores.length || !safeUrl(feature.sourceUrl) ||
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
const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));

export async function initSpecialFeatures({root, getOrigin, getCenterLabel, ensureOrigin, createDeadlineBubble, getDeadline, preview = false, section = 'dining', catalog = null}) {
  if (!root) return {refresh() {}};
  let active = null, features = [], resolvingOrigin = false, originUnavailable = false, failedOrigin = null;
  const selectedRadii = new Map();
  const unit = section === 'hotel' ? '施設' : '店舗';
  const resultsId = `${root.id || 'specialFeature'}Results`;
  const heading = section === 'hotel' ? '宿泊・ホテル優待 特集' : 'レア優待店 特集';
  const currentRadius = feature => selectedRadii.get(feature.id) ?? featureRadius(feature);
  const today = () => new Intl.DateTimeFormat('sv-SE', {timeZone:'Asia/Tokyo'}).format(new Date());
  const render = () => {
    const displayed = visibleFeatures(features, today(), preview);
    if (!displayed.some(feature => feature.id === active?.id)) active = null;
    root.hidden = !displayed.length;
    root.innerHTML = '';
    if (!displayed.length) return;
    root.innerHTML = `<h2 class="selection-heading">${heading}</h2><div class="feature-buttons"></div><div class="feature-results" aria-live="polite"></div>`;
    for (const feature of displayed) {
      const item = document.createElement('div'); item.className = 'feature-item';
      const button = document.createElement('button'); button.type = 'button';
      button.className = 'feature-button';
      button.textContent = feature.shortName || feature.issuer.name;
      button.setAttribute('aria-label', feature.title);
      button.setAttribute('aria-controls', resultsId);
      const bubble = feature.status === 'ended' ? document.createElement('span') : createDeadlineBubble(feature.issuer.id, feature.deadlineBenefitPattern);
      if (feature.status === 'ended') {
        bubble.className = 'voucher-deadline-bubble'; bubble.textContent = '今回分は終了';
        bubble.setAttribute('aria-label', `利用期限終了：${feature.validThrough}`);
      }
      if (bubble) bubble.classList.add('feature-deadline');
      button.setAttribute('aria-pressed', String(active?.id === feature.id));
      button.dataset.feature = feature.id;
      button.addEventListener('click', async () => {
        if (resolvingOrigin) return;
        if (active?.id === feature.id) { active = null; render(); return; }
        active = feature; resolvingOrigin = true; originUnavailable = false; render();
        try { if (ensureOrigin) originUnavailable = !(await ensureOrigin()); }
        catch (error) { originUnavailable = true; console.warn('特集の検索地点を取得できませんでした', error); }
        finally { failedOrigin = originUnavailable ? getOrigin() : null; resolvingOrigin = false; render(); }
        root.querySelector(`[data-feature="${feature.id}"]`)?.focus();
      });
      const caption = document.createElement('p'); caption.className = 'feature-caption';
      const subtitle = document.createElement('span'); subtitle.textContent = feature.subtitle || '';
      const count = document.createElement('span');
      count.textContent = feature.stores.length ? `${feature.status === 'ended' ? '前回' : ''}${feature.stores.length}${unit}紹介` : `${unit}確認中`;
      caption.append(subtitle, count); item.append(button);
      if (bubble) item.append(bubble);
      item.append(caption);
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
        if (active?.id === feature.id) {
          render(); root.querySelector(`[data-feature-radius="${feature.id}"]`)?.focus();
        }
      });
      radiusLabel.append(select); item.append(radiusLabel);
      root.querySelector('.feature-buttons').append(item);
    }
    root.querySelector('.feature-results').id = resultsId;
    if (!active) return;
    const ended = active.status === 'ended';
    const nationwide = currentRadius(active) === 'all';
    const origin = originUnavailable ? null : getOrigin(), stores = featureStores({...active, radiusMeters:currentRadius(active)}, origin);
    const output = root.querySelector('.feature-results');
    if (resolvingOrigin || (!nationwide && (originUnavailable || !origin))) {
      output.innerHTML = `<p class="feature-note">${resolvingOrigin ? '検索地点を確認しています…' : '距離を表示するには、現在地の利用を許可するか、場所を指定してください。'}</p>`;
      return;
    }
    const label = getCenterLabel();
    const details = document.createElement("div");
    const info = section === "hotel" ? details : output;
    output.innerHTML = `<p class="feature-note">${section === "hotel" ? "" : `${active.status === 'draft' ? `下書き・利用期間と対象${unit}は未確認。` : ''}${esc(active.description)}<br>`}${origin ? `${nationwide ? `全国の対象${unit}` : `${esc(label)}から${(currentRadius(active)/1000).toLocaleString('ja-JP')}km以内`}・直線距離が近い順` : `全国の対象${unit}・掲載順（検索地点を指定すると距離を表示して近い順）`}／${stores.length}件表示・全${active.stores.length}${unit}</p>`;
    if (origin && !stores.length && active.stores.length) output.innerHTML += `<p class="feature-note">この範囲に対象${unit}はありません。別の場所を指定してお探しください。</p>`;
    if (section === 'hotel') info.innerHTML = `<p class="feature-note">${esc(active.description)}</p>`;
    if (active.status === 'public') info.innerHTML += `<p class="feature-note">${active.availability === 'continuous' ? '' : `特典提供期間：${esc(active.validFrom)}〜${esc(active.validThrough)}／`}確認日：${esc(active.checkedOn)}</p>`;
    if (active.voucherName) info.innerHTML += `<p class="feature-note">${esc(active.voucherName)}</p>`;
    const deadline = getDeadline(active.issuer.id, active.deadlineBenefitPattern);
    if (!ended) info.innerHTML += `<p class="feature-note">${esc(active.issuer.name)}（${esc(active.issuer.code)}）<br>${deadline ? `優待券の利用期限：${esc(deadline.date)}（${deadline.days === 0 ? '本日まで' : 'あと' + deadline.days + '日'}）／${esc(deadline.issue)}。お手持ちの券面をご確認ください。` : '優待券の利用期限は、お手持ちの券面をご確認ください。'}</p>`;
    for (const store of stores) {
      const card = document.createElement('article'); card.className = 'card feature-card';
      const mapUrl = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(store.name + ' ' + store.address)}`;
      const sourceUrl = safeUrl(store.sourceUrl || active.sourceUrl);
      card.innerHTML = `<h3 class="store-name"><a class="store-link" href="${mapUrl}" target="_blank" rel="noopener noreferrer">${esc(store.name)}</a></h3><p class="store-address">${esc(store.address)}</p><p class="feature-note">${store.distance == null ? '距離未確認'  : `${featureDistanceLabel(store.distance)}・${esc(label)}から`}</p><p class="feature-conditions">${esc(store.conditions)}</p>${store.coordinateNote ? `<p class="feature-note">${esc(store.coordinateNote)}</p>` : ''}${store.menu ? `<p class="feature-note">${esc(store.menu)}</p>` : ''}${sourceUrl ? `<a href="${esc(sourceUrl)}" target="_blank" rel="noopener noreferrer">公式情報を確認</a>` : ''}`;
      output.append(card);
    }
    if (section === "hotel") output.append(details);
  };
  try {
    features = (await (catalog || loadFeatureCatalog())).filter(feature => (feature.section || 'dining') === section);
    render();
  } catch (error) {
    root.hidden = true; console.warn('特集を読み込めませんでした', error);
  }
  return {refresh() { if (getOrigin() !== failedOrigin) originUnavailable = false; render(); }};
}

export async function loadFeatureCatalog(fetcher = fetch) {
  const response = await fetcher('./data/features/index.json', {cache:'no-store'});
  if (!response.ok) throw new Error('Feature data unavailable');
  const data = await response.json();
  return loadFeatureData(data.features, fetcher);
}

// One unavailable remote feature must not hide other verified features.
export async function loadFeatureData(configs, fetcher = fetch) {
  const results = await Promise.allSettled(configs.map(async config => {
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
