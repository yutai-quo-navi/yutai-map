import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {validateFeature, visibleFeatures, featureStores, featureSearchResults, featureRadiusOptions, loadFeatureData, featureDistanceLabel} from '../special-features.js';
import {nearestDeadline, voucherEntriesFromLedger} from '../expiry.js';

const ended = JSON.parse(readFileSync(new URL('../data/features/index.json', import.meta.url))).features[0];
const draft = {...ended, status:'draft'};
const live = () => ({...draft, status:'public', sourceUrl:'https://example.com/official',
  checkedOn:'2026-07-01', validFrom:'2026-07-01', validThrough:'2026-09-30',
  stores:[{...draft.stores[0], verified:true, lat:35.71, lng:139.80}]});

test('all hotel vouchers share a range and merge results by distance while retaining voucher identity', () => {
  const features=[{id:'a',stores:[{id:'far',lat:43.3,lng:141.35}]}, {id:'b',stores:[{id:'near',lat:43.061,lng:141.35}]}];
  const origin={lat:43.06,lng:141.35};
  const all=featureSearchResults(features,origin,()=> 'all');
  assert.deepEqual(all.map(match=>match.store.id),['near','far']);
  assert.deepEqual(all.map(match=>match.feature.id),['b','a']);
  assert.deepEqual(featureSearchResults(features,origin,()=>10000).map(match=>match.store.id),['near']);
});

test('manual feature stays hidden after expiry; scheduled feature needs a verified snapshot', async () => {
  const data = JSON.parse(readFileSync(new URL('../data/features/index.json', import.meta.url)));
  validateFeature(draft);
  assert.equal(draft.stores.length, 13);
  assert.equal(visibleFeatures([draft], '2026-10-07').length, 0);
  const remote = {...live(), ...data.features[1], stores:live().stores, checkedOn:'2026-10-07'};
  validateFeature(remote);
  assert.equal(visibleFeatures([draft, remote], '2026-10-07').length, 1);
  assert.equal(visibleFeatures([draft, remote], '2026-10-07', true).length, 2);
  const dining = data.features.filter(feature => !feature.section || feature.section === 'dining');
  const loaded = await loadFeatureData(dining, async () => new Response(JSON.stringify({id:remote.id, stores:remote.stores, checkedOn:remote.checkedOn})));
  assert.equal(loaded.length, 1);
  const warned = console.warn; console.warn = () => {};
  try {
    assert.equal((await loadFeatureData(data.features, async () => new Response('', {status:503}))).length, 1);
    assert.equal((await loadFeatureData(data.features, async () => new Response(JSON.stringify({id:'wrong'})))).length, 1);
  } finally { console.warn = warned; }
});

test('hotel voucher deadlines match their own voucher type and never the lunch coupon', () => {
  const hotels = JSON.parse(readFileSync(new URL('../data/features/index.json',import.meta.url))).features.filter(feature=>feature.section==='hotel');
  assert.equal(hotels.length,3);
  const entries = voucherEntriesFromLedger(JSON.parse(readFileSync(new URL('../data/expiry.json',import.meta.url))).entries);
  const now = new Date('2026-10-07T03:00:00Z');
  for (const hotel of hotels) {
    const deadline=nearestDeadline(entries,hotel.issuer.id,now,hotel.deadlineBenefitPattern);
    assert.equal(deadline.date,hotel.issuer.id === 'daiwa-house' ? '2027-06-30' : '2027-07-31');
    assert.equal(deadline.benefit,hotel.voucherName);
    assert.equal(nearestDeadline([{issuer:'kyoritsu',status:'confirmed',date:'2026-10-31',benefit:'株主お食事（ランチ）券'}],hotel.issuer.id,now,hotel.deadlineBenefitPattern),null);
  }
});
test('publication requires year-specific dates, verified coordinates and a safe source', () => {
  assert.throws(() => validateFeature({...draft, status:'public'}));
  const feature = live(); validateFeature(feature);
  for (const changes of [{sourceUrl:'javascript:alert(1)'}, {validThrough:'2026-09-31'},
    {validFrom:'2027-07-01'}, {checkedOn:null}, {updateMode:'unknown'}]) {
    assert.throws(() => validateFeature({...feature, ...changes}));
  }
  assert.equal(visibleFeatures([feature], '2026-09-30').length, 1);
  assert.equal(visibleFeatures([feature], '2026-10-01').length, 0);
});
test('Sapporo includes Tokyo and Kobe beyond normal radius and sorts nearby first', () => {
  const feature = {...draft, stores:[
    {...draft.stores[7], lat:34.68, lng:135.18},
    {...draft.stores[0], lat:35.71, lng:139.80}
  ]};
  const result = featureStores(feature, {lat:43.06, lng:141.35});
  assert.equal(result.length, 2);
  assert.equal(result[0].id, draft.stores[0].id);
  assert.ok(result[0].distance > 10_000);
  assert.deepEqual(featureStores(draft, null).map(s => s.id), draft.stores.map(s => s.id));
});
test('multiple features share issuer voucher countdown, independently of lunch dates', () => {
  const features = [live(), {...live(), id:'kyoritsu-other', validThrough:'2026-08-31'}];
  const entries = [{issuer:'kyoritsu', date:'2026-09-30', status:'confirmed', issue:'test voucher'}];
  for (const feature of features) {
    const deadline = nearestDeadline(entries, feature.issuer.id, new Date('2026-08-01T03:00:00Z'));
    assert.equal(deadline.days, 60);
    assert.equal(deadline.date, '2026-09-30');
  }
});
test('100km feature keeps nearby stores without inheriting 3000km or normal radius', () => {
  const store = draft.stores[0];
  const feature = {...draft, radiusMeters:100_000, stores:[
    {...store, id:'near', lat:35.75, lng:139.8},
    {...store, id:'far', lat:34.68, lng:135.18}
  ]};
  assert.deepEqual(featureStores(feature,{lat:35.71,lng:139.8}).map(s=>s.id), ['near']);
  assert.equal(featureStores({...feature,radiusMeters:3_000_000},{lat:35.71,lng:139.8}).length, 2);
  assert.throws(()=>validateFeature({...feature,radiusMeters:-1}));
  assert.throws(()=>validateFeature({...feature,radiusMeters:Infinity}));
});
test('each feature has its own dropdown choices and validates its default', () => {
  const features = JSON.parse(readFileSync(new URL('../data/features/index.json', import.meta.url))).features;
  assert.deepEqual(featureRadiusOptions(features[0]), ['all',500_000,1_000_000,1_500_000]);
  assert.deepEqual(featureRadiusOptions(features[1]), ['all',100_000,500_000,1_000_000]);
  assert.throws(()=>validateFeature({...features[1],radiusMeters:400_000}));
  assert.throws(()=>validateFeature({...features[1],radiusOptionsMeters:[100_000,100_000]}));
});

