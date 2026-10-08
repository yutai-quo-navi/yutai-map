import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compareBenefitPriority} from '../expiry.js';

test('deadlines rank by urgency, equal deadlines by count, expired benefits last', () => {
  const items = [
    {id:'expired', days:-1, count:10000},
    {id:'undated-small', count:10},
    {id:'later', days:60, count:1000},
    {id:'near-small', days:20, count:10},
    {id:'near-large', days:20, count:100},
    {id:'today', days:0, count:1},
    {id:'ended', ended:true, count:20000},
    {id:'undated-large', count:100}
  ];
  assert.deepEqual(items.sort(compareBenefitPriority).map(item=>item.id),
    ['today','near-large','near-small','later','undated-large','undated-small','ended','expired']);
});

test('count determines order when no deadline exists and ties remain stable', () => {
  const items = [{id:'small',count:1},{id:'a',count:86},{id:'b',count:86}];
  assert.deepEqual(items.sort(compareBenefitPriority).map(item=>item.id), ['a','b','small']);
});
