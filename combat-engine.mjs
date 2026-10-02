import {newBattle,validateBattle,startBattle,endTurn,activeUnit,moveUnit,attack,simpleAction,aiTurn,castSpell,resolveMishap,BATTLE_WEAPONS} from './public/tools/battle-rules.js';
import {inventory,ITEMS} from './public/tools/rules.js';
import {monsterAttack} from './monster-rules.mjs';
const weapons={broadsword:'sword',longspear:'spear',battleaxe:'axe',shortbow:'bow',lightcrossbow:'crossbow',longbow:'longbow',greatsword:'greatsword',mace:'mace',halberd:'halberd',staff:'staff',dagger:'dagger'};
let input='';for await(const chunk of process.stdin)input+=chunk;
try{
 const payload=JSON.parse(input);let battle;
 if(payload.create){
  battle=newBattle(payload.mapId);const prototype=battle.units[0];battle.units=payload.create.map(({character:c,team},i)=>{
   if(c.kind==='monster'){const m=c.monster,u={...structuredClone(prototype),id:c.id,name:c.name,team,q:team==='A'?2:10,r:i,kind:c.kind,visual:c.visual,monster:m,str:c.runtime?.current.str??m.strength,maxStr:m.strength,agi:m.agility,maxAgi:m.agility,wits:1,maxWits:1,emp:1,maxEmp:1,melee:0,shoot:0,move:0,weapon:'dagger',armor:m.armor,maxArmor:m.armor,gear:0,shield:0,wp:0,magic:{},ingredients:{torch:0,blood:0,hand:0},ready:false};if(!u.str)throw Error('Мёртвое чудовище не может начать бой.');return u;}
   const sheet=c.sheet,items=sheet.creation==='npc'?sheet.gear.map(id=>ITEMS[id]):inventory(sheet),weapon=items.map(x=>weapons[x.id]).find(Boolean)||'dagger',current=c.runtime?.current||sheet.attrs;
   const u={...structuredClone(prototype),id:c.id,name:c.name,team,q:team==='A'?2:10,r:i,weapon,
    str:current.str,maxStr:sheet.attrs.str,agi:current.agi,maxAgi:sheet.attrs.agi,wits:current.wit,maxWits:sheet.attrs.wit,emp:current.emp,maxEmp:sheet.attrs.emp,
    melee:sheet.skills.melee,shoot:sheet.skills.shoot,move:sheet.skills.move,armor:items.reduce((n,x)=>n+(x.armor||0),0),
    shield:Math.max(0,...items.map(x=>x.shield||0)),gear:items.some(x=>weapons[x.id])?BATTLE_WEAPONS[weapon].bonus:0,
    wp:c.kind==='pc'?c.runtime?.wp||0:0,kind:c.kind,npc:c.kind==='npc',kin:sheet.kin,visual:c.visual,magic:{},ingredients:{torch:0,blood:0,hand:0},ready:!!BATTLE_WEAPONS[weapon].crossbow};
   u.maxArmor=u.armor;
   u.armor=Math.min(u.armor,c.runtime?.armor??u.armor);u.gear=Math.min(u.gear,c.runtime?.gearBonus??u.gear);
   if(!u.str||!u.agi||!u.wits||!u.emp)throw Error('Сломленный персонаж не может начать бой.');
   // Automatic magic/talent effects are added only after their campaign rules are audited.
   return u;
  });
  // Find legal, distinct starting cells within the inherited map.
  const used=new Set();for(const u of battle.units){let cell;for(let r=0;r<9&&!cell;r++)for(let q=u.team==='A'?0:7;q<(u.team==='A'?6:13);q++)if(!used.has(`${q},${r}`)&&battle.terrain[`${q},${r}`]!=='wall'){cell={q,r};break;}if(!cell)throw Error('Нет места для отряда.');Object.assign(u,cell);used.add(`${u.q},${u.r}`);}
 }else{
  battle=validateBattle(payload.battle);const c=payload.command,action=c.action;
  if(activeUnit(battle)?.monster&&['slash','stab','shoot','punch','shove','cast','ai'].includes(action))throw Error('Чудовище использует свою таблицу атак.');
  if(action==='start')startBattle(battle);
  else if(action==='end')endTurn(battle);
  else if(action==='ai')aiTurn(battle);
  else if(action==='monsterAttack')monsterAttack(battle,c.target,c.index,c.push);
  else if(action==='move')moveUnit(battle,c.unit,c.q,c.r,c.retreat===true);
  else if(action==='defense'){const u=battle.units.find(u=>u.id===c.unit);if(!u||!['none','dodge','dodgeStand','weapon','shield'].includes(c.value))throw Error('Неизвестная защита.');u.defense=c.value;}
  else if(['slash','stab','shoot','punch','shove'].includes(action))attack(battle,c.target,action,{push:c.push===true});
  else if(action==='cast')castSpell(battle,c.spell,c.target,{wp:c.wp,safe:c.safe===true,ingredient:c.ingredient===true,extend:c.extend===true});
  else if(action==='resolve')resolveMishap(battle,c.note,c.target);
  else if(['stand','extinguish','cover','ready','aim','swing'].includes(action))simpleAction(battle,action);
  else throw Error('Неизвестное действие боя.');
  for(const u of battle.units)if(u.npc||u.monster)u.wp=0;
 }
 process.stdout.write(JSON.stringify(validateBattle(battle)));
}catch(e){process.stderr.write(e.message);process.exitCode=1;}
