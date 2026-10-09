import {test} from 'node:test';
import assert from 'node:assert/strict';
import {upcomingExpiries,expiryGroup,cleanExpirySettings,dueExpiryAlerts,parseHoldings,cleanAlertDays} from '../expiry-search.js';
const now=new Date('2026-10-08T15:00:00Z');
const row=(id,date,extra={})=>({id,code:'0001',company_name:'会社',benefit_name:'優待',expiry_date:date,status:'confirmed',category:'dining',...extra});
test('60 day window includes today and last day, unregistered issuers, but excludes expired and unconfirmed records',()=> {
 const entries=[row('past','2026-10-08'),row('today','2026-10-09'),row('end','2026-12-08'),row('future','2026-12-09'),row('checking','2026-10-10',{status:'checking'}),row('invalid','2026-11-31')];
 assert.deepEqual(upcomingExpiries(entries,now).map(r=>r.id),['today','end']);
});
test('month-only dates are visible but cannot trigger alerts',()=> {
 const entry=row('month','',{research_month:'2026-11'});
 assert.equal(upcomingExpiries([entry],now).length,1);
 assert.deepEqual(dueExpiryAlerts([entry],{month:{owned:true,days:[0,1,2,3]}},now),[]);
});
test('groups separate hotels, transport and service; action deadlines go to applications',()=> {
 assert.equal(expiryGroup(row('hotel','',{code:'9024',benefit_name:'無料ペア宿泊券',category:'leisure'})),'hotel');
 assert.equal(expiryGroup(row('rail','',{code:'9005',category:'other'})),'leisure');
 assert.equal(expiryGroup(row('clean','',{code:'9731',category:'leisure'})),'service');
 assert.equal(expiryGroup(row('apply','',{expiry_type:'申込期限'})),'catalog');
});
test('reminders fire only on chosen days and only for held records, using Japan dates',()=> {
 const entries=[row('held','2026-10-12'),row('not-held','2026-10-12')];
 const settings={held:{owned:true,days:[0,3]},'not-held':{owned:false,days:[3]}};
 assert.deepEqual(dueExpiryAlerts(entries,settings,now).map(r=>r.id),['held']);
 assert.equal(dueExpiryAlerts(entries,settings,new Date('2026-10-10T00:00:00Z')).length,0);
 assert.equal(dueExpiryAlerts(entries,settings,new Date('2026-10-12T00:00:00Z')).length,1);
 assert.equal(dueExpiryAlerts(entries,settings,new Date('2026-10-13T00:00:00Z')).length,0);
});
test('saved preferences reject malformed and out-of-range reminder days',()=> {
 assert.deepEqual(cleanExpirySettings({a:{owned:true,days:[0,1,1,3,4,-1,'2']}}),{a:{owned:true,days:[0,1,3]}});
 assert.deepEqual(cleanExpirySettings([]),{});
});

test('global reminder days override legacy per-voucher days, with empty meaning off',()=>{
 const e=row('held','2026-10-12'),s={held:{owned:true,days:[]}};
 assert.equal(dueExpiryAlerts([e],s,now,[3]).length,1);
 assert.equal(dueExpiryAlerts([e],s,now,[]).length,0);
});
test('later dates are available separately without reintroducing expired records',()=>{
 assert.deepEqual(upcomingExpiries([row('past','2026-10-08'),row('future','2027-01-01')],now,Infinity).map(e=>e.id),['future']);
});

test('brokerage paste recognizes full-width issuer names and ignores prices, dates and controls',()=>{
 const entries=[['8016','オンワードホールディングス'],['9973','KOZOホールディングス'],['2914','JT'],['4979','OATアグリオ'],['3036','アルコニックス'],['2858','別会社']].map(([code,company_name])=>({code,company_name}));
 const text=`8016 オンワードＨＤ決算発表日：2026/10/08（済） --/--/-- 101 278 757 +58 +8.30 +48,379 +172.30 76,457 詳細 メールアラート画面へ
現買 現売 積立 9973 ＫＯＺＯＨＤ --/--/-- 101 22 19 +1 +5.56 -303 -13.64 1,919 詳細
現買 現売 積立 株オプ 2914 ＪＴ決算発表日：2026/10/29（予定） --/--/-- 74 2,693 7,195 +235
現買 現売 積立 4979 ＯＡＴアグリオ 22/11/10 1 1,669 2,858 +80 2,858 詳細
現買 現売 積立 株オプ 3036 アルコニックス`;
 assert.deepEqual(parseHoldings(text,entries).matches.map(e=>e.code).sort(),['2914','3036','4979','8016','9973']);
 assert.equal(parseHoldings('価格 2858 株数 100',entries).matches.length,0);
});
test('paste accepts delimited codes, deduplicates, reports unknown and supports letter codes',()=>{
 const entries=[{code:'8016',company_name:'オンワードHD'},{code:'556A',company_name:'犬猫生活'}];
 assert.deepEqual(parseHoldings('８０１６,556a\n8016 9999',entries),{matches:[{code:'8016',name:'オンワードHD'},{code:'556A',name:'犬猫生活'}],unknown:['9999']});
 assert.equal(parseHoldings('オンワードＨＤ、犬猫生活',entries).matches.length,2);
 assert.deepEqual(cleanAlertDays(null),[0,1,2,3]);assert.deepEqual(cleanAlertDays([3,3,4,-1,'2']),[3]);
});
