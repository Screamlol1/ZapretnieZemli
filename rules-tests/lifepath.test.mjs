import assert from 'node:assert/strict';
import {generateLifepath,ORIGINS,LIFE_EVENTS,replayLifepath} from '../public/tools/lifepath.js';
import {validateImport,AGES,budgets,inventory,resources} from '../public/tools/rules.js';
import {LIFEPATH_DATA} from '../public/tools/lifepath-data.js';
let seed=91826;const die=n=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed%n+1;};
let count=0;
for(const origin of Object.keys(ORIGINS))for(const profession of Object.keys(LIFE_EVENTS))for(const age of Object.keys(AGES))for(let i=0;i<20;i++){
 const s=generateLifepath({origin,profession,age},die),copy=validateImport(JSON.parse(JSON.stringify(s)));
 assert.deepEqual(copy,s);assert.deepEqual(budgets(s),{attrs:0,skills:0,talents:0});
 assert.equal(s.lifepath.events.length,AGES[s.age].talents);assert.equal(s.age,origin==='elf'?'adult':age);
 assert.ok(Object.values(s.attrs).every(x=>x>=1&&x<=5));assert.ok(Object.values(s.skills).every(x=>x>=0&&x<=5));
 assert.equal(inventory(s).length,s.gear.length);assert.ok(inventory(s).every(Boolean));
 assert.ok(resources(s).arrows>=s.lifeArrows);assert.ok(!s.gear.includes('')&&!s.trade.length);
 const bad=structuredClone(s);bad.skills.melee++;assert.throws(()=>validateImport(bad));
 const bad2=structuredClone(s);bad2.lifepath.events[0].roll=7;assert.throws(()=>validateImport(bad2));
 count++;
}
for(const rows of Object.values(LIFEPATH_DATA.children)){assert.equal(rows.length,6);for(const row of rows){assert.equal(Object.values(row.attrs).reduce((a,b)=>a+b),15);assert.equal(Object.values(row.skills).reduce((a,b)=>a+b),6);}}
const t=generateLifepath({origin:'alder',profession:'fighter',age:'old'},()=>1);assert.equal(t.talents.pain,3);assert.equal(t.gear.filter(x=>x==='studded').length,3);
const transfer=structuredClone(t);transfer.lifepath.transfer={from:'emp',to:'str'};transfer.attrs=replayLifepath(transfer.lifepath).attrs;assert.deepEqual(validateImport(transfer).attrs,transfer.attrs);
assert.throws(()=>validateImport({...t,lifepath:{...t.lifepath,kinRoll:19}}));
const edited=structuredClone(t);edited.talentsEdited=true;edited.talents={};
assert.deepEqual(validateImport(edited).talents,{});
assert.equal(budgets(edited).talents,3);
edited.talents={lucky:1,tongue:2};
assert.deepEqual(validateImport(edited).talents,edited.talents);
edited.talents.lucky=2;assert.throws(()=>validateImport(edited));
edited.talents={unknown:1};assert.throws(()=>validateImport(edited));
console.log(`${count} generated characters verified across all origins, professions and ages; replay, imports, caps, equipment and tampering checked.`);


