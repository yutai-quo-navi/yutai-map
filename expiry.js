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
export function nearestDeadline(entries, issuer, now = new Date()) {
  return entries.filter(e=>e.issuer===issuer && e.status==='confirmed')
    .map(e=>({...e,days:deadlineDays(e.date,now)}))
    .filter(e=>e.days!==null && e.days>=0 && (!e.expires_at || Date.parse(e.expires_at)>now.getTime()))
    .sort((a,b)=>a.date.localeCompare(b.date))[0] || null;
}
export function deadlineLabel(entry) {
  return entry.days===0 ? '⚠ 本日が優待期限' : '⚠ 優待期限まであと'+entry.days+'日';
}
