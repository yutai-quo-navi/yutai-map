// Public expiry ledger; does not request location or store data.
export function japanDate(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-US', {timeZone:'Asia/Tokyo', year:'numeric', month:'2-digit', day:'2-digit'}).formatToParts(now);
  const get = type => parts.find(p => p.type === type).value;
  return `${get('year')}-${get('month')}-${get('day')}`;
}
export function daysRemaining(date, today = japanDate()) {
  return Math.round((Date.parse(`${date}T00:00:00Z`) - Date.parse(`${today}T00:00:00Z`)) / 86400000);
}
export function monthEntries(entries, today = japanDate()) {
  return entries.filter(e => e.status === 'confirmed' && /^\d{4}-\d{2}-\d{2}$/.test(e.expiry_date) && e.expiry_date.startsWith(today.slice(0,7)))
    .sort((a,b) => a.expiry_date.localeCompare(b.expiry_date) || a.code.localeCompare(b.code));
}
export function deadlineState(days) {
  if(days < 0) return {label:'期限終了', tone:'expired'};
  if(days === 0) return {label:'🚨 本日まで', tone:'today'};
  return {label:`${days <= 3 ? '🔥 ' : days <= 7 ? '⚠️ ' : ''}あと${days}日`, tone:days <= 3 ? 'urgent' : days <= 7 ? 'soon' : 'normal'};
}
export function initExpiry({resolveIssuer, search}) {
  const storePanel = document.querySelector('#storePanel');
  const expiryPanel = document.querySelector('#expiryPanel');
  const list = document.querySelector('#expiryList');
  const status = document.querySelector('#expiryStatus');
  const tabs = [...document.querySelectorAll('[data-content-tab]')];
  let entries = [], loaded = false, loading = null, lastDate = '';
  function showStore() { show('stores'); }
  function show(id) {
    storePanel.hidden = id !== 'stores'; expiryPanel.hidden = id !== 'expiry';
    tabs.forEach(tab => { const active = tab.dataset.contentTab === id; tab.setAttribute('aria-selected', String(active)); tab.tabIndex = active ? 0 : -1; });
    if(id === 'expiry') load();
  }
  function node(tag, text, className) {
    const el = document.createElement(tag); el.textContent = text;
    if(className) el.className = className;
    return el;
  }
  function render() {
    const today = japanDate(); lastDate = today;
    const current = monthEntries(entries, today);
    const pending = current.filter(e => daysRemaining(e.expiry_date, today) >= 0);
    document.querySelector('#expiryHeading').textContent = `🔥 ${Number(today.slice(5,7))}月期限`;
    document.querySelector('#expiryMonth').textContent = `${today.slice(0,4)}年${Number(today.slice(5,7))}月 / 日本時間`;
    document.querySelector('#expiryCount').textContent = String(pending.length);
    status.textContent = current.length ? `今月${current.length}件 / これから期限を迎える優待${pending.length}件` : '今月の公式確認済みの期限情報はまだありません';
    list.replaceChildren();
    for(const entry of current) {
      const days = daysRemaining(entry.expiry_date, today), state = deadlineState(days);
      const card = node('article', '', `expiry-card ${state.tone}`);
      card.append(node('p', state.label, 'expiry-countdown'), node('h3', `${entry.company_name}（${entry.code}）`), node('p', entry.benefit_name, 'expiry-benefit'));
      const [,month,day] = entry.expiry_date.split('-').map(Number);
      card.append(node('p', `${month}/${day}まで / ${entry.expiry_type}`, 'expiry-date'));
      if(entry.issue) card.append(node('p', `対象：${entry.issue}`, 'expiry-meta'));
      if(entry.notes) card.append(node('p', entry.notes, 'expiry-meta'));
      if(entry.brands?.length) card.append(node('p', entry.brands.join(' / '), 'expiry-meta'));
      const actions = node('div', '', 'card-actions');
      const issuer = resolveIssuer(entry);
      if(days >= 0 && issuer) {
        const button = node('button', 'この優待が使える店を探す', 'expiry-search'); button.type = 'button';
        button.addEventListener('click', () => { showStore(); search(entry, issuer); }); actions.append(button);
      }
      const url = String(entry.source_url || '');
      if(/^https?:\/\//i.test(url)) {
        const link = node('a', '公式情報'); link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer'; actions.append(link);
      }
      card.append(actions, node('p', `公式確認：${entry.checked_on}`, 'expiry-meta')); list.append(card);
    }
  }
  async function load() {
    if(loaded) { render(); return; }
    if(loading) return loading;
    status.textContent = '期限情報を読み込んでいます…';
    loading = (async () => {
      try {
        const response = await fetch('./data/expiry.json', {cache:'no-store'});
        if(!response.ok) throw new Error('expiry unavailable');
        const data = await response.json();
        if(data.version !== 1 || !Array.isArray(data.entries)) throw new Error('invalid expiry ledger');
        entries = data.entries; loaded = true; render();
      } catch {
        status.textContent = '期限情報を読み込めませんでした';
        const retry = node('button', '再読み込み', 'category-filter'); retry.type = 'button'; retry.addEventListener('click', load); list.replaceChildren(retry);
      } finally { loading = null; }
    })();
    return loading;
  }
  tabs.forEach((tab,index) => {
    tab.addEventListener('click', () => show(tab.dataset.contentTab));
    tab.addEventListener('keydown', event => {
      if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length-1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
      tabs[next].focus(); show(tabs[next].dataset.contentTab);
    });
  });
  document.addEventListener('visibilitychange', () => { if(!document.hidden && loaded && !expiryPanel.hidden) render(); });
  // Refresh countdowns when a page stays open across midnight in Japan.
  setInterval(() => { if(loaded && !expiryPanel.hidden && japanDate() !== lastDate) render(); }, 30000);
  return {showStore, refresh:() => { if(loaded) render(); }};
}
