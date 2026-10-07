// Manually maintained features are independent of regular issuer search/sync.
export const FEATURE_RADIUS_METERS = 3_000_000;
export function featureRadius(feature) { return feature.radiusMeters ?? FEATURE_RADIUS_METERS; }

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
      feature.updateMode !== 'manual' || !['draft', 'public'].includes(feature.status) ||
      !Array.isArray(feature.stores)) throw new Error('Invalid manual feature');
  if (!Number.isFinite(featureRadius(feature)) || featureRadius(feature) <= 0 || featureRadius(feature) > FEATURE_RADIUS_METERS)
    throw new Error('Invalid feature radius');
  const ids = new Set();
  for (const store of feature.stores) {
    if (!store.id || ids.has(store.id) || !store.name || !store.address || !store.conditions)
      throw new Error('Invalid or duplicate feature store');
    ids.add(store.id);
    const hasLat = store.lat != null, hasLng = store.lng != null;
    if (hasLat !== hasLng || (hasLat && (!Number.isFinite(store.lat) || !Number.isFinite(store.lng) ||
        Math.abs(store.lat) > 90 || Math.abs(store.lng) > 180))) throw new Error('Invalid coordinates');
  }
  if (feature.status === 'public' && (!feature.stores.length || !safeUrl(feature.sourceUrl) ||
      !validDate(feature.checkedOn) || !validDate(feature.validFrom) || !validDate(feature.validThrough) ||
      feature.validFrom > feature.validThrough || feature.checkedOn > feature.validThrough ||
      feature.stores.some(store => store.verified !== true || store.lat == null))) throw new Error('Unverified public feature');
  return feature;
}
export function visibleFeatures(features, today, preview = false) {
  return features.map(validateFeature).filter(feature =>
    (feature.status === 'public' && feature.validFrom <= today && today <= feature.validThrough) ||
    (preview && feature.status === 'draft'));
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
    .filter(store => store.distance == null || store.distance <= featureRadius(feature))
    .sort((a, b) => (a.distance ?? Infinity) - (b.distance ?? Infinity));
}
const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));

export async function initSpecialFeatures({root, getOrigin, getCenterLabel, createDeadlineBubble, getDeadline, preview = false}) {
  if (!root) return {refresh() {}};
  let active = null, features = [];
  const today = () => new Intl.DateTimeFormat('sv-SE', {timeZone:'Asia/Tokyo'}).format(new Date());
  const render = () => {
    features = visibleFeatures(features, today(), preview);
    if (!features.some(feature => feature.id === active?.id)) active = null;
    root.hidden = !features.length;
    root.innerHTML = '';
    if (!features.length) return;
    root.innerHTML = '<h2 class="selection-heading">レア優待店 特集</h2><div class="feature-buttons"></div><div class="feature-results" aria-live="polite"></div>';
    for (const feature of features) {
      const item = document.createElement('div'); item.className = 'feature-item';
      const button = document.createElement('button'); button.type = 'button';
      button.className = 'feature-button';
      button.textContent = feature.shortName || feature.issuer.name;
      button.setAttribute('aria-label', feature.title);
      button.setAttribute('aria-controls', 'specialFeatureResults');
      const bubble = createDeadlineBubble(feature.issuer.id);
      if (bubble) bubble.classList.add('feature-deadline');
      button.setAttribute('aria-pressed', String(active?.id === feature.id));
      button.dataset.feature = feature.id;
      button.addEventListener('click', () => {
        active = active?.id === feature.id ? null : feature; render();
        root.querySelector(`[data-feature="${feature.id}"]`)?.focus();
      });
      const caption = document.createElement('p'); caption.className = 'feature-caption';
      const subtitle = document.createElement('span'); subtitle.textContent = feature.subtitle || '';
      const count = document.createElement('span');
      count.textContent = feature.stores.length ? `${feature.stores.length}店舗紹介` : '店舗確認中';
      caption.append(subtitle, count); item.append(button);
      if (bubble) item.append(bubble);
      item.append(caption);
      root.querySelector('.feature-buttons').append(item);
    }
    root.querySelector('.feature-results').id = 'specialFeatureResults';
    if (!active) return;
    const origin = getOrigin(), stores = featureStores(active, origin);
    const output = root.querySelector('.feature-results');
    const label = getCenterLabel();
    output.innerHTML = `<p class="feature-note">${active.status === 'draft' ? '下書き・利用期間と対象店舗は未確認。' : ''}${esc(active.description)}<br>${origin ? `${esc(label)}から${(featureRadius(active)/1000).toLocaleString('ja-JP')}km以内・距離が分かる店舗から近い順` : '全国の対象店舗・掲載順（検索地点を指定すると近い順）'}／${stores.length}件表示・全${active.stores.length}店舗</p>`;
    if (origin && !stores.length && active.stores.length) output.innerHTML += '<p class="feature-note">この範囲に対象店舗はありません。別の場所を指定してお探しください。</p>';
    if (active.status === 'public') output.innerHTML += `<p class="feature-note">特典提供期間：${esc(active.validFrom)}〜${esc(active.validThrough)}／確認日：${esc(active.checkedOn)}</p>`;
    const deadline = getDeadline(active.issuer.id);
    output.innerHTML += `<p class="feature-note">${esc(active.issuer.name)}（${esc(active.issuer.code)}）<br>${deadline ? `優待券の利用期限：${esc(deadline.date)}（${deadline.days === 0 ? '本日まで' : 'あと' + deadline.days + '日'}）／${esc(deadline.issue)}。お手持ちの券面をご確認ください。` : '優待券の利用期限は、お手持ちの券面をご確認ください。'}</p>`;
    for (const store of stores) {
      const card = document.createElement('article'); card.className = 'card feature-card';
      const mapUrl = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(store.name + ' ' + store.address)}`;
      const sourceUrl = safeUrl(store.sourceUrl || active.sourceUrl);
      card.innerHTML = `<h3 class="store-name"><a class="store-link" href="${mapUrl}" target="_blank" rel="noopener noreferrer">${esc(store.name)}</a></h3><p class="store-address">${esc(store.address)}</p><p class="feature-note">${store.distance == null ? '距離未算出' : `${Math.round(store.distance / 1000).toLocaleString('ja-JP')}km・${esc(label)}から`}</p><p class="feature-conditions">${esc(store.conditions)}</p>${store.menu ? `<p class="feature-note">${esc(store.menu)}</p>` : ''}${sourceUrl ? `<a href="${esc(sourceUrl)}" target="_blank" rel="noopener noreferrer">公式情報を確認</a>` : ''}`;
      output.append(card);
    }
  };
  try {
    const response = await fetch('./data/features/index.json', {cache:'no-store'});
    if (!response.ok) throw new Error('Feature data unavailable');
    const data = await response.json();
    features = data.features; render();
  } catch (error) {
    root.hidden = true; console.warn('特集を読み込めませんでした', error);
  }
  return {refresh: render};
}
