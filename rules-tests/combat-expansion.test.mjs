import assert from 'node:assert/strict';
import {newBattle,validateBattle,endTurn,attack,moveUnit,simpleAction,startBattle,activeUnit} from '../public/tools/battle-rules.js';
import {initiative} from '../initiative.mjs';
import {initiativeSlots} from '../public/battle-initiative.js';
import {riskCommand} from '../combat-risk.mjs';
import {kinAbility,willpowerAvailable,pathRank} from '../public/combat-abilities.js';
import {defenseCost} from '../public/battle-talents.js';
import {doubleSlash} from '../public/battle-special-actions.js';
import {riskAction} from '../public/dice-risk.js';
function battle(count=2){const b=newBattle();const p=structuredClone(b.units[0]);b.terrain={};b.units=Array.from({length:count},(_,i)=>({...structuredClone(p),id:'u'+i,name:'Боец '+i,kind:'pc',kin:'human',team:i?'B':'A',q:i%13,r:Math.floor(i/13),str:6,maxStr:6,agi:4,maxAgi:4,wits:4,maxWits:4,emp:4,maxEmp:4,weapon:'sword',gear:2,armor:0,maxArmor:0,shield:0,wp:0,talents:{},magic:{},defense:'none'}));b.phase='combat';b.round=1;b.order=b.units.map(u=>u.id);b.log=[];b.commandLog=[];b.diceEvents=[];return b;}
const execute=(b,c,d)=>{b.diceEvents=[];b.commandLog=[];attack(b,c.target,'slash',{},d);};
const resolve=(b,{push=false,wp=0,power}={},die=()=>2)=>riskCommand(b,{action:'risk',roll:b.pendingRisk.id,push,wp,power},execute,die);
{
 const b=battle(17);b.phase='setup';b.order=[];b.round=0;
 b.units.forEach((u,i)=>{u.team=i<10?'A':'B';if(i>=10&&i<16)u.kind='npc';});
 Object.assign(b.units[16],{kind:'monster',monster:{},activations:3});
 initiative(b,{action:'initiativeAutogroup'},()=>1);assert.equal(initiativeSlots(b).length,14);
 assert.throws(()=>initiative(b,{action:'start'},()=>1),/14 карт/);
 delete b.initiativeSlots;
 assert.throws(()=>{b.units[0].initiativeGroup=b.units[1].initiativeGroup='Герои';initiativeSlots(b);},/дополнительное правило/);
 b.settings.sharedHeroInitiative=true;
 for(let i=0;i<10;i++)b.units[i].initiativeGroup='Пара '+Math.floor(i/2);
 assert.equal(initiativeSlots(b).length,9);initiative(b,{action:'start'},()=>1);assert.equal(b.phase,'combat');
 assert.equal(new Set(b.initiativeSlots.map(s=>s.card)).size,9);assert.equal(b.order.length,19);assert.equal(new Set(b.order).size,17);validateBattle(b);
 const clone=structuredClone(b);clone.units.reverse();validateBattle(clone);
 const mon='u16',indices=b.order.flatMap((id,i)=>id===mon?[i]:[]);assert.equal(indices.length,3);
 b.turn=indices[0];activeUnit(b).fast=activeUnit(b).slow=0;
 while(b.turn!==indices[1])endTurn(b);
 assert.equal(activeUnit(b).slow,1,'second monster activation restores its own action budget');
 const round=b.round;while(b.round===round)endTurn(b);assert.equal(b.round,2);validateBattle(b);
 const groupIndex=b.activationOrder.findIndex(e=>e.group==='Пара 0');b.turn=groupIndex;b.activationStarted=false;const groupNext=b.activationOrder[groupIndex+1].unit;initiative(b,{action:'initiativeGroupNext',target:groupNext},()=>1);assert.equal(activeUnit(b).id,groupNext);validateBattle(b);b.activationStarted=true;assert.throws(()=>initiative(b,{action:'initiativeGroupNext',target:groupNext},()=>1));
 b.units[10].gear=1;validateBattle(b); // Wear does not invalidate a previously formed group.
 const tampered=structuredClone(b);tampered.activationOrder[0].card=10;assert.throws(()=>validateBattle(tampered));
}
{
 const b=battle(12);b.phase='setup';b.order=[];b.units.forEach((u,i)=>{u.kind=i?'npc':'pc';u.initiativeGroup=i?'Стража':'';});
 b.units[2].maxStr=7;assert.throws(()=>initiativeSlots(b),/одинаковыми параметрами/);
}
{
 const b=battle();b.units[0].melee=0;b.units[1].kin='halfling';b.units[1].wp=10;
 let p=riskCommand(b,{action:'slash',target:'u1',interactive:true},execute,()=>6);
 assert.equal(p.pendingRisk.kind,'avoid');assert.equal(p.pendingRisk.actor,'u1');assert.equal(p.units[1].str,6);
 p=resolve(p,{wp:p.diceEvents.at(-1).risk.maximum});assert.ok(!p.pendingRisk);assert.equal(p.units[1].str,6);assert.ok(p.units[1].wp<10);
 assert.throws(()=>resolve(p));
}
{
 const b=battle();b.units[0].kin='dwarf';b.units[0].wp=2;
 let p=riskCommand(b,{action:'slash',target:'u1',interactive:true},execute,()=>2);
 p=resolve(p,{push:true},()=>2);assert.equal(p.pendingRisk.kind,'dwarf');assert.equal(p.units[0].wp,2);
 p=resolve(p,{push:true},()=>2);assert.equal(p.pendingRisk.kind,'dwarf');assert.equal(p.units[0].wp,1);
 p=resolve(p,{push:true},()=>2);assert.ok(!p.pendingRisk);assert.equal(p.units[0].wp,0);assert.equal(p.units[0].slow,0);
}
{
 const b=battle(3);b.units[1].kin='orc';b.units[1].wp=3;b.units[2].prey={target:'u1',bonus:1};
 let p=riskCommand(b,{action:'slash',target:'u1',interactive:true},execute,()=>6);
 assert.equal(p.pendingRisk.kind,'orc');assert.equal(p.phase,'combat');assert.equal(p.units[1].str,0);const injuryId=p.injuryEvents[0].id;
 p=resolve(p,{wp:2});assert.equal(p.injuryEvents[0].id,injuryId,'injury id is stable across Orc continuation');assert.equal(p.units[1].str,2);assert.equal(p.units[1].wp,1);assert.equal(p.phase,'combat');assert.ok(p.injuryEvents.some(e=>e.character==='u1'&&e.table==='slash'));
 assert.ok(!p.units[2].prey,'reviving an Orc does not restore a previously ended prey bonus');
}
{
 const b=battle();b.units[0].kin='orc';
 let p=riskCommand(b,{action:'slash',target:'u1',interactive:true},execute,()=>2);
 p=resolve(p,{push:true},()=>1);assert.equal(p.pendingRisk.kind,'orc');assert.equal(p.units[0].str,0);
 p=resolve(p,{wp:2});assert.equal(p.units[0].str,2);assert.ok(!p.pendingRisk);assert.ok(p.injuryEvents.every(e=>e.source==='push'));
}
{
 const b=battle();Object.assign(b.units[0],{kin:'wolfkin',wp:3});kinAbility(b,{unit:'u0',ability:'prey',target:'u1',wp:2,visible:true});assert.equal(b.units[0].wp,1);assert.equal(b.units[0].prey.bonus,2);
 assert.throws(()=>kinAbility(b,{unit:'u0',ability:'prey',target:'u1',wp:1,visible:true}),/уже выбран/);assert.equal(b.units[0].wp,1);
 attack(b,'u1','slash',{},()=>2);assert.equal(b.diceEvents.find(e=>e.label==='Атака').groups.find(g=>g.kind==='skill').values.length,b.units[0].melee+2);
}
{
 const b=battle();Object.assign(b.units[0],{npc:true,kind:'npc',kin:'wolfkin',wp:0});kinAbility(b,{unit:'u0',ability:'prey',target:'u1',wp:1,visible:true});assert.equal(willpowerAvailable(b.units[0],b),0);assert.throws(()=>kinAbility(b,{unit:'u0',ability:'prey',target:'u1',wp:1,visible:true}));endTurn(b);endTurn(b);assert.equal(willpowerAvailable(b.units[0],b),1);
}
{
 const b=battle();Object.assign(b.units[0],{paths:{blade:3},path:'enemy',pathRank:1,kin:'halfelf',wp:2});assert.equal(pathRank(b.units[0],'blade'),3);
 let p=riskCommand(b,{action:'slash',target:'u1',interactive:true},execute,()=>6);assert.equal(p.pendingRisk.kind,'power');
 p=resolve(p,{power:{damage:1,ignoreArmor:false}});assert.equal(p.units[0].wp,1);assert.ok(p.log.some(x=>x.includes('урон +2')));
}
{
 const b=battle();Object.assign(b.units[0],{talents:{shieldfight:2},shield:2});attack(b,'u1','shield',{},()=>2);assert.equal(b.units[0].fast,0);assert.equal(b.units[0].slow,1);assert.equal(b.diceEvents.at(-1).groups.find(g=>g.kind==='gear').values.length,2);
}
{
 const b=battle(3);b.units[2].q=0;b.units[2].r=1;b.units[0].talents={sword:2};doubleSlash(b,['u1','u2'],()=>2);assert.equal(b.units[0].slow,0);assert.equal(b.diceEvents.filter(e=>e.label==='Атака').length,2);assert.throws(()=>doubleSlash(b,['u1','u2'],()=>2));
}
{
 const b=battle();b.units[0].injuries=[{status:'active',mechanics:{modifiers:{melee:-2},runSlow:true,noTwoHand:true}}];attack(b,'u1','slash',{},()=>2);assert.equal(b.diceEvents.find(e=>e.label==='Атака').groups.find(g=>g.kind==='penalty').values.length,2);
 b.units[0].slow=1;b.units[1].q=9;moveUnit(b,'u0',0,1);assert.equal(b.units[0].slow,0);assert.equal(b.units[0].fast,1);
}
{const b=battle();Object.assign(b.units[0],{weapon:'axe',talents:{axe:2},str:1,melee:0,gear:0});b.units[0].gear=2;let n=0;attack(b,'u1','slash',{},()=>++n===1?6:2);assert.ok(b.units[1].str>0);assert.ok(b.injuryEvents.some(e=>e.source==='axeTalent'));}
assert.equal(defenseCost({talents:{defender:3}},'weapon').free,false);
assert.equal(defenseCost({talents:{defender:3},reactions:{parries:1}},'weapon').free,true);
assert.equal(pathRank({npc:true,path:'blade',pathRank:3},'blade'),0,'legacy NPC defaults cannot activate powers');
assert.equal(pathRank({npc:true,npcTalentsConfigured:true,path:'blade',pathRank:3},'blade'),3);
{
 const check={id:'r',diceEvent:'new',pushed:true,base:[2],skillDice:[],gear:[],penalty:[],artifacts:[]},c={id:'c',kind:'pc',owner:'o',sheet:{kin:'dwarf'},runtime:{lastCheck:check,current:{str:3,agi:3,wit:3,emp:3},wp:2}},s={characters:[c],me:{role:'player',owner:'o'},journey:{},opposedChecks:[{id:'pair',attacker:{rolled:true},defender:{rolled:true}}]};
 const event={id:'new',risk:{action:'character',character:'c',roll:'r'}};
 assert.equal(riskAction(s,event).kinRepeat,true);assert.equal(riskAction(s,{...event,id:'old'}),null);
 event.risk={...event.risk,action:'opposed',opposed:'pair'};assert.equal(riskAction(s,event).kinRepeat,true);assert.equal(riskAction(s,{...event,id:'old'}),null);
}
console.log('Expanded combat: 17 figures / 9 cards, monster activations, consented PC groups, kin choices, NPC per-round limits, learned paths, shield and sword actions, injury penalties passed.');
