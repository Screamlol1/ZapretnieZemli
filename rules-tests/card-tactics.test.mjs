import assert from 'node:assert/strict';
import {newBattle,attack,moveUnit,weaponFor,validateBattle} from '../public/tools/battle-rules.js';
import catalogWeapons from '../public/weapon-profiles.json' with {type:'json'};
import {cardCommand} from '../public/card-combat.js';
import {tacticsCommand} from '../public/battle-tactics.js';
import {closeAction} from '../public/battle-close-actions.js';
import {riskCommand} from '../combat-risk.mjs';
function battle(){const b=newBattle(),p=b.units[0];b.terrain={};b.units=[0,1,2].map((i)=>({...structuredClone(p),id:'u'+i,name:'Боец '+i,team:i?'B':'A',kind:'pc',kin:'human',q:i,r:0,str:10,maxStr:10,agi:4,maxAgi:4,wits:4,maxWits:4,emp:4,maxEmp:4,melee:0,weapon:'sword',gear:1,shield:0,armor:0,maxArmor:0,talents:{},paths:{},wp:4,fast:1,slow:1,defense:'none'}));b.phase='combat';b.round=1;b.order=b.units.map(u=>u.id);b.turn=0;b.log=[];b.diceEvents=[];b.commandLog=[];b.settings.hiddenCombinations=true;return b;}
function cc(b,action,unit='u0',rest={},d=()=>2){cardCommand(b,{action,unit,exchange:b.cardExchange?.id,...rest},d);}
function combo(b,a=['strike','await'],v=['strike','await']){cc(b,'cardStart','u0',{target:'u1'});cc(b,'cardChoose','u0',{cards:a});cc(b,'cardChoose','u1',{cards:v});}
{
 const b=battle();combo(b);assert.equal(b.cardExchange.stage,'attacker');assert.throws(()=>cc(b,'cardDeclare','u1',{choice:'slash'}),/атакующий/);
 cc(b,'cardDeclare','u0',{choice:'slash'});cc(b,'cardDeclare','u1',{choice:'slash'});
 let count=0;cc(b,'cardResolve','u0',{},()=>++count===1?6:2);assert.equal(b.units[1].str,8);assert.equal(b.units[0].str,10,'pain cancels defender attack');assert.equal(b.units[1].slow,0);
 cc(b,'cardDeclare','u0',{choice:'await'});cc(b,'cardDeclare','u1',{choice:'await'});cc(b,'cardResolve');assert.ok(!b.cardExchange);assert.throws(()=>cc(b,'cardResolve'));
}
{
 const b=battle();b.units[1].talents.pain=2;combo(b);cc(b,'cardDeclare','u0',{choice:'slash'});cc(b,'cardDeclare','u1',{choice:'slash'});
 let count=0;cc(b,'cardResolve','u0',{},()=>[1,12].includes(++count)?6:2);assert.ok(b.log.some(x=>x.includes('Боец 1:')&&x.includes('Атака'))||b.units[0].str<10);assert.equal(b.units[1].slow,0);
}
{
 const b=battle();b.units[0].paths.enemy=1;cc(b,'cardStart','u0',{target:'u1'});cc(b,'cardInsight');assert.equal(b.units[0].wp,3);assert.throws(()=>cc(b,'cardChoose','u0',{cards:['strike','await']}),/Сначала/);cc(b,'cardChoose','u1',{cards:['strike','await']});assert.throws(()=>cc(b,'cardPeek','u0',{index:0}));cc(b,'cardPeek','u1',{index:1});assert.deepEqual(b.cardExchange.insight.revealed,[{index:1,card:'await'}]);cc(b,'cardChoose','u0',{cards:['strike','await']});
}
{
 let b=battle();combo(b,['strike','await'],['defend','await']);cc(b,'cardDeclare','u0',{choice:'slash'});cc(b,'cardDeclare','u1',{choice:'dodgeStand'});
 const execute=(state,c,d)=>cardCommand(state,c,d);b=riskCommand(b,{action:'cardResolve',unit:'u0',exchange:b.cardExchange.id,interactive:true},execute,()=>2);
 assert.equal(b.pendingRisk.actor,'u1');assert.equal(b.turn,0,'defender risk preserves initiative owner');
 let safeguards=0;while(b.pendingRisk&&safeguards++<5)b=riskCommand(b,{action:'risk',roll:b.pendingRisk.id,push:false},execute,()=>2);
 assert.ok(!b.pendingRisk);assert.equal(b.cardExchange.step,1);assert.equal(b.units[0].slow,0);assert.equal(b.units[1].fast,0);
}
{
 const b=battle();b.units[1].talents.firmgrip=3;assert.throws(()=>closeAction(b,b.units[0],b.units[1],'disarm',{},()=>6),/хватка/);
 delete b.units[1].talents.firmgrip;closeAction(b,b.units[0],b.units[1],'disarm',{},()=>6);assert.equal(b.units[1].disarmed,true);b.turn=1;b.units[1].talents.quickdraw=2;const fast=b.units[1].fast;closeAction(b,b.units[1],b.units[0],'draw',{},()=>2);assert.equal(b.units[1].fast,fast);assert.equal(b.units[1].disarmed,false);
}
{
 const b=battle();closeAction(b,b.units[0],b.units[1],'grapple',{},()=>6);assert.equal(b.units[1].grappledBy,'u0');assert.equal(b.units[1].prone,true);assert.throws(()=>moveUnit(b,'u0',0,1),/захват/);assert.throws(()=>closeAction(b,b.units[0],b.units[2],'grappleAttack',{},()=>2));closeAction(b,b.units[0],b.units[1],'release');assert.ok(!b.units[1].grappledBy);
}
{
 const b=battle();b.units[1].q=2;b.units[2].q=6;b.units[1].weapon='spear';b.units[1].talents.spear=2;b.units[0].talents.charge=3;
 tacticsCommand(b,{action:'tacticalCharge',unit:'u0',target:'u1',q:1,r:0,choice:'slash'},()=>2);assert.equal(b.units[0].fast,0);assert.equal(b.units[0].slow,1);assert.equal(b.chargeContinuation.actor,'u0');assert.equal(b.tacticalReactions[0].actor,'u1');assert.equal(b.units[1].str,10);
 tacticsCommand(b,{action:'tacticalReaction',unit:'u1',accept:false},()=>2);tacticsCommand(b,{action:'tacticalFinishCharge',unit:'u0'},()=>2);assert.ok(!b.chargeContinuation);assert.ok(b.diceEvents.at(-1).groups.some(g=>g.sides===8));assert.equal(b.units[0].slow,1);
}
{
 const b=battle();const u=b.units[0];u.talents.ambidextrous=1;u.offhand={id:'knife',profile:'dagger',name:'Кинжал',maximum:1,gear:1,damage:1,light:true};tacticsCommand(b,{action:'tacticalOffhandAttack',unit:u.id,target:'u1',choice:'stab'},()=>2);assert.equal(u.weapon,'sword');assert.equal(u.slow,1);assert.equal(u.fast,0);assert.equal(b.diceEvents[0].groups.find(g=>g.kind==='penalty').values.length,2);assert.throws(()=>tacticsCommand(b,{action:'tacticalOffhandAttack',unit:u.id,target:'u1',choice:'stab'},()=>2),/одно дополнительное/);
}
{
 const b=battle();b.units[2].team='A';b.units[2].paths.shield=3;b.units[2].shield=1;b.units[2].q=0;b.units[2].r=1;b.units[2].wp=4;
 tacticsCommand(b,{action:'tacticalGuard',unit:'u2',target:'u0',mode:'shield',free:true,reduction:2},()=>2);b.turn=1;let count=0;attack(b,'u0','slash',{},()=>++count===1||count>11&&count<15?6:2);assert.ok(b.units[2].wp<4);assert.equal(b.units[2].fast,1,'preconsented free parry spends WP, not action');assert.ok(!b.units[2].guardTarget);
}
console.log('Cards/tactics: sealed two-step exchange, pain, Enemy insight, deterministic defense risk, disarm/grapple, spear interruption, offhand and ally Shield tested.');

