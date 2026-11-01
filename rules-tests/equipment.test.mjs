import assert from 'node:assert/strict';
import {newBattle,attack,moveUnit,resolveLoad,validateBattle} from '../public/tools/battle-rules.js';
import {artifactHits,protection} from '../public/equipment-dice.js';
import {travelStatus} from '../public/travel-status.js';
const fixture=()=>{const b=newBattle();b.units=b.units.slice(0,2);b.units[0].team='A';b.units[1].team='B';b.phase='combat';b.round=1;b.order=b.units.map(u=>u.id);b.units[0].q=3;b.units[0].r=3;b.units[1].q=4;b.units[1].r=3;b.units[1].defense='none';b.units[1].armor=0;return b;};
assert.deepEqual([1,6,7,8,9,10,11,12].map(artifactHits),[0,1,1,2,2,3,3,4]);
{
 const b=fixture(),u=b.units[0],v=b.units[1];u.weapon='sword';u.weaponStats={name:'Артефакт',bonus:4,damage:3};u.gear=4;u.weaponArtifact=12;u.str=1;u.melee=0;
 attack(b,v.id,'slash',{},sides=>sides===12?12:2);assert.equal(v.str,0,'four artifact successes add three damage to base 3');validateBattle(b);
}
{
 const b=fixture(),u=b.units[0];u.weaponArtifact=8;const values=[];attack(b,b.units[1].id,'slash',{push:true},sides=>{values.push(sides);return sides===8?8:1;});assert.equal(values.filter(x=>x===8).length,1,'successful artifact is not rerolled');assert.equal(u.gear,0);
}
{
 const u={armor:3,armorSources:[{id:'body',current:2,maximum:2,artifact:0},{id:'head',current:1,maximum:1,artifact:0}]},values=[1,2,6];const r=protection(u,3,()=>values.shift());assert.equal(r.taken,2);assert.equal(u.armorSources[0].current,1);assert.equal(u.armorSources[1].current,1);
 const protectedUnit={armor:1,armorSources:[{id:'artifact',current:1,maximum:1,artifact:12}]};const blocked=protection(protectedUnit,4,n=>n===12?12:1);assert.equal(blocked.taken,0);assert.equal(protectedUnit.armor,1);
}
{
 const b=fixture(),u=b.units[0];b.units[1].q=10;u.overloaded=true;u.endure=0;moveUnit(b,u.id,3,4,false,()=>2);assert.equal(u.r,3);assert.equal(u.fast,0);assert.ok(u.pendingMove);const agi=u.agi;resolveLoad(b,true,()=>6);assert.equal(u.agi,agi-1);assert.equal(u.r,4);assert.equal(u.fast,0);assert.equal(u.pendingMove,undefined);validateBattle(b);
}
{
 const s={me:{role:'player',owner:'p'},characters:[{id:'hero',owner:'p',name:'Герой',kind:'pc'}],members:[],journey:{party:['hero'],plans:{},pending:[],pendingCount:0,phase:'planning',route:[],completed:{},cycleParticipants:[{owner:'p',name:'Игрок',complete:false},{owner:'gm',name:'Мастер',complete:false}]}};
 assert.equal(travelStatus(s).action,'plan');s.journey.plans.hero={job:'hike'};assert.equal(travelStatus(s).action,'wait');s.me={role:'gm',owner:'master'};assert.equal(travelStatus(s).action,'route');s.journey.route=[{x:1,y:0}];assert.equal(travelStatus(s).action,'ready');s.journey.pendingCount=1;assert.equal(travelStatus(s).action,'events');s.me.role='player';assert.equal(travelStatus(s).action,'wait');s.me.owner='p';s.journey.pendingCount=0;s.journey.phase='resolving';assert.equal(travelStatus(s).action,'complete');s.journey.completed.p=true;assert.equal(travelStatus(s).action,'wait');
}
console.log('Equipment: artifact successes, pushing, item-specific armor wear, overload decisions and journey next actions passed.');
