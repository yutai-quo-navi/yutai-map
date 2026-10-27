import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {searchScopeLabel,coverageMessage,emptySearchMessage,validateSearchResponse} from '../dining-search-state.js';

test('66 selected companies cannot be described as an unfiltered search when a brand is active',()=>{
  assert.equal(searchScopeLabel(66,{name:'喫茶室ルノアール'}),'66社選択・検索対象は「喫茶室ルノアール」のみ');
  assert.equal(searchScopeLabel(66,null),'66社選択・全ブランド');
  assert.match(emptySearchMessage({brand:{name:'喫茶室ルノアール'},incomplete:true}),/喫茶室ルノアール.*登録済み店舗は0件/);
});
test('normal zero, missing coordinates and unknown verification have distinct honest messages',()=>{
  assert.equal(coverageMessage({complete:true}), '');
  assert.equal(emptySearchMessage({}), '条件に一致する対象店舗は0件です。');
  assert.match(emptySearchMessage({coverage:{unresolved_stores:3},incomplete:true}),/座標未補完/);
  assert.match(coverageMessage({unresolved_stores:3}),/全国.*3件.*この検索範囲内の件数ではありません/);
  assert.match(coverageMessage({unverified_issuers:['renoir']}),/照合状況が未確認/);
  assert.doesNotMatch(coverageMessage({unverified_issuers:['renoir']}),/座標未補完|未完了/);
  assert.match(coverageMessage(null,true),/整備・更新状況を確認できません/);
});
const zero=()=>({results:[],count:0,category_counts:{all:0,restaurant:0,cafe:0,bakery:0,foodcourt:0,other:0},incomplete:false,has_more:false,next_cursor:null});
test('HTTP 200 errors and malformed records fail rather than becoming a normal zero',()=>{
  assert.deepEqual(validateSearchResponse(zero(),['a']),zero());
  for(const value of [{},{error:'search_index_unavailable'},{...zero(),count:1},{...zero(),category_counts:{}},{...zero(),has_more:true}]) assert.throws(()=>validateSearchResponse(value,['a']));
  const row={issuer_id:'a',store_id:'1',name:'test',lat:42.82,lng:141.65,distance:10};
  const good={...zero(),results:[row],count:1,category_counts:{...zero().category_counts,all:1,restaurant:1}};
  assert.equal(validateSearchResponse(good,['a']),good);
  for(const change of [{issuer_id:'b'},{lat:null},{distance:-1}]) assert.throws(()=>validateSearchResponse({...good,results:[{...row,...change}]},['a']));
});
const source=fs.readFileSync(new URL('../app.js',import.meta.url),'utf8');
function code(name){const start=source.indexOf('function '+name+'(');return source.slice(start,source.indexOf('\n}',start)+2);}
test('choosing a brand keeps its name visible; clearing typed text clears the actual filter',()=>{
  const brand={issuer_id:'renoir',name:'喫茶室ルノアール'};
  const ctx=vm.createContext({brandCatalog:[brand],activeBrand:'',selected:new Set(['renoir']),els:{brandSearch:{value:''}},brandReadings:{},normalizeBrandQuery:s=>s,brandKey:b=>JSON.stringify([b.issuer_id,b.name]),writeSetting(){},renderBrandOptions(){},hideBrandSuggestions(){},resetCategoryFilter(){},invalidateDiningSearch(){},brandCandidateLimit:12});
  vm.runInContext(code('chooseBrand')+'\n'+code('syncTypedBrand'),ctx);
  ctx.chooseBrand(JSON.stringify(['renoir',brand.name]));
  assert.equal(ctx.els.brandSearch.value,brand.name);
  assert.ok(ctx.activeBrand);
  ctx.els.brandSearch.value='';ctx.syncTypedBrand();assert.equal(ctx.activeBrand,'');
});
test('company picker apply clears a previous brand condition before requesting a rerun',()=>{
  const start=source.indexOf("els.pickerApply.addEventListener('click', () => {");
  const body=source.slice(start,source.indexOf('\n  });',start));
  const ctx=vm.createContext({selected:new Set(['renoir']),draftSelection:new Set(['mcd','mos']),activeBrand:'saved-renoir',els:{brandSearch:{value:'喫茶室ルノアール'},picker:{close(){}}},editingFromResults:true,lastPosition:{lat:42.82,lng:141.65},writeSetting(){},resetCategoryFilter(){},persistSelection(){},renderChips(){},renderBrandOptions(){},invalidateDiningSearch(){},rerunFromResults(){assert.equal(ctx.activeBrand,'');assert.deepEqual([...ctx.selected],['mcd','mos']);}});
  vm.runInContext(body.slice(body.indexOf('{')+1),ctx);
  assert.equal(ctx.activeBrand,'');assert.equal(ctx.els.brandSearch.value,'');
});
