import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';
import * as rules from '../public/tools/rules.js';
import * as reforged from '../public/tools/reforged.js';
import * as life from '../public/tools/lifepath.js';
import {HINTS} from '../public/tools/hints.js';
// Run the production UI handlers with a minimal DOM adapter, without browser processes.
const elements=new Map(),registered=new Map();
function element(id){if(!elements.has(id))elements.set(id,{value:'',textContent:'',disabled:false,hidden:false,classList:{add(){},remove(){}},addEventListener(){},set innerHTML(html){this.html=html;const options=[...html.matchAll(/<option value="([^"]*)"([^>]*)>/g)];if(options.length)this.value=(options.find(x=>x[2].includes('selected'))||options[0])[1];},get innerHTML(){return this.html||'';}});return elements.get(id);}
const context=vm.createContext({...rules,...life,...reforged,HINTS,AbortController,structuredClone,crypto:globalThis.crypto,setTimeout(){return 1;},clearTimeout(){},document:{getElementById:element,addEventListener(){},modelContext:{registerTool(tool){registered.set(tool.name,tool);}}},window:{addEventListener(){}}});
const source=fs.readFileSync(new URL('../public/tools/app.js',import.meta.url),'utf8').replace(/^import[^\n]*\n/gm,'');
vm.runInContext(source,context);
const read=()=>registered.get('read_character_sheet').execute({}).character;
const load=character=>registered.get('configure_character_sheet').execute({character});
for(const initial of [rules.blank(),life.generateLifepath({origin:'alder',profession:'fighter',age:'old'},()=>1)]){
 load(initial);
 const remove=id=>{let stopped=false;element('talents').onclick({target:{closest(){return {dataset:{remove:id}};}},preventDefault(){},stopPropagation(){stopped=true;}});assert.equal(stopped,true);assert.equal(Object.hasOwn(read().talents,id),false);};
 for(const id of Object.keys(read().talents))remove(id);
 const available=rules.budgets(read()).talents;
 for(let i=0;i<3;i++){
  element('add-talent').value='lucky';element('talent-add').onclick();
  assert.equal(read().talents.lucky,1);assert.match(element('talents').innerHTML,/data-remove="lucky"/);
  remove('lucky');assert.equal(rules.budgets(read()).talents,available);
  assert.deepEqual(rules.validateImport(read()).talents,{});
 }
}
console.log('Production UI: manually added talents removed and re-added three times in normal and lifepath modes; budgets and saved imports verified.');

