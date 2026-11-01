import assert from 'node:assert/strict';
import {newBattle,startBattle,activeUnit,moveUnit,attack,rangeName,validateBattle,aiTurn,simpleAction,lineOfSight,pathTo,movementReason} from '../public/tools/battle-rules.js';
function setup(){const s=newBattle();startBattle(s,()=>1);const u=activeUnit(s),v=s.units.find(x=>x.team!==u.team);s.terrain={};s.units.forEach((x,i)=>{x.q=i*2;x.r=0;});u.q=3;u.r=3;v.q=5;v.r=3;u.weapon='sword';u.gear=2;return {s,u,v};}
for(const [d,name] of [[1,'расстояние руки'],[2,'близкая'],[3,'короткая'],[4,'дальняя'],[6,'дальняя'],[7,'предельная']]){const {s,u,v}=setup();v.q=u.q+d;assert.equal(rangeName(s,u,v),name);}
{
 const {s,u,v}=setup();assert.throws(()=>moveUnit(s,u.id,6,3));moveUnit(s,u.id,4,3);assert.equal(u.fast,0);assert.throws(()=>moveUnit(s,u.id,3,3),/отступление/);v.armor=0;attack(s,v.id,'slash',{},()=>6);assert.equal(u.slow,0);assert.equal(v.str,0);
}
{
 const {s,u,v}=setup();s.terrain['4,3']='rough';moveUnit(s,u.id,4,3,false,()=>2);assert.equal(u.prone,true);assert.equal(u.q,4);
}
{
 const {s,u,v}=setup();v.q=4;v.weapon='dagger';v.gear=1;v.fast=v.slow=0;let i=0;moveUnit(s,u.id,2,3,true,()=>++i<10?2:6);assert.equal(u.q,2);assert.equal(v.fast,0);assert.ok(s.log.some(x=>x.includes('бесплатная атака')));assert.ok(u.str<u.maxStr);
}
{
 const {s,u,v}=setup();u.weapon='spear';u.gear=2;attack(s,v.id,'stab',{},()=>2);assert.equal(u.slow,0);
}
{
 const {s,u,v}=setup();u.weapon='bow';u.ready=true;v.q=7;assert.throws(()=>attack(s,v.id,'shoot'),/дальности/);v.q=6;attack(s,v.id,'shoot',{},()=>2);assert.equal(u.ready,false);
}
{
 const {s,u,v}=setup();v.q=u.q;assert.throws(()=>validateBattle(s),/бойцы/);
}
for(let seed=1;seed<=20;seed++){let n=seed;const die=max=>{n=(1664525*n+1013904223)>>>0;return n%max+1;};const s=newBattle();startBattle(s,die);let turns=0;while(s.phase==='combat'&&turns++<400){aiTurn(s,die);validateBattle(s);}assert.equal(s.phase,'finished',`Battle seed ${seed}`);}
console.log('Player hex model: range ladder, one-hex run, engagement, retreat free attack, spear reach, shooting, occupied cells; 20 complete battles passed.');

{
 const {s,u,v}=setup();v.q=4;let rolls=0;moveUnit(s,u.id,3,4,false,()=>{rolls++;return 1;});assert.equal(rolls,0);assert.equal(u.fast,0);assert.equal(u.q,3);assert.equal(u.r,4);assert.equal(v.str,v.maxStr);assert.equal(s.log.some(x=>x.includes('бесплатная атака')),false);
}
{
 const {s,u,v}=setup();v.q=4;moveUnit(s,u.id,3,4,true,()=>{throw Error('Orbit must not roll');});assert.equal(u.r,4);
}
{
 const {s,u}=setup();u.prone=true;const before=structuredClone(s);assert.throws(()=>moveUnit(s,u.id,3,4),/Лежащий/);assert.throws(()=>moveUnit(s,u.id,3,4,true),/Лежащий/);assert.deepEqual(s,before);assert.match(movementReason(s,u,{q:3,r:4}),/Лежащий/);simpleAction(s,'stand');moveUnit(s,u.id,3,4);assert.equal(u.r,4);
}
{
 const {s,u,v}=setup();v.q=4;v.str=0;assert.ok(pathTo(s,u,{q:4,r:3}));moveUnit(s,u.id,4,3);validateBattle(s);const raw=structuredClone(s);raw.units.reverse();validateBattle(raw);u.fast=1;moveUnit(s,u.id,5,3);assert.equal(u.q,5);
}
for(const downed of [false,true]){
 const {s,u,v}=setup();u.weapon='bow';u.gear=2;u.ready=false;u.shoot=3;v.q=6;v.armor=0;const blocker=s.units.find(x=>x.id!==u.id&&x.id!==v.id);blocker.q=4;blocker.r=3;blocker.str=downed?0:blocker.maxStr;assert.ok(lineOfSight(s,u,v));attack(s,v.id,'shoot',{},()=>2);assert.equal(u.slow,0);u.slow=1;attack(s,v.id,'shoot',{},()=>2);
}
{
 const {s,u,v}=setup();u.weapon='bow';u.ready=false;simpleAction(s,'aim');assert.equal(u.aim,true);attack(s,v.id,'shoot',{},()=>2);
}
{
 const {s,u,v}=setup();u.weapon='crossbow';u.ready=false;assert.throws(()=>attack(s,v.id,'shoot'),/подготовьте/);simpleAction(s,'ready');assert.equal(u.slow,0);
}
console.log('Orbit without reactions, prone movement lock, downed-cell passage/import, unobstructed live/downed shots, unprepared repeat bow shots and crossbow reload passed.');
