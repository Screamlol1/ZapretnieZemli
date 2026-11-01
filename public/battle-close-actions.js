import {activeUnit,isAlive,hexDistance,lineOfSight,weaponFor,canSpend,attack,moveUnit,simpleAction,spend,defend} from './tools/battle-rules.js';
import {rank} from './battle-talents.js';
import {rollPool,poolScore} from './dice-pools.js';
import {tracePool} from './dice-trace.js';
import {injuryPenalty} from './battle-injuries.js';
const log=(b,t)=>{b.log.push(t);b.commandLog?.push(t);};
export const closeNames={slash:'Рубящий',stab:'Колющий',punch:'Кулаком',grapple:'Захват',grappleAttack:'Удар в захвате',breakFree:'Вырваться',dodge:'Уклониться и упасть',dodgeStand:'Уклониться стоя',weapon:'Парировать оружием',shield:'Парировать щитом',draw:'Поднять / достать оружие',swing:'Замах',stand:'Встать',shove:'Толчок',disarm:'Обезоружить',feint:'Финт',retreat:'Отступить',await:'Ожидать'};
export function speed(u,action){return ['grapple','breakFree'].includes(action)?'slow':['slash','stab','punch'].includes(action)?action==='punch'&&rank(u,'brawler')>=2||action==='stab'&&u.weapon==='dagger'&&rank(u,'knife')>=2?'fast':'slow':'fast';}
export function available(b,u,v,action){
 if(!u||!isAlive(u))return 'Персонаж не может действовать.';
 if(action==='await')return '';
 if(u.grappledBy&&action!=='breakFree')return 'Сначала вырвитесь из захвата.';
 if(u.grappling&&!['grappleAttack','release'].includes(action))return 'В захвате доступен только удар или отпускание.';
 if(action==='release')return u.grappling?'':'Вы никого не удерживаете.';
 if(action==='draw'){if(!u.disarmed)return 'Оружие уже в руке.';if(u.droppedWeapon&&hexDistance(u,u.droppedWeapon)>1)return 'Оружие дальше расстояния руки.';}
 if(action==='stand'&&!u.prone)return 'Персонаж уже стоит.';
 if(action==='swing'&&(!weaponFor(u).heavy||!u.gear||u.disarmed))return 'Нужно готовое тяжёлое оружие.';
 if(action==='breakFree'&&!u.grappledBy)return 'Персонаж не захвачен.';
 if(action==='grappleAttack'&&(!u.grappling||v?.id!==u.grappling))return 'Сначала захватите противника.';
 if(['slash','stab','punch','grapple','shove','disarm','feint','grappleAttack'].includes(action)){
  if(!v||!isAlive(v)||u.team===v.team)return 'Нужен действующий противник.';
  const reach=['grapple','punch','grappleAttack','shove'].includes(action)?1:weaponFor(u).near?2:1;
  if(hexDistance(u,v)>reach||!lineOfSight(b,u,v))return 'Цель вне досягаемости.';
  if(u.prone&&!['shove','grappleAttack'].includes(action))return 'Сначала встаньте.';
  if(action==='grapple'&&v.monster)return 'Чудовища не поддаются обычному захвату.';
  if(action==='grapple'&&(v.grappledBy||v.grappling))return 'Противник уже участвует в захвате.';
  if(['slash','stab','disarm'].includes(action)&&(!u.gear||u.disarmed))return 'Нужно готовое исправное оружие.';
  if(['slash','stab'].includes(action)&&!weaponFor(u)[action])return 'Оружие не поддерживает эту атаку.';
  if(action==='disarm'&&(v.monster||v.disarmed||!v.gear||rank(v,'firmgrip')>=3))return 'Оружие уже потеряно либо Крепкая хватка 3 запрещает обезоруживание.';
 }
 if(['weapon','shield'].includes(action)&&(!u.gear||u.disarmed)&&action==='weapon'||action==='shield'&&!u.shield)return 'Нет готового предмета для парирования.';
 const free=action==='draw'&&rank(u,'quickdraw')>=(weaponFor(u).heavy?3:weaponFor(u).light||u.weapon==='dagger'?1:2)||action==='stand'&&rank(u,'steady')>=3;
 return free||canSpend(u,speed(u,action))?'':'Не осталось подходящего действия.';
}
export function closeAction(b,u,v,action,details={},d){
 const reason=available(b,u,v,action);if(reason)throw Error(reason);
 if(action==='await')return;
 const originalTurn=b.turn;b.turn=b.order.indexOf(u.id);if(b.turn<0)throw Error('Персонаж не включён в инициативу.');
 try{
  if(['slash','stab','punch','shove'].includes(action)){attack(b,v.id,action,{},d);return;}
  if(['swing','stand'].includes(action)){simpleAction(b,action,d);return;}
  if(action==='retreat'){moveUnit(b,u.id,details.q,details.r,true,d);return;}
  if(['dodge','dodgeStand','weapon','shield'].includes(action)){spend(u,'fast');if(action==='dodge')u.prone=true;log(b,`${u.name}: защита подготовлена, противник не атаковал.`);return;}
  if(action==='draw'){
   if(rank(u,'quickdraw')<(weaponFor(u).heavy?3:weaponFor(u).light||u.weapon==='dagger'?1:2))spend(u,'fast');
   u.disarmed=false;delete u.droppedWeapon;log(b,`${u.name}: оружие снова в руке.`);return;
  }
  if(action==='release'){const target=b.units.find(x=>x.id===u.grappling);if(target)delete target.grappledBy;delete u.grappling;return;}
  if(action==='grappleAttack'){
   spend(u,'fast');attack(b,v.id,'punch',{bonusAttack:true,ignoreDefense:true,ignoreProne:true},d);if(!isAlive(v)){delete u.grappling;delete v.grappledBy;}return;
  }
  if(action==='breakFree'){
   const holder=b.units.find(x=>x.id===u.grappledBy);if(!holder||!isAlive(holder)){delete u.grappledBy;return;}
   spend(u,'slow');const defense=rollPool(holder.str,holder.melee,0,injuryPenalty(holder,'melee','str'),d);tracePool(b,holder,'Удержание',defense);
   const roll=rollPool(u.str,u.melee,0,injuryPenalty(u,'melee','str'),d);tracePool(b,u,'Вырваться из захвата',roll,{attribute:'str',requiredSuccesses:poolScore(defense).hits+1});
   if(poolScore(roll).hits>poolScore(defense).hits){delete u.grappledBy;delete holder.grappling;log(b,`${u.name} вырвался из захвата.`);}else log(b,`${u.name} остаётся в захвате.`);return;
  }
  if(action==='feint'){
   spend(u,'fast');const from=b.initiativeSlots?.find(s=>s.members.includes(u.id)),to=b.initiativeSlots?.find(s=>s.members.includes(v.id));
   if(from&&to)(b.pendingFeints??=[]).push({from:from.key,to:to.key});else(b.pendingFeints??=[]).push({from:u.id,to:v.id,legacy:true});
   log(b,`${u.name}: финт против ${v.name}; обмен инициативой вступит в силу со следующего раунда.`);return;
  }
  if(['disarm','grapple'].includes(action)){
   const defense=defend(b,v,action,d);spend(u,speed(u,action));
   const n=action==='disarm'?((weaponFor(v).grip?weaponFor(v).grip.includes('2'):['spear','staff','halberd','greatsword','bow','longbow','crossbow'].includes(v.weapon))?2:1)+Math.min(2,rank(v,'firmgrip')):1;
   const roll=rollPool(u.str,u.melee,action==='grapple'?0:u.gear,injuryPenalty(u,'melee','str'),d);tracePool(b,u,closeNames[action],roll,{attribute:'str',gearField:action==='disarm'?'gear':null,requiredSuccesses:defense+n});
   if(poolScore(roll).hits-defense>=n){
    v.disarmed=true;v.droppedWeapon={q:v.q,r:v.r};
    if(action==='grapple'){u.prone=true;v.prone=true;u.grappling=v.id;v.grappledBy=u.id;}
    log(b,`${u.name}: ${action==='grapple'?'захватил':'обезоружил'} ${v.name}.`);
   }else log(b,`${u.name}: ${closeNames[action]} не удался.`);return;
  }
  throw Error('Неизвестное действие ближнего боя.');
 }finally{b.turn=originalTurn;}
}
