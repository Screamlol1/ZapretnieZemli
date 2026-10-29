import assert from 'node:assert/strict';
import {blank,validateImport,budgets,normalize} from '../public/tools/rules.js';
import {generateLifepath} from '../public/tools/lifepath.js';
import {pipReason} from '../public/tools/creation-feedback.js';
const s=blank();s.skills.melee=3;s.skills.heal=1;
assert.match(pipReason(s,'skills','heal',2),/максимум 1/);
assert.match(pipReason(s,'skills','melee',4),/максимум 3/);
s.skills.might=3;s.skills.endure=1;
assert.match(pipReason(s,'skills','move',1),/Недостаточно очков/);
assert.equal(pipReason(s,'skills','melee',2),'');
for(const base of [s,generateLifepath({origin:'alder',profession:'fighter',age:'young'},()=>1)]){
 const before=budgets(base),id=Object.keys(base.skills).find(k=>base.skills[k]<5),old=base.skills[id];
 const cost=(old+1)*5;
 const hero=structuredClone(base);hero.progression={version:1,revision:1,baseSkills:{...base.skills},earned:100,spent:cost,training:{},restCycle:null};hero.skills[id]++;
 const checked=validateImport(hero);
 assert.equal(checked.skills[id],old+1);assert.deepEqual(budgets(checked),before);
 assert.deepEqual(normalize(structuredClone(checked)),checked);
 assert.match(pipReason(checked,'skills',id,old+2),/Развитие/);
 const bad=structuredClone(hero);bad.progression.spent=0;assert.throws(()=>validateImport(bad),/развития/);
 bad.progression.spent=cost;bad.skills[id]=6;assert.throws(()=>validateImport(bad),/развития/);
 bad.skills[id]=old+1;bad.progression.earned=0;assert.throws(()=>validateImport(bad),/развития/);
}
console.log('Creation reasons and earned skill validation: caps, budget, lifepath, XP accounting and no normalization loss.');

for(const base of [blank(),generateLifepath({origin:'alder',profession:'fighter',age:'young'},()=>1)]){
 const hero=structuredClone(base),id='defender',start=base.talents[id]||0;
 hero.progression={version:2,revision:2,baseSkills:{...base.skills},baseTalents:{...base.talents},basePaths:{[base.path]:base.pathRank},earned:100,spent:0,training:{},restCycle:null,talentTraining:{},practiceCycle:null,purchases:[]};
 hero.paths={[base.path]:base.pathRank};
 for(let rank=start+1;rank<=3;rank++){hero.progression.purchases.push({kind:'talent',id,rank,cost:rank*3,method:rank===1?'teacher':'advance',teacher:rank===1,session:1,cycle:'test'});hero.progression.spent+=rank*3;}
 hero.talents[id]=3;
 const extra=base.path==='enemy'?'shield':'enemy';hero.paths[extra]=1;hero.progression.purchases.push({kind:'path',id:extra,rank:1,cost:3,method:'teacher',teacher:true,session:1,cycle:'test'});hero.progression.spent+=3;
 const checked=validateImport(hero);assert.equal(checked.talents[id],3);assert.equal(checked.paths[extra],1);assert.deepEqual(budgets(checked),budgets(base));assert.deepEqual(normalize(checked),checked);
 for(const mutate of [s=>s.progression.spent--,s=>s.paths.blood=1,s=>s.pathRank=3,s=>s.progression.purchases[0].rank=3,s=>s.progression.purchases[0].cost=1]){const bad=structuredClone(hero);mutate(bad);assert.throws(()=>validateImport(bad),/развития/);}
}
console.log('Paid talents and multiple paths roundtrip for normal/lifepath sheets; rank, cost and profession tampering rejected.');
