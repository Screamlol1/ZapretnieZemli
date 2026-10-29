import {endPreyOnBroken} from './public/combat-abilities.js';
import {injuryPenalty,injuryEvent,injuryAfterCheck,injuryEffects} from './public/battle-injuries.js';
import {defenseCost,rank,weaponTalent} from './public/battle-talents.js';
import {rollPool,poolScore} from './public/dice-pools.js';
import {traceDice,tracePool,diceGroup} from './public/dice-trace.js';
import {protection,rollArtifact} from './public/equipment-dice.js';
import {activeUnit,hexDistance,lineOfSight,battleDie,canSpend,BATTLE_WEAPONS,weaponFor} from './public/tools/battle-rules.js';
export function monsterAttack(battle,targetId,index,push=false,d=battleDie){
 const monster=activeUnit(battle),target=battle.units.find(u=>u.id===targetId);
 if(battle.phase!=='combat'||!monster?.monster||monster.str<=0||!monster.slow)throw Error('Нет медленного действия чудовища.');
 if(push)throw Error('Атаки чудовища нельзя форсировать.');
 if(!target||target.team===monster.team||target.str<=0)throw Error('Выберите действующую цель.');
 if(index==='random'){index=d(6)-1;traceDice(battle,monster,'Выбор атаки чудовища',[diceGroup('table',[index+1])],`Атака: ${index+1}.`);}
 if(!Number.isInteger(index)||index<0||index>5)throw Error('Выберите атаку D6.');
 const a=monster.monster.attacks[index];
 if(hexDistance(monster,target)>a.range||!lineOfSight(battle,monster,target))throw Error('Цель вне дальности или закрыта стеной.');
 if(a.type==='manual')throw Error('Особый эффект: используйте решение Мастера; запишите результат по книге.');
 if(a.type==='fear'&&target.monster)throw Error('Чудовища невосприимчивы к страху.');
 const roll=n=>Array.from({length:n},()=>d(6)),hits=a=>a.filter(v=>v===6).length;
 monster.slow--;let defense=0;
 const mode=target.defense,reaction=defenseCost(target,mode);
 if(a.type==='physical'&&!injuryEffects(target).incapacitated&&!injuryEffects(target).paralyzed&&target.agi>0&&target.wits>0&&target.emp>0&&(reaction.free||canSpend(target,'fast'))&&mode!=='none'){
  let base,skill,gear=0,modifier=0;
  if(mode.startsWith('dodge')&&a.dodge){base=target.agi;skill=target.move;modifier=mode==='dodgeStand'?-2:0;if(mode==='dodge')target.prone=true;}
  else if(a.parry&&['weapon','shield'].includes(mode)){
   base=target.str;skill=target.melee;gear=mode==='shield'?target.shield:target.gear;
   if(!gear||mode==='weapon'&&weaponFor(target).ranged)base=undefined;
   else if(mode==='weapon'&&!weaponFor(target).parrying)modifier=-2;
  }
  if(base!==undefined){if(!reaction.free){if(target.fast)target.fast--;else target.slow--;}target.reactions??={};target.reactions[reaction.key]=(target.reactions[reaction.key]||0)+1;const sword=mode==='weapon'&&weaponTalent(target,'slash')==='sword'?rank(target,'sword'):0;const p=rollPool(base,skill,gear,[modifier,reaction.bonus,sword?1:0,mode==='shield'&&rank(target,'shieldfight')?1:0,injuryPenalty(target,mode.startsWith('dodge')?'move':'melee',mode.startsWith('dodge')?'agi':'str')],d);p.artifact=rollArtifact(mode==='shield'?target.shieldArtifact:mode==='weapon'?target.weaponArtifact:0,d);if(mode==='shield'&&rank(target,'shieldfight')>=3)p.artifact.push({sides:8,value:d(8)});if(sword>=3)p.artifact.push({sides:8,value:d(8)});tracePool(battle,target,'Защита от чудовища',p,{attribute:mode.startsWith('dodge')?'agi':'str',gearField:mode.startsWith('dodge')?null:mode==='shield'?'shield':'gear'});injuryAfterCheck(battle,target,mode.startsWith('dodge')?'move':'melee');defense=poolScore(p).hits;}
 }
 const dice=roll(a.dice);traceDice(battle,monster,a.name,[diceGroup('monster',dice)],`Успехов: ${hits(dice)}.`);const avoided=a.type==='physical'?(battle.avoidHit?.(target,Math.max(0,hits(dice)-defense),monster)||0):0,net=hits(dice)-defense-avoided;let damage=0,armor=[];
 const oldLogLength=battle.log.length;
 if(net>0){damage=a.damage+net-1;if(a.type==='physical'){const saved=protection(target,damage,d);armor=saved.dice;damage=saved.taken;traceDice(battle,target,'Броня',[diceGroup('armor',armor),...saved.artifacts.map(a=>diceGroup('artifact',[a.value],a.sides))],`Поглощено: ${saved.stopped}. Урон: ${saved.taken}.`);target.str=Math.max(0,target.str-damage);}else target.wits=Math.max(0,target.wits-damage);}
 endPreyOnBroken(battle,target);battle.log.push(`${monster.name}: D6 ${index+1} · ${a.name}, [${dice}], защита ${defense}, броня [${armor}] → ${target.name}, ${a.type==='fear'?'Разум':'Телосложение'} −${damage}. ${a.note}`);
 if(net>0&&!target.monster&&target[a.type==='fear'?'wits':'str']===0){injuryEvent(battle,target,a.type==='fear'?'wits':'str',a.type==='fear'?'horror':'other');battle.brokenChoice?.(target,a.type==='fear'?'wits':'str');}
 if(target.str===0&&target.monster)battle.log.push(`${target.name} погибает или умирает; критическая травма не бросается.`);
 battle.commandLog?.push(...battle.log.slice(oldLogLength));battle.log=battle.log.slice(-300);return battle;
}
