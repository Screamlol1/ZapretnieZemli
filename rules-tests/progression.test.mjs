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
