import {activeUnit,hexDistance,lineOfSight,battleDie,canSpend,BATTLE_WEAPONS} from './public/tools/battle-rules.js';
export function monsterAttack(battle,targetId,index,push=false,d=battleDie){
 const monster=activeUnit(battle),target=battle.units.find(u=>u.id===targetId);
 if(battle.phase!=='combat'||!monster?.monster||monster.str<=0||!monster.slow)throw Error('Нет медленного действия чудовища.');
 if(push)throw Error('Атаки чудовища нельзя форсировать.');
 if(!target||target.team===monster.team||target.str<=0)throw Error('Выберите действующую цель.');
 if(index==='random')index=d(6)-1;
 if(!Number.isInteger(index)||index<0||index>5)throw Error('Выберите атаку D6.');
 const a=monster.monster.attacks[index];
 if(hexDistance(monster,target)>a.range||!lineOfSight(battle,monster,target))throw Error('Цель вне дальности или закрыта стеной.');
 if(a.type==='manual')throw Error('Особый эффект: используйте решение Мастера; запишите результат по книге.');
 if(a.type==='fear'&&target.monster)throw Error('Чудовища невосприимчивы к страху.');
 const roll=n=>Array.from({length:n},()=>d(6)),hits=a=>a.filter(v=>v===6).length;
 monster.slow--;let defense=0;
 const mode=target.defense;
 if(a.type==='physical'&&canSpend(target,'fast')&&mode!=='none'){
  let base,skill,gear=0,modifier=0;
  if(mode.startsWith('dodge')&&a.dodge){base=target.agi;skill=target.move;modifier=mode==='dodgeStand'?-2:0;if(mode==='dodge')target.prone=true;}
  else if(a.parry&&['weapon','shield'].includes(mode)){
   base=target.str;skill=target.melee;gear=mode==='shield'?target.shield:target.gear;
   if(!gear||mode==='weapon'&&BATTLE_WEAPONS[target.weapon].ranged)base=undefined;
   else if(mode==='weapon'&&!BATTLE_WEAPONS[target.weapon].parrying)modifier=-2;
  }
  if(base!==undefined){if(target.fast)target.fast--;else target.slow--;const sd=skill+modifier;defense=Math.max(0,hits(roll(base))+hits(roll(Math.abs(sd)))*(sd<0?-1:1)+hits(roll(gear)));}
 }
 const dice=roll(a.dice),net=hits(dice)-defense;let damage=0,armor=[];
 if(net>0){damage=a.damage+net-1;if(a.type==='physical'){armor=roll(target.armor);damage=Math.max(0,damage-hits(armor));if(damage)target.armor=Math.max(0,target.armor-armor.filter(v=>v===1).length);target.str=Math.max(0,target.str-damage);}else target.wits=Math.max(0,target.wits-damage);}
 battle.log.push(`${monster.name}: D6 ${index+1} · ${a.name}, [${dice}], защита ${defense}, броня [${armor}] → ${target.name}, ${a.type==='fear'?'Разум':'Телосложение'} −${damage}. ${a.note}`);
 if(target.str===0&&target.monster)battle.log.push(`${target.name} погибает или умирает; критическая травма не бросается.`);
 battle.log=battle.log.slice(-300);return battle;
}
