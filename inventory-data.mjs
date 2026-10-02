import {ITEMS,inventory} from './public/tools/rules.js';
let input='';for await(const chunk of process.stdin)input+=chunk;
try{const c=JSON.parse(input);const items=c.kind==='npc'?c.sheet.gear.map(id=>ITEMS[id]):inventory(c.sheet);process.stdout.write(JSON.stringify(items.filter(x=>x&&!x.resource)));}
catch(e){process.stderr.write(e.message);process.exitCode=1;}