{
 const b=battle(),u=b.units[0];u.weapon='throwingknife';u.shoot=1;u.talents.throw=3;u.weaponStats={name:'Метательный нож',bonus:1,damage:1,...Object.fromEntries(Object.entries(catalogWeapons.throwingknife).filter(([k])=>k!=='profile'))};b.units[1].q=5;b.units[2].q=10;assert.equal(weaponFor(u).range,6);validateBattle(b);attack(b,'u1','shoot',{},()=>2);assert.equal(u.disarmed,true);assert.deepEqual(u.droppedWeapon,{q:5,r:0});assert.ok(b.diceEvents[0].groups.some(g=>g.sides===8));assert.ok(b.diceEvents[0].sources.some(x=>x.value===1));assert.throws(()=>attack(b,'u1','shoot',{},()=>2),/Оружие выбито/);
}
{
 const b=battle(),u=b.units[0];u.mounted=true;u.mountRate=1;u.paths.plains=3;u.wp=3;b.units[1].q=8;b.units[2].q=10;tacticsCommand(b,{action:'tacticalPlainsSpeed',unit:'u0',wp:1},()=>2);tacticsCommand(b,{action:'tacticalRide',unit:'u0',q:2,r:0},()=>2);assert.equal(u.q,2);assert.equal(u.wp,2);assert.equal(u.fast,1);assert.equal(u.mountFast,0);b.round++;assert.throws(()=>tacticsCommand(b,{action:'tacticalRide',unit:'u0',q:4,r:0},()=>2),/скорость/);
}
{
 const b=battle(),u=b.units[0];u.weapon='bow';u.gear=2;u.talents.fastshoot=3;b.units[1].q=3;b.units[2].q=7;attack(b,'u1','shoot',{},()=>2);assert.equal(u.fast,0);assert.equal(u.slow,1);attack(b,'u1','shoot',{},()=>2);assert.equal(u.slow,0);
}
console.log('Catalog weapon flags, thrown-weapon recovery, Throwing Arm artifact/range, mounted movement/round expiry, Fast Shooter action cost and modifier sources tested.');
