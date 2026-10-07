import {test} from 'node:test';
import assert from 'node:assert/strict';
import {japanDate, daysRemaining, monthEntries, deadlineState, nearestDeadline, latestExpiredDeadline} from '../expiry.js';

test('latest confirmed expiry wins duplicates and a new valid voucher replaces expired status', () => {
  const now=new Date('2026-10-08T00:00:00Z');
  const old={id:'voucher',issuer:'balnibarbi',date:'2026-09-30',status:'confirmed',benefit:'食事券'};
  const entries=[old,{...old,date:'2027-03-31'},{...old,id:'new',date:'2027-09-30'},
    {...old,date:'2028-09-30',status:'checking'}, {...old,date:'2029-09-30',benefit:'別の券'}];
  assert.equal(nearestDeadline([old],'balnibarbi',now),null);
  assert.equal(latestExpiredDeadline([old],'balnibarbi',now).date,'2026-09-30');
  assert.equal(nearestDeadline(entries,'balnibarbi',now,'食事券').date,'2027-09-30');
});

test('Japan calendar changes at 15:00 UTC irrespective of host timezone', () => {
  assert.equal(japanDate(new Date('2026-09-30T14:59:59Z')), '2026-09-30');
  assert.equal(japanDate(new Date('2026-09-30T15:00:00Z')), '2026-10-01');
});
test('requested countdown examples and urgency boundaries', () => {
  assert.equal(daysRemaining('2026-10-12','2026-10-05'), 7);
  assert.equal(daysRemaining('2026-10-15','2026-10-05'), 10);
  assert.equal(daysRemaining('2026-10-31','2026-10-05'), 26);
  assert.equal(deadlineState(7).tone, 'soon');
  assert.equal(deadlineState(3).tone, 'urgent');
  assert.equal(deadlineState(0).label, '🚨 本日まで');
  assert.equal(deadlineState(-1).tone, 'expired');
  assert.equal(daysRemaining('2027-01-01','2026-12-31'), 1);
  assert.equal(daysRemaining('2028-03-01','2028-02-28'), 2);
});
test('only current year and month confirmed entries; expired entries remain labeled', () => {
  const entries=[['old','2025-10-12','confirmed'],['past','2026-10-01','confirmed'],['ok','2026-10-12','confirmed'],['hidden','2026-10-15','checking'],['next','2026-11-01','confirmed']].map(([code,expiry_date,status]) => ({code,expiry_date,status}));
  assert.deepEqual(monthEntries(entries,'2026-10-05').map(e=>e.code), ['past','ok']);
});
test('approved month-only entries stay in their month without inventing a date', () => {
  const entries=[{code:'3197',expiry_date:'',research_month:'2026-09',status:'confirmed'}];
  assert.equal(monthEntries(entries,'2026-09-05').length,1);
  assert.equal(monthEntries(entries,'2026-10-05').length,0);
  assert.equal(entries[0].expiry_date,'');
});
