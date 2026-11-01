import {activeUnit,isAlive,hexDistance,pathTo,weaponFor,canSpend,spend,attack,moveUnit,inMap,occupied} from './tools/battle-rules.js';
import {rank} from './battle-talents.js';
import {pathRank,spendWillpower} from './combat-abilities.js';
import {closeAction} from './battle-close-actions.js';
const log=(b,t)=>{b.log.push(t);b.commandLog?.push(t);};
const open=(b,u)=>!['wall','forest','rough'].includes(b.terrain[`${u.q},${u.r}`]);
function mountMove(b,u,c){
 if(!u.mounted||u.prone||u.grappledBy||u.grappling||!inMap(c.q,c.r)||occupied(b,c.q,c.r,u.id)||u.q===c.q&&u.r===c.r)throw Error('Нужен всадник и свободный конечный гекс.');
 const rate=(u.mountRate||1)+(u.mountBoostRound===b.round?u.mountBoost||0:0),route=pathTo(b,u,{q:c.q,r:c.r});
 if(!route||route.cost>rate||route.path.some(p=>!open(b,p)))throw Error('Маршрут превышает скорость животного или проходит через закрытую зону.');
 if(u.mountActionsRound!==b.round){u.mountActionsRound=b.round;u.mountFast=1;u.mountSlow=1;}
 if(!u.mountFast&&!u.mountSlow)throw Error('Животное уже использовало оба действия в этом раунде.');
 const from={q:u.q,r:u.r};if(u.mountFast)u.mountFast--;else u.mountSlow--;u.q=c.q;u.r=c.r;
 for(const enemy of b.units.filter(v=>v.team!==u.team&&isAlive(v)&&!v.prone&&!v.disarmed&&['spear','halberd'].includes(v.weapon)&&v.gear>0&&rank(v,'spear')>=2&&canSpend(v,'slow')&&hexDistance(v,from)>1&&hexDistance(v,u)===1))(b.tacticalReactions??=[]).push({actor:enemy.id,target:u.id});
 log(b,`${u.name}: движение животного → (${u.q}, ${u.r}), скорость ${rate}.`);
}
export function tacticsCommand(b,c,d){
 const u=b.units.find(u=>u.id===c.unit);if(!u||u.monster)throw Error('Выберите обычного участника боя.');
 if(c.action==='tacticalRecover'){
  if(!u.painRecovery)throw Error('Нет восстановления от Стойкости к боли.');
  if(c.attribute==='skip'){u.painRecovery=0;return;}
  const max={agi:'maxAgi',wits:'maxWits',emp:'maxEmp'}[c.attribute];
  if(!max||!Number.isInteger(c.amount)||c.amount<1||c.amount>u.painRecovery||u[c.attribute]+c.amount>u[max])throw Error('Выберите утраченную характеристику и допустимое восстановление.');
  u[c.attribute]+=c.amount;u.painRecovery-=c.amount;log(b,`${u.name}: Стойкость к боли, ${c.attribute} +${c.amount}.`);return;
 }
 if(c.action==='tacticalMount'){
  if(b.phase!=='setup'||typeof c.mounted!=='boolean'||!Number.isInteger(c.rate)||c.rate<1||c.rate>5)throw Error('Верховое животное и скорость задаёт Мастер при подготовке.');u.mounted=c.mounted;u.mountRate=c.rate;return;
 }
 if(c.action==='tacticalOffhand'){
  if(b.phase!=='setup')throw Error('Второе оружие выбирается при подготовке боя.');
  if(!c.item){delete u.offhand;return;}
  const item=u.offhandOptions?.find(i=>i.id===c.item);if(!item||!rank(u,'ambidextrous')||rank(u,'ambidextrous')<2&&!item.light||item.heavy||u.shield||(weaponFor(u).grip?weaponFor(u).grip.includes('2'):['greatsword','spear','halberd','staff','bow','longbow','crossbow'].includes(u.weapon)))throw Error('Для второго оружия нужны Обоерукий, свободная рука и подходящее одноручное оружие.');u.offhand=structuredClone(item);return;
 }
 if(c.action==='tacticalGuard'){
  if(b.phase!=='combat'||!isAlive(u)||!pathRank(u,'shield')||!['weapon','shield'].includes(c.mode))throw Error('Нужен действующий боец с Путём щита.');
  if(!c.target){delete u.guardTarget;delete u.guardPlan;return;}
  const ally=b.units.find(v=>v.id===c.target);if(!ally||ally.team!==u.team||!isAlive(ally)||hexDistance(u,ally)>2||u.disarmed&&c.mode==='weapon'||c.mode==='weapon'&&!u.gear||c.mode==='shield'&&!u.shield)throw Error('Выберите союзника в близкой досягаемости и исправный предмет для парирования.');
  if(typeof c.free!=='boolean'||c.free&&pathRank(u,'shield')<2||!Number.isInteger(c.reduction)||c.reduction<0||c.reduction>10||c.reduction&&pathRank(u,'shield')<3)throw Error('Эффект не соответствует рангу Пути щита.');
  u.guardTarget=ally.id;u.guardPlan={mode:c.mode,free:c.free,reduction:c.reduction};log(b,`${u.name}: готов парировать за ${ally.name}; СВ спишутся только при применении.`);return;
 }
 if(c.action==='tacticalReaction'){
  const r=b.tacticalReactions?.[0];if(!r||r.actor!==u.id||typeof c.accept!=='boolean')throw Error('Эта реакция уже завершена.');
  const target=b.units.find(v=>v.id===r.target);b.tacticalReactions.shift();
  if(c.accept){if(!target||!isAlive(target)||rank(u,'spear')<2||!['spear','halberd'].includes(u.weapon)||u.disarmed||hexDistance(u,target)!==1)throw Error('Перехват копьём больше недоступен.');const before=b.turn;b.turn=b.order.indexOf(u.id);try{attack(b,target.id,'stab',{},d);}finally{b.turn=before;}}
  else log(b,`${u.name}: перехват копьём пропущен.`);return;
 }
 if(c.action==='tacticalFinishCharge'&&b.chargeContinuation?.actor===u.id&&(!isAlive(u)||u.prone||u.disarmed||u.grappledBy||b.phase!=='combat')){delete b.chargeContinuation;log(b,`${u.name}: удар натиска сорван перехватом.`);return;}
 if(b.phase!=='combat'||activeUnit(b)?.id!==u.id||!isAlive(u))throw Error('Сейчас действует другой участник.');
 const v=b.units.find(v=>v.id===c.target);
 if(c.action==='tacticalPlainsSpeed'){
  if(!u.mounted||pathRank(u,'plains')<3||!Number.isInteger(c.wp)||c.wp<1)throw Error('Путь равнин 3 увеличивает скорость верхового животного на один раунд.');
  const amount=spendWillpower(u,b,c.wp);u.mountBoost=(u.mountBoostRound===b.round?u.mountBoost||0:0)+amount;u.mountBoostRound=b.round;log(b,`${u.name}: скорость животного +${amount} до конца раунда, СВ −${c.wp}.`);return;
 }
 if(c.action==='tacticalRide'){
  if(b.units.some(enemy=>enemy.team!==u.team&&isAlive(enemy)&&hexDistance(enemy,u)===1))throw Error('Из ближнего боя используйте отступление, а не обычное движение животного.');
  mountMove(b,u,c);return;
 }
 if(c.action==='closeAction'){closeAction(b,u,v,c.choice,c,d);return;}
 if(c.action==='tacticalOffhandAttack'){
  const off=u.offhand,n=rank(u,'ambidextrous');if(!off||!n||u.offhandRound===b.round||!canSpend(u,'fast')||!['slash','stab'].includes(c.choice))throw Error('Вторая рука: одно дополнительное быстрое нападение за раунд.');
  if(!off.gear||n<2&&!off.light)throw Error('Второе оружие сломано или слишком тяжёлое.');
  const saved=Object.fromEntries(['weapon','weaponStats','gear','weaponArtifact','equipmentIds','disarmed','droppedWeapon'].map(k=>[k,u[k]]));
  spend(u,'fast');u.offhandRound=b.round;u.weapon=off.profile;u.disarmed=false;delete u.droppedWeapon;u.weaponStats={name:off.name,bonus:off.maximum,damage:off.damage,grip:off.grip,...off.properties};u.gear=off.gear;u.weaponArtifact=off.artifact;u.equipmentIds={...u.equipmentIds,weapon:off.id};
  try{attack(b,c.target,c.choice,{bonusAttack:true,tacticalModifier:n>=3?0:-2},d);}finally{off.gear=u.gear;Object.assign(u,saved);}return;
 }
 if(c.action==='tacticalCharge'){
  const n=rank(u,'charge');if(!n||!v||hexDistance(u,v)!==2||hexDistance({q:c.q,r:c.r},v)!==1||!['slash','stab','punch','shove'].includes(c.choice))throw Error('Натиск: из близкой дистанции в соседний с противником гекс.');
  moveUnit(b,u.id,c.q,c.r,false,d);
  if(u.pendingMove||!isAlive(u))return;
  if(b.tacticalReactions?.length){b.chargeContinuation={actor:u.id,target:v.id,choice:c.choice,modifier:n>=2?1:0,artifact:n>=3?8:0};log(b,'Удар натиска ожидает перехваты копьём.');return;}
  attack(b,v.id,c.choice,{bonusAttack:true,tacticalModifier:n>=2?1:0,tacticalArtifact:n>=3?8:0},d);return;
 }
 if(c.action==='tacticalFinishCharge'){
  const p=b.chargeContinuation;if(!p||p.actor!==u.id||b.tacticalReactions?.length)throw Error('Нет ожидающего удара натиска.');delete b.chargeContinuation;attack(b,p.target,p.choice,{bonusAttack:!p.mounted,tacticalModifier:p.modifier,tacticalArtifact:p.artifact},d);return;
 }
 if(c.action==='tacticalMountedCharge'){
  if(!u.mounted||rank(u,'horsefight')<3||!v||hexDistance(u,v)<3||!['slash','stab','punch'].includes(c.choice)||!open(b,u)||!open(b,v)||hexDistance({q:c.q,r:c.r},v)!==1)throw Error('Конный натиск: Конный боец 3, открытый грунт, начало не ближе короткой дистанции.');
  mountMove(b,u,c);
  if(b.tacticalReactions?.length){b.chargeContinuation={actor:u.id,target:v.id,choice:c.choice,mounted:true,modifier:0,artifact:8};return;}
  attack(b,v.id,c.choice,{tacticalArtifact:8},d);return;
 }
 if(c.action==='tacticalPlains'){
  if(!u.mounted||pathRank(u,'plains')<2||!inMap(c.q,c.r)||occupied(b,c.q,c.r,u.id)||hexDistance(u,{q:c.q,r:c.r})!==1||!open(b,{q:c.q,r:c.r})||!canSpend(u,'fast'))throw Error('Путь равнин 2: верхом, соседний свободный гекс и действие движения.');
  spendWillpower(u,b,1);spend(u,'fast');u.q=c.q;u.r=c.r;u.mountMovedRound=b.round;log(b,`${u.name}: отступление верхом без проверки за 1 СВ.`);return;
 }
 throw Error('Неизвестная тактическая способность.');
}
