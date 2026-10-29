import assert from 'node:assert/strict';
import {blank,budgets,validateImport,normalize,GENERAL} from '../public/tools/rules.js';
import {REFORGED_DEFAULT,creationAge,skillPointCost,startingWillpower,talentAllowed,TALENT_SKILLS} from '../public/tools/reforged.js';
import {generateLifepath} from '../public/tools/lifepath.js';
for(const age of ['young','adult','old'])for(const ageWorth of [false,true])for(const flatCost of [false,true]){
 const s=blank();s.age=age;s.reforged={...REFORGED_DEFAULT,ageWorth,flatCost};
 const expected=(ageWorth?{young:8,adult:12,old:16}:{young:8,adult:10,old:12})[age]+(flatCost?{young:2,adult:3,old:4}[age]:0);
 assert.equal(creationAge(s,{young:{skills:8},adult:{skills:10},old:{skills:12}}).skills,expected);
 s.skills.melee=3;assert.equal(budgets(s).skills,expected-(flatCost?4:3));
 assert.deepEqual(validateImport(JSON.parse(JSON.stringify(s))),s);
}
const s=blank();s.reforged={...REFORGED_DEFAULT,requiresSkills:true};
assert.equal(talentAllowed(s,'ambidextrous'),false);s.skills.melee=1;assert.equal(talentAllowed(s,'ambidextrous'),true);assert.equal(talentAllowed(s,'ambidextrous',2),false);
s.talents={ambidextrous:1};assert.deepEqual(validateImport(s).talents,s.talents);s.skills.melee=0;assert.throws(()=>validateImport(s));normalize(s);assert.deepEqual(s.talents,{});
s.skills.perform=1;assert.equal(talentAllowed(s,'tongue'),true);assert.equal(talentAllowed(s,'harpoon'),false);
assert.ok(GENERAL.filter(g=>!g.expansion).every(g=>TALENT_SKILLS[g.id]?.length));
assert.equal(startingWillpower(s),2);s.attrs.emp=5;s.pathRank=2;assert.equal(startingWillpower(s),4);s.attrs.emp=4;assert.equal(startingWillpower(s),3.5);s.reforged.willpowerThreshold=false;assert.equal(startingWillpower(s),0);
assert.throws(()=>validateImport({...s,reforged:{...s.reforged,flatCost:'true'}}));assert.throws(()=>validateImport({...s,reforged:{...s.reforged,version:'2.0'}}));
const rolled=generateLifepath({origin:'alder',profession:'fighter',age:'young'},()=>1);rolled.reforged={...REFORGED_DEFAULT};assert.throws(()=>validateImport(rolled));
assert.equal(skillPointCost(s,3),4);assert.equal(skillPointCost(blank(),3),3);
console.log('Reforged: all age/cost combinations, prerequisites, imports, invalid module configs, thresholds and ruleset separation verified.');
