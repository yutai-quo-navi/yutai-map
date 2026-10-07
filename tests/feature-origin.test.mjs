import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

function setup({place=false, denied=false} = {}) {
  const calls={geo:0, search:0, refresh:0};
  const context=vm.createContext({
    lastPosition:null,lastCenterLabel:'現在地',
    specialFeatures:{refresh(){calls.refresh++;}},
    els:{placeSearchPanel:{hidden:!place},placeInput:{value:'福岡',focus(){}},placeSuggestions:{hidden:true},locate:{disabled:false}},
    navigator:{geolocation:{getCurrentPosition(success,failure){calls.geo++;denied ? failure({code:1}) : success({coords:{latitude:43.06,longitude:141.35}});}}},
    setStatus(){},showError(){},normalize:value=>value,console,
    SUGGEST_API:'https://api.example.com/suggest',URLSearchParams,
    fetch:async()=>({ok:true,json:async()=>({vocabulary:[{type:'place',label:'福岡',center:[130.4,33.59]}]})}),
    searchNearby(){calls.search++;}
  });
  const source=readFileSync(new URL('../app.js',import.meta.url),'utf8');
  vm.runInContext(source.slice(source.indexOf('async function submitPlaceSearch('),source.indexOf('async function searchNearby(')),context);
  return {context,calls};
}
test('feature alone obtains current location once without invoking ordinary issuer search',async()=>{
  const {context,calls}=setup();
  const pos=await context.ensureFeatureOrigin();
  assert.equal(pos.lat,43.06);assert.equal(pos.lng,141.35);
  assert.equal(calls.geo,1);assert.equal(calls.search,0);
  assert.equal(context.els.locate.disabled,false);
  await context.ensureFeatureOrigin();assert.equal(calls.geo,1);
});
test('feature honors a typed place and replaces a previous current location through OpenPOI suggestions',async()=>{
  const {context,calls}=setup({place:true});
  context.lastPosition={lat:43.06,lng:141.35};
  const pos=await context.ensureFeatureOrigin();
  assert.equal(pos.lat,33.59);assert.equal(pos.lng,130.4);
  assert.equal(context.lastCenterLabel,'福岡');
  assert.equal(calls.geo,0);assert.equal(calls.search,0);
});
test('denied current location leaves distance origin unset and releases the button',async()=>{
  const {context,calls}=setup({denied:true});
  assert.equal(await context.ensureFeatureOrigin(),null);
  assert.equal(context.lastPosition,null);assert.equal(calls.search,0);
  assert.equal(context.els.locate.disabled,false);
});
test('ordinary current-location button continues to invoke issuer search',async()=>{
  const {context,calls}=setup();
  await context.requestLocation();
  assert.equal(calls.search,1);assert.equal(calls.geo,1);
});
