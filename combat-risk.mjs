import {pathRank,spendWillpower,willpowerAvailable,endPreyOnBroken} from './public/combat-abilities.js';
import {injuryEvent} from './public/battle-injuries.js';
import {battleDie} from './public/tools/battle-rules.js';
import {tracePool,traceDice} from './public/dice-trace.js';
import {powerAllowed} from './public/battle-talents.js';
import {pushPool,canPushPool} from './public/dice-pools.js';

// Resume a command from its server-owned input, replaying only already drawn dice.
// No future random values are generated or sent to clients while a choice is pending.
export function riskCommand(input, command, execute, random=battleDie){
 const pending=input.pendingRisk;
 if(pending && (command.action!=='risk'||command.roll!==pending.id||typeof command.push!=='boolean'))throw Error('Сначала примите результат броска или пойдите на риск.');
 if(!pending&&command.action==='risk')throw Error('Этот бросок уже завершён.');
 if(!pending&&!command.interactive){input.injuryCommandId=crypto.randomUUID();execute(input,command,random);delete input.injuryCommandId;return input;}
 const replay=pending?structuredClone(pending.replay):{before:structuredClone(input),command:structuredClone(command),draws:[],choices:[],events:0,logs:0};
 if(pending)replay.choices.push(pending.kind==='power'?(command.power||{damage:0,ignoreArmor:false}):['avoid','orc'].includes(pending.kind)?(command.wp||0):command.push);
 replay.id??=crypto.randomUUID();const s=structuredClone(replay.before);s.injuryCommandId=replay.id;s.diceEvents=[];s.commandLog=[];
 let draw=0,check=0;const stop={};
 const die=sides=>{const old=replay.draws[draw++];if(old){if(old.sides!==sides)throw Error('Состав броска изменился.');return old.value;}const value=random(sides);replay.draws.push({sides,value});return value;};
 s.riskCheck=(u,label,p,context)=>{
  if(u.monster||!canPushPool(p))return;
  let attempt=0;
  while(true){
   const extra=attempt>0,choice=replay.choices[check++];
   if(choice===undefined){
    const id=crypto.randomUUID();s.pendingRisk={id,actor:u.id,label,...context,...(extra?{kind:'dwarf'}:{})};
    s.diceEvents.at(-1).risk={action:'combat',roll:id,character:u.id,attribute:context.attribute,...(extra?{kind:'dwarf',wp:willpowerAvailable(u,s)}:{})};throw stop;
   }
   if(!choice)return;
   if(extra)spendWillpower(u,s,1);
   const {damage,wear}=pushPool(p,die);const old=u[context.attribute];u[context.attribute]=Math.max(0,old-damage);
   endPreyOnBroken(s,u);if(old>0&&!u[context.attribute])injuryEvent(s,u,context.attribute,'other','push');
   if(context.gearField)u[context.gearField]=Math.max(0,u[context.gearField]-wear);
   if(!u.npc)u.wp=Math.min(10,u.wp+damage);
   tracePool(s,u,(extra?'Упорство · ':'Пойти на риск · ')+label,p);
   const text=`${u.name}: риск — ${context.attribute} −${damage}, износ −${wear}${u.npc?'':`, СВ +${damage}`}${extra?', дополнительный риск за 1 СВ':''}.`;
   s.diceEvents.at(-1).result+=' '+text;s.log.push(text);s.commandLog.push(text);attempt++;
   if(old>0&&!u[context.attribute])s.brokenChoice?.(u,context.attribute);
   if(u.kin!=='dwarf'||!u[context.attribute]||!canPushPool(p)||!willpowerAvailable(u,s))return;
  }
 };
 s.avoidHit=(u,hits,attacker)=>{
  if(u.kin!=='halfling'||!hits||!willpowerAvailable(u,s))return 0;
  const maximum=Math.min(hits,willpowerAvailable(u,s)),choice=replay.choices[check++];
  if(choice===undefined){
   const id=crypto.randomUUID();s.pendingRisk={id,actor:u.id,kind:'avoid',label:'Неуловимость'};
   traceDice(s,u,'Неуловимость',[],`${attacker.name}: осталось ${hits} успехов. Можно отменить успехи до брони.`);
   s.diceEvents.at(-1).risk={action:'combat',kind:'avoid',roll:id,character:u.id,wp:willpowerAvailable(u,s),maximum};throw stop;
  }
  if(!Number.isInteger(choice)||choice<0||choice>maximum)throw Error('Выберите допустимое число успехов для отмены.');
  if(choice){spendWillpower(u,s,choice);const text=`${u.name}: Неуловимость, отменено ${choice} успехов.`;s.log.push(text);s.commandLog.push(text);}return choice;
 };
 s.brokenChoice=(u,attribute)=>{
  if(u.kin!=='orc'||u[attribute]!==0||!willpowerAvailable(u,s))return;
  const maximum=Math.min(u[({str:'maxStr',agi:'maxAgi',wits:'maxWits',emp:'maxEmp'})[attribute]],willpowerAvailable(u,s)),choice=replay.choices[check++];
  if(choice===undefined){
   const id=crypto.randomUUID();s.pendingRisk={id,actor:u.id,kind:'orc',label:'Несокрушимость'};
   traceDice(s,u,'Несокрушимость',[],'Характеристика сломлена. Орк может немедленно восстановиться за СВ; критическая травма остаётся.');
   s.diceEvents.at(-1).risk={action:'combat',kind:'orc',roll:id,character:u.id,attribute,wp:willpowerAvailable(u,s),maximum};throw stop;
  }
  if(!Number.isInteger(choice)||choice<0||choice>maximum)throw Error('Выберите допустимое восстановление.');
  if(choice){spendWillpower(u,s,choice);u[attribute]=choice;u.prone=false;const text=`${u.name}: Несокрушимость, ${attribute} +${choice}; травмы сохраняются.`;s.log.push(text);s.commandLog.push(text);}
 };
 s.hitPower=(u,type)=>{
  if(!powerAllowed(u,type,s))return {};
  const choice=replay.choices[check++];
  if(choice===undefined){
   const id=crypto.randomUUID();s.pendingRisk={id,actor:u.id,kind:'power',label:'Попадание · сила воли'};
   traceDice(s,u,'Попадание · сила воли',[],'Попадание подтверждено. Выберите эффект до броска брони.');
   s.diceEvents.at(-1).risk={action:'combat',kind:'power',roll:id,character:u.id,wp:willpowerAvailable(u,s),damageAllowed:pathRank(u,type==='shoot'?'arrow':'blade')>=3,halfelf:u.kin==='halfelf',npc:!!u.npc};throw stop;
  }
  if(!choice||typeof choice!=='object'||typeof choice.ignoreArmor!=='boolean'||!Number.isInteger(choice.damage)||choice.damage<0||choice.damage>10||choice.damage&&pathRank(u,type==='shoot'?'arrow':'blade')<3)throw Error('Недопустимый эффект достоинства.');
  const cost=choice.damage+Number(choice.ignoreArmor);if(cost>willpowerAvailable(u,s))throw Error('Недостаточно силы воли.');
  if(cost)spendWillpower(u,s,cost);const power={...choice,damage:choice.damage+(cost&&u.kin==='halfelf'&&pathRank(u,type==='shoot'?'arrow':'blade')>=3?1:0)};
  if(cost){const text=`${u.name}: СВ −${cost}${power.ignoreArmor?', броня игнорируется':''}${power.damage?`, урон +${power.damage}`:''}.`;s.log.push(text);s.commandLog.push(text);}
  return power;
 };
 try{execute(s,replay.command,die);}catch(e){if(e!==stop)throw e;}
 delete s.injuryCommandId;delete s.riskCheck;delete s.hitPower;delete s.avoidHit;delete s.brokenChoice;
 const events=s.diceEvents.length,logs=s.commandLog.length;
 s.diceEvents=s.diceEvents.slice(replay.events);s.commandLog=s.commandLog.slice(replay.logs);
 if(s.pendingRisk){replay.events=events;replay.logs=logs;s.pendingRisk.replay=replay;}
 s.log=s.log.slice(-300);return s;
}
