import {test} from 'node:test';
import assert from 'node:assert/strict';
import {upcomingExpiries,expiryGroup,cleanExpirySettings,dueExpiryAlerts} from '../expiry-search.js';
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
