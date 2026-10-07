// Shared voucher deadlines use Japanese calendar days, independently of device timezone.
export function japanDay(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Tokyo',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(now);
  const get = type => parts.find(p => p.type === type).value;
  return get('year')+'-'+get('month')+'-'+get('day');
}
export function deadlineDays(date, now = new Date()) {
  if(!/^\d{4}-\d{2}-\d{2}$/.test(date)) return null;
  const [y,m,d] = date.split('-').map(Number);
  const stamp = Date.UTC(y,m-1,d);
  if(new Date(stamp).toISOString().slice(0,10)!==date) return null;
  const [ty,tm,td] = japanDay(now).split('-').map(Number);
  return Math.round((stamp-Date.UTC(ty,tm-1,td))/86400000);
}
export function nearestDeadline(entries, issuer, now = new Date(), benefitPattern = null) {
  return entries.filter(e=>e.issuer===issuer && e.status==='confirmed' && (!benefitPattern || new RegExp(benefitPattern).test(e.benefit || '')))
    .map(e=>({...e,days:deadlineDays(e.date,now)}))
    .filter(e=>e.days!==null && e.days>=0 && (!e.expires_at || Date.parse(e.expires_at)>now.getTime()))
    .sort((a,b)=>a.date.localeCompare(b.date))[0] || null;
}
export function deadlineLabel(entry) {
  return entry.days===0 ? '⚠️本日失効' : '⚠️失効'+entry.days+'日前';
}

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
  return entries.filter(e => e.status === 'confirmed' && (e.expiry_date || e.research_month || '').slice(0,7) === today.slice(0,7))
    .sort((a,b) => (a.expiry_date || `${a.research_month}-99`).localeCompare(b.expiry_date || `${b.research_month}-99`) || a.code.localeCompare(b.code));
}
export function deadlineState(days) {
  if(days < 0) return {label:'期限終了', tone:'expired'};
  if(days === 0) return {label:'🚨 本日まで', tone:'today'};
  return {label:`${days <= 3 ? '🔥 ' : days <= 7 ? '⚠️ ' : ''}あと${days}日`, tone:days <= 3 ? 'urgent' : days <= 7 ? 'soon' : 'normal'};
}

// Feature vouchers read the same editable expiry ledger as the expiry page.
export function voucherEntriesFromLedger(entries) {
  return entries.filter(entry => entry.issuer_id && entry.expiry_type === '利用期限' &&
    entry.status === 'confirmed' && entry.expiry_date).map(entry => ({
      id:entry.id, issuer:entry.issuer_id, code:entry.code, name:entry.company_name,
      benefit:entry.benefit_name, date:entry.expiry_date, status:entry.status,
      issue:entry.issue || '対象発行回未登録'
    }));
}
