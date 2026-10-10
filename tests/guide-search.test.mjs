import assert from 'node:assert/strict';
import {test} from 'node:test';
import {guideSearchSelection} from '../guide-search.js';
const companies=[{id:'sample',status:'public'},{id:'hidden',status:'development'}];
test('guide links preserve exact Japanese brand and only accept published issuers',()=>{
  assert.deepEqual(guideSearchSelection('?issuer=sample&brand=%E5%92%8C%E9%A3%9F',companies),{section:'dining',feature:'',issuer:'sample',brand:'和食'});
  assert.equal(guideSearchSelection('?issuer=hidden&brand=test',companies).issuer,'');
  assert.equal(guideSearchSelection('?issuer=unknown&brand=test',companies).brand,'');
});
test('hotel links select a voucher; hostile or missing IDs do not activate hotel mode',()=>{
  assert.deepEqual(guideSearchSelection('?section=hotel&feature=vision-hotels',companies),{section:'hotel',feature:'vision-hotels',issuer:'',brand:''});
  assert.equal(guideSearchSelection('?section=hotel&feature=%3Cscript%3E',companies).section,'dining');
});
