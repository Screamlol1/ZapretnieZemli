import assert from 'node:assert/strict';
import {generateLifepath,growLifepath,ORIGINS,LIFE_EVENTS,replayLifepath} from '../public/tools/lifepath.js';
import {budgets,validateImport} from '../public/tools/rules.js';
let seed=43561;const die=n=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed%n+1;};
let count=0;
for(const origin of Object.keys(ORIGINS))for(const profession of Object.keys(LIFE_EVENTS))for(let i=0;i<20;i++){
 let s=generateLifepath({origin,profession,age:'young'},die);
 if(origin==='elf'){assert.throws(()=>growLifepath(s,die));continue;}
 s.name='Test';s.pride='Pride';s.secret='Secret';s.notes='Keep my notes';s.purchases=['spoon'];
 if(i%2){s.talentsEdited=true;s.talents={lucky:1};}
 if(i%3===0){const from=Object.keys(s.attrs).find(k=>s.attrs[k]>1),to=Object.keys(s.attrs).find(k=>k!==from&&s.attrs[k]<5);s.lifepath.transfer={from,to};s.attrs=replayLifepath(s.lifepath).attrs;}
 for(const age of ['adult','old']){
  const before=structuredClone(s);s=growLifepath(s,die);
  assert.equal(s.age,age);assert.equal(s.lifepath.events.length,before.lifepath.events.length+1);
  assert.deepEqual(s.lifepath.events.slice(0,-1),before.lifepath.events);
  assert.deepEqual(s.lifepath.losses.slice(0,-1),before.lifepath.losses);
  for(const k of ['origin','homeRoll','childRoll','pathRoll','meetingRoll','coins','transfer'])assert.deepEqual(s.lifepath[k],before.lifepath[k]);
  for(const k of ['name','pride','secret','relationships','purchases'])assert.deepEqual(s[k],before[k]);
  assert.ok(s.notes.startsWith('Keep my notes'));assert.deepEqual(budgets(s),{attrs:0,skills:0,talents:0});
  assert.deepEqual(validateImport(JSON.parse(JSON.stringify(s))),s);count++;
 }
 assert.throws(()=>growLifepath(s,die));
}
console.log(`${count} age transitions verified, including edited talents, transfers, repeated skills, import and preserved personal fields.`);