test('lunch deadline excludes unrelated Kyoritsu discount coupons', () => {
  const entries = [
    {issuer:'kyoritsu', date:'2026-08-31', status:'confirmed', benefit:'株主優待割引券'},
    {issuer:'kyoritsu', date:'2026-09-30', status:'confirmed', benefit:'株主お食事（ランチ）券'}
  ];
  const now = new Date('2026-08-01T03:00:00Z');
  assert.equal(nearestDeadline(entries,'kyoritsu',now,draft.deadlineBenefitPattern).date,'2026-09-30');
  assert.equal(nearestDeadline(entries,'kyoritsu',now).date,'2026-09-30');
});

test('feature deadlines connect to the editable ledger and ignore booking or unconfirmed dates', () => {
  const row = {id:'3418-current',issuer_id:'balnibarbi',code:'3418',company_name:'バルニバービ',
    benefit_name:'電子優待券',expiry_type:'利用期限',status:'confirmed',expiry_date:'2026-11-30',issue:'2026年発行分'};
  const entries = voucherEntriesFromLedger([row,{...row,id:'booking',expiry_type:'予約期限'},
    {...row,id:'unconfirmed',status:'checking'},{...row,id:'month-only',expiry_date:''}]);
  assert.equal(entries.length, 1);
  const deadline = nearestDeadline(entries,'balnibarbi',new Date('2026-10-07T03:00:00Z'));
  assert.equal(deadline.date,'2026-11-30');
  assert.equal(deadline.days,54);
});

test('ended Kyoritsu feature remains visible with its 13 historical stores, while drafts remain hidden', () => {
  validateFeature(ended);
  assert.equal(ended.status, 'ended');
  assert.equal(visibleFeatures([ended], '2026-10-07').length, 1);
  assert.equal(visibleFeatures([ended], '2026-09-30').length, 0);
  assert.equal(ended.stores.length, 13);
  assert.throws(() => validateFeature({...ended, validThrough:null}));
  assert.throws(() => validateFeature({...ended, sourceUrl:null}));
});

test('short distances retain metres and unknown positions never count as inside a radius', () => {
  assert.equal(featureDistanceLabel(380), '380m');
  assert.equal(featureDistanceLabel(1234), '1.2km');
  const feature={...draft, radiusMeters:100000, stores:[{...draft.stores[0],id:'unknown',lat:null,lng:null}]};
  assert.equal(featureStores(feature,{lat:35.68,lng:139.76}).length,0);
});

test('all 13 historical lunch locations calculate distance even after voucher expiry', () => {
  const origin={lat:43.06,lng:141.35};
  assert.equal(ended.stores.filter(store=>Number.isFinite(store.lat)&&Number.isFinite(store.lng)).length,13);
  assert.equal(featureStores({...ended,radiusMeters:500000},origin).length,0);
  assert.equal(featureStores({...ended,radiusMeters:1000000},origin).length,12);
  const all=featureStores({...ended,radiusMeters:4000000},origin);
  assert.equal(all.length,13);
  assert.ok(all.every(store=>store.distance>10000));
  assert.equal(all.at(-1).id,'kyoritsu-lunch-08');
});

 test('nationwide default includes every store beyond 4000km and still sorts by distance', () => {
  const config = JSON.parse(readFileSync(new URL('../data/features/index.json', import.meta.url))).features;
  assert.ok(config.every(feature => feature.radiusMeters === 'all'));
  const feature = {...draft, stores:[
    {...draft.stores[0], id:'far', lat:-33.87, lng:151.21},
    {...draft.stores[0], id:'near', lat:43.06, lng:141.35},
    {...draft.stores[0], id:'unknown', lat:null, lng:null}
  ]};
  const result = featureStores(feature, {lat:43.06,lng:141.35});
  assert.deepEqual(result.map(store => store.id), ['near','far','unknown']);
  assert.ok(result[1].distance > 4000000);
  assert.equal(featureStores(feature, null).length, 3);
  assert.deepEqual(featureStores({...feature,radiusMeters:100000}, {lat:43.06,lng:141.35}).map(store=>store.id), ['near']);
  assert.throws(() => validateFeature({...draft, radiusMeters:'anything'}));
});
