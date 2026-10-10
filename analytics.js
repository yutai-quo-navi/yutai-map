// Shared by the search application and static guide pages. Never accept free text.
export const MEASUREMENT_ID = 'G-1KH2LCX7HT';
const DISABLED_KEY = 'yutai-analytics-disabled';
const disabledFlag = `ga-disable-${MEASUREMENT_ID}`;
const production = typeof window !== 'undefined' && typeof location !== 'undefined' && location.hostname === 'yutai-quo-navi.github.io';
let disabled = false;
try { disabled = localStorage.getItem(DISABLED_KEY) === '1'; } catch {}
if (typeof window !== 'undefined') window[disabledFlag] = disabled || !production;

const cleanUrl = value => {
  try { const url = new URL(value); return url.protocol === 'https:' ? url.origin + url.pathname : ''; }
  catch { return ''; }
};
const fields = {
  benefit_tab: {section: /^(dining|hotel|expiry)$/},
  benefit_select: {section: /^(dining|hotel)$/, benefit_id: /^[a-z0-9-]{1,80}$/, selected: /^(true|false)$/},
  benefit_search: {section: /^(dining|hotel)$/, mode: /^(current|place)$/, result_count: /^\d{1,6}$/},
  outbound_action: {section: /^(dining|hotel)$/, destination: /^(map|official)$/}
};

export function track(name, parameters = {}) {
  if (!production || window[disabledFlag] || !fields[name] || !window.gtag) return;
  const safe = {};
  for (const [key, rule] of Object.entries(fields[name])) {
    if (rule.test(String(parameters[key] ?? ''))) safe[key] = parameters[key];
  }
  window.gtag('event', name, {...safe, send_to: MEASUREMENT_ID});
}

if (production && !disabled) {
  window.dataLayer = window.dataLayer || [];
  window.gtag = function () { window.dataLayer.push(arguments); };
  window.gtag('consent', 'default', {analytics_storage: 'granted', ad_storage: 'denied', ad_user_data: 'denied', ad_personalization: 'denied'});
  window.gtag('js', new Date());
  const page = {
    page_location: cleanUrl(location.href), page_referrer: cleanUrl(document.referrer),
    page_title: document.title,
    allow_google_signals: false, allow_ad_personalization_signals: false
  };
  window.gtag('config', MEASUREMENT_ID, {...page, send_page_view: false});
  window.gtag('event', 'page_view', {...page, send_to: MEASUREMENT_ID});
  const script = document.createElement('script');
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtag/js?id=${MEASUREMENT_ID}`;
  document.head.append(script);
}

const toggle = typeof document !== 'undefined' ? document.getElementById('analyticsDisabled') : null;
if (toggle) {
  toggle.checked = disabled;
  toggle.addEventListener('change', () => {
    window[disabledFlag] = toggle.checked;
    try { localStorage.setItem(DISABLED_KEY, toggle.checked ? '1' : '0'); } catch {}
    location.reload();
  });
}

// No link URL, store address, search input or coordinates are included.
if (typeof document !== 'undefined') document.addEventListener('click', event => {
  const node = event.target.closest?.('.card a');
  if (!node) return;
  const section = node.closest('#hotelFeatures') ? 'hotel' : 'dining';
  if (node.matches('.card a')) {
    let host; try { host = new URL(node.href).hostname; } catch { return; }
    track('outbound_action', {section, destination: host === 'www.google.com' || host === 'maps.google.com' ? 'map' : 'official'});
  }
});
