import {test} from 'node:test';
import assert from 'node:assert/strict';
import {requestCurrentPosition} from '../geolocation.js';

test('normal accuracy works without a retry',()=>{
  let calls=0, result;
  const pos={coords:{latitude:35,longitude:139}};
  requestCurrentPosition({getCurrentPosition(ok,fail,options){calls++;assert.equal(options.enableHighAccuracy,false);ok(pos);}},p=>result=p,()=>assert.fail());
  assert.equal(calls,1);assert.equal(result,pos);
});
for(const code of [2,3]) test(`error ${code} retries once with fresh high accuracy`,()=>{
  let calls=0,retries=0,errors=0;
  requestCurrentPosition({getCurrentPosition(ok,fail,options){calls++;assert.equal(options.enableHighAccuracy,calls===2);if(calls===2)assert.equal(options.maximumAge,0);fail({code});}},()=>assert.fail(),()=>errors++,()=>retries++);
  assert.equal(calls,2);assert.equal(retries,1);assert.equal(errors,1);
});
test('permission rejection does not retry',()=>{
  let calls=0,errors=0;
  requestCurrentPosition({getCurrentPosition(ok,fail){calls++;fail({code:1});}},()=>assert.fail(),()=>errors++);
  assert.equal(calls,1);assert.equal(errors,1);
});
test('recovered coordinates reach success only once',()=>{
  let calls=0,success=0;
  requestCurrentPosition({getCurrentPosition(ok,fail){if(++calls===1)fail({code:2});else ok({coords:{latitude:35,longitude:139}});}},()=>success++,()=>assert.fail());
  assert.equal(calls,2);assert.equal(success,1);
});
