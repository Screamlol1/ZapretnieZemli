import assert from 'node:assert/strict';
import {newBattle,startBattle,activeUnit,castSpell,spellReason,resolveMishap,validateBattle,BATTLE_MAPS,BATTLE_CHARACTERS,simpleAction,endTurn,aiTurn} from '../public/tools/battle-rules.js';
for(const map of Object.keys(BATTLE_MAPS))for(const count of [2,6,10]){
 const s=newBattle(map,BATTLE_CHARACTERS.slice(0,count).map((u,i)=>({id:u.id,team:i%2?'B':'A'})));
 assert.equal(new Set(s.units.map(u=>`${u.q},${u.r}`)).size,count);validateBattle(s);startBattle(s,()=>1);validateBattle(s);
}
assert.throws(()=>newBattle('road',BATTLE_CHARACTERS.map(u=>({id:u.id,team:'A'}))));
function setup(){const s=newBattle('grove',[{id:'c5',team:'A'},{id:'b1',team:'B'},{id:'a1',team:'B'}]);startBattle(s,()=>1);s.turn=s.order.indexOf('c5');s.terrain={};const u=activeUnit(s),v=s.units.find(u=>u.id==='b1'),x=s.units.find(u=>u.id==='a1');u.q=3;u.r=3;v.q=5;v.r=3;x.q=6;x.r=4;return {s,u,v,x};}
{
 const {s,u,v}=setup();castSpell(s,'immolate',v.id,{wp:1,ingredient:true,safe:true},()=>6);assert.equal(v.str,2);assert.equal(v.burning,true);assert.equal(v.armor,3);assert.equal(u.wp,5);assert.equal(u.ingredients.torch,1);assert.equal(u.slow,0);assert.throws(()=>castSpell(s,'doom',v.id,{wp:1}));validateBattle(s);
}
{
 const {s,u}=setup();let calls=0;castSpell(s,'firewalker',null,{wp:1,safe:true},()=>{calls++;return 1;});assert.equal(calls,0);assert.equal(u.fireproof,true);assert.equal(s.pendingMishap,null);
}
{
 const {s,u,v}=setup();v.q=6;assert.match(spellReason(s,u,'doom',v.id,{wp:1}),/дальности/);castSpell(s,'doom',v.id,{wp:1,extend:true},()=>2);assert.equal(u.wp,4);assert.equal(v.str,4);
}
{
 const {s,u,v}=setup();const dice=[1,4,2];castSpell(s,'doom',v.id,{wp:1},()=>dice.shift());assert.equal(s.pendingMishap.roll,42);validateBattle(s);assert.throws(()=>endTurn(s),/неудачу/);assert.throws(()=>resolveMishap(s,''));resolveMishap(s,'Дополнительная цель — колдун',u.id);assert.equal(u.str,2);assert.equal(s.pendingMishap,null);validateBattle(s);
}
{
 const {s,u,v}=setup();const dice=[1,6,2];castSpell(s,'doom',v.id,{wp:1},()=>dice.shift());assert.equal(u.str,2);assert.equal(v.str,5);assert.equal(s.pendingMishap,null);
}
{
 const {s,u}=setup();const dice=[1,6,2];castSpell(s,'firewalker',null,{wp:1,safe:false},()=>dice.shift());assert.equal(u.str,2);assert.equal(u.fireproof,false);
}
{
 const {s,u,v}=setup();v.burning=true;s.turn=s.order.indexOf(v.id);simpleAction(s,'extinguish',()=>6);assert.equal(v.burning,false);assert.equal(v.slow,0);
}
{
 const {s,u,v}=setup();aiTurn(s,()=>2);assert.equal(u.wp,5);assert.equal(v.burning,true);
}
{
 const {s,u,v}=setup();u.wp=0;assert.match(spellReason(s,u,'doom',v.id,{wp:1}),/силы воли/);u.wp=6;s.terrain['4,3']='wall';assert.match(spellReason(s,u,'doom',v.id,{wp:1}),/преградой/);
}
console.log('Maps, variable squads and magic tests passed.');
