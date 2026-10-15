import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createSmoothNavigator} from '../smooth-scroll.js';

function setup({reduced=false, targetTop=3000} = {}) {
  const frames=new Map(), listeners=new Map(), coordinates=[];
  let next=1;
  const record=(type,handler)=>{
    if(!listeners.has(type)) listeners.set(type,new Set());
    listeners.get(type).add(handler);
  };
  const remove=(type,handler)=>listeners.get(type)?.delete(handler);
  const win={
    scrollY:0, innerHeight:800,
    requestAnimationFrame(handler){const id=next++;frames.set(id,handler);return id;},
    cancelAnimationFrame(id){frames.delete(id);},
    getComputedStyle(){return {scrollMarginTop:'20px'};},
    matchMedia(){return {matches:reduced};},
    scrollTo(x,y){this.scrollY=y;coordinates.push(y);},
    addEventListener:record,removeEventListener:remove
  };
  const doc={
    hidden:false,
    documentElement:{scrollHeight:10000},
    body:{scrollHeight:10000},
    addEventListener:record,removeEventListener:remove
  };
  const target={getBoundingClientRect(){return {top:targetTop-win.scrollY};}};
  function frameAt(timestamp){
    const pending=[...frames.values()];
    frames.clear();
    pending.forEach(callback=>callback(timestamp));
  }
  function event(type){[...(listeners.get(type)||[])].forEach(handler=>handler());}
  return {win,doc,target,frames,coordinates,frameAt,event};
}

test('long result navigation accelerates gently and comes to a soft stop',()=>{
  const ctx=setup();
  const nav=createSmoothNavigator(ctx.win,ctx.doc);
  assert.equal(nav.scrollTo(ctx.target),true);
  assert.equal(ctx.frames.size,1);
  ctx.frameAt(0);
  assert.equal(ctx.win.scrollY,0);
  ctx.frameAt(350);
  const quarter=ctx.win.scrollY;
  ctx.frameAt(700);
  const middle=ctx.win.scrollY;
  ctx.frameAt(1050);
  const third=ctx.win.scrollY;
  ctx.frameAt(1400);
  assert.ok(quarter>0 && quarter<middle);
  assert.ok(middle<third && third<2980);
  assert.ok(Math.abs(ctx.win.scrollY-2980)<0.01);
  assert.equal(ctx.frames.size,0);
  // Start/end quarters cover substantially less distance than the middle quarters.
  assert.ok(quarter<2980/4);
  assert.ok(2980-third<2980/4);
});

test('touch or wheel interrupts animation rather than fighting the user',()=>{
  for(const type of ['touchstart','wheel','keydown','pointerdown']){
    const ctx=setup(), nav=createSmoothNavigator(ctx.win,ctx.doc);
    nav.scrollTo(ctx.target);
    ctx.frameAt(0);
    ctx.frameAt(350);
    const before=ctx.win.scrollY;
    ctx.event(type);
    assert.equal(ctx.frames.size,0,type);
    ctx.frameAt(800);
    assert.equal(ctx.win.scrollY,before,type);
  }
});

test('reduced motion navigates immediately without animation',()=>{
  const ctx=setup({reduced:true});
  const nav=createSmoothNavigator(ctx.win,ctx.doc);
  assert.equal(nav.scrollTo(ctx.target),true);
  assert.equal(ctx.win.scrollY,2980);
  assert.equal(ctx.frames.size,0);
});

test('hidden document does not begin scrolling and switching away cancels it',()=>{
  const ctx=setup(), nav=createSmoothNavigator(ctx.win,ctx.doc);
  ctx.doc.hidden=true;
  assert.equal(nav.scrollTo(ctx.target),false);
  assert.equal(ctx.frames.size,0);
  ctx.doc.hidden=false;
  nav.scrollTo(ctx.target);
  ctx.frameAt(0);
  ctx.doc.hidden=true;
  ctx.event('visibilitychange');
  assert.equal(ctx.frames.size,0);
});

test('nearby target avoids needless movement',()=>{
  const ctx=setup({targetTop:23}), nav=createSmoothNavigator(ctx.win,ctx.doc);
  assert.equal(nav.scrollTo(ctx.target),false);
  assert.equal(ctx.frames.size,0);
});
