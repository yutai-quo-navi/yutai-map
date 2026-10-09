import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

function setup({place=false, denied=false} = {}) {
  const calls={geo:0, search:0, refresh:0};
  const context=vm.createContext({
    lastPosition:null,lastCenterLabel:'現在地',
    specialFeatures:{refresh(){calls.refresh++;},invalidate(){calls.refresh++;}},
    els:{placeSearchPanel:{hidden:!place},placeInput:{value:'福岡',focus(){}},placeSuggestions:{hidden:true},locate:{disabled:false,setAttribute(){},removeAttribute(){}}},
    navigator:{geolocation:{getCurrentPosition(success,failure){calls.geo++;denied ? failure({code:1}) : success({coords:{latitude:43.06,longitude:141.35}});}}},
    setTimeout,clearTimeout,qs:()=>null,
    invalidateDiningSearch(){},setStatus(){},showError(){},normalize:value=>value,console,
    SUGGEST_API:'https://api.example.com/suggest',URLSearchParams,
    fetch:async()=>({ok:true,json:async()=>({vocabulary:[{type:'place',label:'福岡',center:[130.4,33.59]}]})}),
    searchNearby(){calls.search++;}
  });
  const source=readFileSync(new URL('../app.js',import.meta.url),'utf8');
  vm.runInContext(source.slice(source.indexOf('let searchFeedbackDepth ='),source.indexOf('let pendingSearch =')),context);
  vm.runInContext(source.slice(source.indexOf('async function submitPlaceSearch('),source.indexOf('async function searchNearby(')),context);
  return {context,calls};
}
test('current-location search runs only after an explicit request',async()=>{
  const {context,calls}=setup();
  assert.equal(calls.geo,0); assert.equal(calls.search,0);
  await context.requestLocation();
  assert.equal(context.lastPosition.lat,43.06); assert.equal(context.lastPosition.lng,141.35);
  assert.equal(calls.geo,1); assert.equal(calls.search,1);
});
test('explicit place submission resolves the typed place and searches',async()=>{
  const {context,calls}=setup({place:true});
  await context.submitPlaceSearch({preventDefault(){}});
  assert.equal(context.lastPosition.lat,33.59);
  assert.equal(context.lastCenterLabel,'福岡');
  assert.equal(calls.geo,0); assert.equal(calls.search,1);
});
test('denied current location leaves origin unset and releases the button',async()=>{
  const {context,calls}=setup({denied:true});
  assert.equal(await context.requestLocation(),null);
  assert.equal(context.lastPosition,null); assert.equal(calls.search,0);
  assert.equal(context.els.locate.disabled,false);
});
test('choosing a place suggestion only records the origin until search is pressed',async()=>{
  const {context,calls}=setup({place:true});
  context.applySearchOrigin({lat:33.59,lng:130.4},'福岡',false);
  assert.equal(calls.geo,0); assert.equal(calls.search,0);
  await context.submitPlaceSearch({preventDefault(){}});
  assert.equal(calls.search,1);
});
