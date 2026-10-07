import {test} from 'node:test';
import assert from 'node:assert/strict';
import {initSearchRadius} from '../search-radius.js';

function setup(saved = {}) {
  const select = {value:'', options:[], ownerDocument:{createElement:()=>({})}, replaceChildren(...options){this.options=options;}};
  const store = {...saved};
  const controller = initSearchRadius(select, {read:key=>store[key], write:(key,value)=>{store[key]=value;}});
  return {select,store,controller};
}

test('shared range restores separate dining and hotel selections through tab switches and reloads', () => {
  const {select,store,controller} = setup({'yutai-radius':'30000'});
  controller.setSection('dining');
  assert.equal(select.value,'30000');
  assert.deepEqual(select.options.map(o=>o.value),['1000','3000','5000','10000','30000']);
  controller.setSection('hotel');
  assert.equal(select.value,'all');
  assert.deepEqual(select.options.map(o=>o.value),['100000','500000','1000000','1500000','all']);
  select.value='1500000'; controller.remember();
  controller.setSection('dining'); assert.equal(select.value,'30000');
  controller.setSection('hotel'); assert.equal(select.value,'1500000');
  assert.equal(controller.value('hotel'),1500000);
  const reloaded=setup(store); reloaded.controller.setSection('hotel');
  assert.equal(reloaded.select.value,'1500000');
  assert.equal(store['yutai-radius'],'30000');
});

test('invalid saved ranges fall back independently and nationwide remains a string', () => {
  const {select,controller}=setup({'yutai-radius':'all','yutai-hotel-radius':'30000'});
  controller.setSection('dining'); assert.equal(select.value,'3000');
  controller.setSection('hotel'); assert.equal(select.value,'all');
  assert.equal(controller.value('hotel'),'all');
});
