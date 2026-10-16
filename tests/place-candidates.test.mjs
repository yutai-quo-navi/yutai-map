import test from 'node:test';
import assert from 'node:assert/strict';
import {placeCandidates} from '../place-candidates.js';
const station={name:'東京駅',address:'東京都千代田区丸の内一丁目',lat:35.677688540995526,lng:139.7652361004884};
test('Tokyo Station never selects upstream vocabulary falsely classified as a prefecture',()=>{
 const data={vocabulary:[{type:'place',label:'東京駅',prefecture:'東京駅',center:[139.7331,35.67053]}],suggestions:[station]};
 assert.deepEqual(placeCandidates(data,'東京駅'),[{label:station.name,sub:station.address,lat:station.lat,lng:station.lng}]);
});
test('exact facility takes priority over a real regional centroid and partial business names',()=>{
 const data={vocabulary:[{type:'place',label:'東京駅',prefecture:'東京都',center:[139.7331,35.67053]}],suggestions:[{...station,name:'東京駅食堂'},station]};
 assert.equal(placeCandidates(data,' 東京駅 ')[0].lat,station.lat);
});
test('administrative place search remains supported without facility results',()=>{
 assert.equal(placeCandidates({vocabulary:[{type:'place',label:'札幌市',prefecture:'北海道',city:'札幌市',center:[141.3545,43.0618]}]},'札幌市')[0].label,'札幌市');
});
test('missing, non-finite or foreign coordinates cannot establish a search origin',()=>{
 assert.deepEqual(placeCandidates({suggestions:[{name:'x',lat:null,lng:null},{name:'x',lat:0,lng:139},{name:'x',lat:35,lng:Infinity}],vocabulary:[{type:'place',label:'x',prefecture:'東京都',center:[]}]},'x'),[]);
});
