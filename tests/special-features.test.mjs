import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {validateFeature, visibleFeatures, featureStores} from '../special-features.js';
import {nearestDeadline} from '../expiry.js';

const draft = JSON.parse(readFileSync(new URL('../data/features/index.json', import.meta.url))).features[0];
const live = () => ({...draft, status:'public', sourceUrl:'https://example.com/official',
  checkedOn:'2026-07-01', validFrom:'2026-07-01', validThrough:'2026-09-30',
  stores:[{...draft.stores[0], verified:true, lat:35.71, lng:139.80}]});

test('all manual drafts validate but remain hidden without preview', () => {
  const data = JSON.parse(readFileSync(new URL('../data/features/index.json', import.meta.url)));
  data.features.forEach(validateFeature);
  assert.equal(draft.stores.length, 13);
  assert.equal(visibleFeatures(data.features, '2026-10-07').length, 0);
  assert.equal(visibleFeatures(data.features, '2026-10-07', true).length, 2);
});
test('publication requires year-specific dates, verified coordinates and a safe source', () => {
  assert.throws(() => validateFeature({...draft, status:'public'}));
  const feature = live(); validateFeature(feature);
  for (const changes of [{sourceUrl:'javascript:alert(1)'}, {validThrough:'2026-09-31'},
    {validFrom:'2027-07-01'}, {checkedOn:null}, {updateMode:'scheduled'}]) {
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
