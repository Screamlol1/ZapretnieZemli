import {ITEMS,inventory,money,PROFESSIONS} from './public/tools/rules.js';
let input='';for await(const chunk of process.stdin)input+=chunk;
try{const c=JSON.parse(input);const items=c.kind==='npc'?c.sheet.gear.map(id=>ITEMS[id]):inventory(c.sheet);const remaining=c.kind==='npc'?0:Math.max(0,money(c.sheet).remaining),copper=PROFESSIONS[c.sheet.profession]?.copper;process.stdout.write(JSON.stringify({items:items.filter(x=>x&&!x.resource),coins:{gold:0,silver:copper?0:Math.floor(remaining/10),copper:copper?remaining:remaining%10}}));}
catch(e){process.stderr.write(e.message);process.exitCode=1;}
