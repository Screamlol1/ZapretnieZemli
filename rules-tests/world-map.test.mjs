import assert from 'node:assert/strict';
import {center,vertices,adjacent,routeProblem,W} from '../public/world-hex.js';
const near=(a,b)=>Math.abs(a-b)<1e-8;
let shared=0;
for(let y=0;y<16;y++)for(let x=0;x<24;x++){
 const p={x,y},neighbors=[];
 for(let dy=-1;dy<=1;dy++)for(let dx=-1;dx<=1;dx++){
  const q={x:x+dx,y:y+dy};if(q.x<0||q.x>=24||q.y<0||q.y>=16||!adjacent(p,q))continue;
  neighbors.push(q);const a=center(p),b=center(q);
  assert(near(Math.hypot(a.x-b.x,a.y-b.y),W),'Centers are one hex width apart');
  const common=vertices(p).filter(v=>vertices(q).some(w=>near(v[0],w[0])&&near(v[1],w[1])));
  assert.equal(common.length,2,'Every adjacent pair shares an entire edge, without gaps');shared++;
 }
 if(x>0&&x<23&&y>0&&y<15)assert.equal(neighbors.length,6);
}
assert(adjacent({x:3,y:1},{x:4,y:0}));assert(!adjacent({x:3,y:1},{x:2,y:2}));
assert.equal(routeProblem({x:0,y:0},[{x:1,y:0},{x:2,y:0}],{}),null);
assert(routeProblem({x:0,y:0},[{x:1,y:0},{x:2,y:0},{x:3,y:0}],{}));
assert.equal(routeProblem({x:0,y:0},[{x:1,y:0},{x:2,y:0},{x:3,y:0}],{},true),null);
assert(routeProblem({x:0,y:0},[{x:1,y:0},{x:2,y:0}],{'2,0':{terrain:'mountain'}}));
assert(routeProblem({x:0,y:0},[{x:1,y:0}],{'1,0':{terrain:'water'}}));
assert(routeProblem({x:0,y:0},[{x:1,y:0},{x:0,y:0}],{}));
assert(routeProblem({x:0,y:0},[{x:2,y:0}],{}));
console.log(`World map: ${shared} shared edges, six neighbors, movement limits OK`);
