import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
test('all public issuers use one index request without browser POI/catalog fallback',()=>{
 const source=fs.readFileSync(new URL('../app.js',import.meta.url),'utf8');
 assert.match(source,/const indexTargets = targets;/);
 assert.match(source,/queryIndexedStoreApi\(targets, pos, radius, operation.signal\)/);
 for(const old of ['queryOpenPOI','queryOfficialStoreDb','matchOfficialStore','function classify(','poiSearchGroups','https://api.openpoiapi.com/v1/search']) assert.ok(!source.includes(old),old);
 assert.ok(source.includes('https://api.openpoiapi.com/v1/suggest'));
 const manifest=JSON.parse(fs.readFileSync(new URL('../data/issuers/index.json',import.meta.url)));
 assert.equal(manifest.issuers.filter(x=>x.status==='public').length,44);
});
