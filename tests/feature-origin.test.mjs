import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {requestCurrentPosition} from '../geolocation.js';

function setup({place=false, denied=false} = {}) {
  const calls={geo:0, search:0, refresh:0};
  const context=vm.createContext({
    requestCurrentPosition,lastPosition:null,lastCenterLabel:'現在地',
    specialFeatures:{refresh(){calls.refresh++;},invalidate(){calls.refresh++;}},
    smoothNavigator:{stop(){},scrollTo(){}},
    els:{placeSearchPanel:{hidden:!place},placeInput:{value:'福岡',focus(){}},placeSuggestions:{hidden:true},locate:{disabled:false,textContent:'現在地から探す',setAttribute(){},removeAttribute(){}},
      cancelSearch:{hidden:true},diningActions:{hidden:true},hotelActions:{hidden:true},radius:{value:'3000',options:[]}},
    navigator:{geolocation:{getCurrentPosition(success,failure){calls.geo++;denied ? failure({code:1}) : success({coords:{latitude:43.06,longitude:141.35}});}}},
    setTimeout,clearTimeout,AbortController,qs:()=>null,searching:false,
    invalidateDiningSearch(){},setStatus(){},showError(){},normalize:value=>value,console,
    SUGGEST_API:'https://api.example.com/suggest',URLSearchParams,
    fetch:async()=>({ok:true,json:async()=>({vocabulary:[{type:'place',label:'福岡',center:[130.4,33.59]}]})}),
    searchNearby(){calls.search++;}
  });
  const source=readFileSync(new URL('../app.js',import.meta.url),'utf8');
  vm.runInContext(source.slice(source.indexOf('let searchFeedbackDepth ='),source.indexOf('let pendingSearch =')),context);
  vm.runInContext(source.slice(source.indexOf('let pendingSearch ='),source.indexOf('let lastResults =')),context);
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

test('cancel during a pending place request ignores its late response',async()=>{
  const {context,calls}=setup({place:true});
  let respond;
  context.fetch=()=>new Promise(resolve=>{respond=resolve;});
  const pending=context.submitPlaceSearch({preventDefault(){}});
  assert.equal(context.els.cancelSearch.hidden,false);
  context.cancelActiveSearch();
  assert.equal(context.els.locate.disabled,false);
  assert.equal(context.els.cancelSearch.hidden,true);
  respond({ok:true,json:async()=>({vocabulary:[{type:'place',label:'福岡',center:[130.4,33.59]}]})});
  await pending;
  assert.equal(calls.search,0);
  assert.equal(context.lastPosition,null);
});
test('cancel during geolocation ignores a delayed successful coordinate',async()=>{
  const {context,calls}=setup();
  let reportPosition;
  context.navigator.geolocation.getCurrentPosition=success=>{calls.geo++;reportPosition=success;};
  const pending=context.requestLocation();
  context.cancelActiveSearch();
  reportPosition({coords:{latitude:43.06,longitude:141.35}});
  await pending;
  assert.equal(calls.search,0);
  assert.equal(context.lastPosition,null);
  assert.equal(context.els.cancelSearch.hidden,true);
});
