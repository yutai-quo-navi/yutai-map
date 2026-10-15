import {test} from 'node:test';
import assert from 'node:assert/strict';
import worker from '../cloudflare/worker/src/index.js';

const origin='https://yutai-quo-navi.github.io';
const stores=Array.from({length:77},(_,i)=>({
  issuer_id:'company1',store_id:String(i).padStart(4,'0'),
  name:'店'+i,lat:35.68,lng:139.76,category:'restaurant',
  rounded_distance:Math.floor(i/2),exact_distance:Math.floor(i/2),
  __all_count:77,__restaurant_count:77,
  __cafe_count:0,__bakery_count:0,__foodcourt_count:0,__other_count:0
}));
const count=()=>({all:77,restaurant:77,cafe:0,bakery:0,foodcourt:0,other:0});
function fixture(){
  const queries=[],upstream=[];
  const env={
    API_RATE_LIMITER:{limit:async()=>({success:true})},
    SEARCH_RATE_LIMITER:{limit:async()=>({success:true})},
    SEARCH_COUNTER:{idFromName:value=>value,get:()=>({fetch:async()=>Response.json({success:true})})},
    DB:{prepare(sql){return {bind(...args){this.args=args;return this;},async all(){
      queries.push({sql,args:this.args||[]});
      if(sql.includes('FROM issuer_stats'))return {results:[]};
      assert.match(sql,/WITH candidates AS/);
      assert.match(sql,/LIMIT 30/);
      const cursorFilter=sql.includes('rounded_distance > ?');
      let matching=stores;
      if(cursorFilter){
        const [distance,,issuer,,store]=this.args.slice(-5);
        matching=stores.filter(x=>x.rounded_distance>distance ||
          (x.rounded_distance===distance &&
            (x.issuer_id>issuer || (x.issuer_id===issuer && x.store_id>store))));
      }
      matching=matching.slice(0,30);
      if(!matching.length){
        return {results:[{store_id:null,__all_count:77,__restaurant_count:77,
          __cafe_count:0,__bakery_count:0,__foodcourt_count:0,__other_count:0}]};
      }
      return {results:matching};
    }};}}
  };
  const url=(cursor,additional='')=>{
    const q=new URLSearchParams({lat:'35.6812',lng:'139.7671',radius:'30000',
      issuers:'company1',...cursor?{cursor}:{},...additional?{limit:additional}:{}});
    return new Request('https://worker.example.com/v1/stores/search?'+q,{headers:{Origin:origin,'CF-Connecting-IP':'192.0.2.42'}});
  };
  return {env,queries,upstream,url};
}

test('pagination returns 30, 30, 17, then stops: no DB page read before explicit HTTP request',async()=>{
  const {env,queries,url}=fixture();
  let cursor=null;
  const ids=[];
  for(const expected of [30,30,17]){
    const priorQueries=queries.length;
    // Merely holding a cursor is not a request to load the next page.
    assert.equal(queries.length,priorQueries);
    const res=await worker.fetch(url(cursor),env);
    assert.equal(res.status,200);
    const data=await res.json();
    assert.equal(data.results.length,expected);
    assert.deepEqual(data.category_counts,count());
    ids.push(...data.results.map(x=>x.store_id));
    cursor=data.next_cursor;
    assert.equal(Boolean(cursor),expected===30);
    assert.equal(queries.filter(x=>x.sql.includes('WITH candidates AS')).length,ids.length===30?1:ids.length===60?2:3);
  }
  assert.equal(ids.length,77);
  assert.equal(new Set(ids).size,77,'no duplicates across pages or tied distances');
  assert.deepEqual(ids,stores.map(x=>x.store_id),'pages preserve distance and stable tie order');
  assert.equal(cursor,null);
});

test('requested limit 9000 can never transfer more than thirty stores',async()=>{
  const {env,queries,url}=fixture();
  const res=await worker.fetch(url(null,'9000'),env);
  assert.equal(res.status,200);
  assert.equal((await res.json()).results.length,30);
  assert.ok(queries.every(x=>!x.sql.includes('LIMIT 9000')));
});

test('invalid paging cursor is rejected before hitting database',async()=>{
  const {env,queries,url}=fixture();
  for(const cursor of ['9000','[30000,"company1"]','[-4,"company1","a"]','[3,"bad issuer","a"]']){
    const res=await worker.fetch(url(cursor),env);
    assert.equal(res.status,400);
  }
  assert.equal(queries.length,0);
});
