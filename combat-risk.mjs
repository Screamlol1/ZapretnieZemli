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
 if(!pending&&!command.interactive){execute(input,command,random);return input;}
 const replay=pending?structuredClone(pending.replay):{before:structuredClone(input),command:structuredClone(command),draws:[],choices:[],events:0,logs:0};
 if(pending)replay.choices.push(pending.kind==='power'?(command.power||{damage:0,ignoreArmor:false}):command.push);
 const s=structuredClone(replay.before);s.diceEvents=[];s.commandLog=[];
 let draw=0,check=0;const stop={};
 const die=sides=>{const old=replay.draws[draw++];if(old){if(old.sides!==sides)throw Error('Состав броска изменился.');return old.value;}const value=random(sides);replay.draws.push({sides,value});return value;};
 s.riskCheck=(u,label,p,context)=>{
  if(u.monster||!canPushPool(p))return;
  const choice=replay.choices[check++];
  if(choice===undefined){
   const id=crypto.randomUUID();s.pendingRisk={id,actor:u.id,label,...context};
   s.diceEvents.at(-1).risk={action:'combat',roll:id,character:u.id,attribute:context.attribute};throw stop;
  }
  if(choice){
   const {damage,wear}=pushPool(p,die);u[context.attribute]=Math.max(0,u[context.attribute]-damage);
   if(context.gearField)u[context.gearField]=Math.max(0,u[context.gearField]-wear);
   if(!u.npc)u.wp=Math.min(10,u.wp+damage);
   tracePool(s,u,'Пойти на риск · '+label,p);
   const text=`${u.name}: риск — ${context.attribute} −${damage}, износ −${wear}${u.npc?'':`, СВ +${damage}`}.`;
   s.diceEvents.at(-1).result+=' '+text;s.log.push(text);s.commandLog.push(text);
  }
 };
 s.hitPower=(u,type)=>{
  if(!powerAllowed(u,type))return {};
  const choice=replay.choices[check++];
  if(choice===undefined){
   const id=crypto.randomUUID();s.pendingRisk={id,actor:u.id,kind:'power',label:'Попадание · сила воли'};
   traceDice(s,u,'Попадание · сила воли',[],'Попадание подтверждено. Выберите эффект до броска брони.');
   s.diceEvents.at(-1).risk={action:'combat',kind:'power',roll:id,character:u.id,wp:u.wp,damageAllowed:u.pathRank>=3};throw stop;
  }
  if(!choice||typeof choice!=='object'||typeof choice.ignoreArmor!=='boolean'||!Number.isInteger(choice.damage)||choice.damage<0||choice.damage>10||choice.damage&&u.pathRank<3)throw Error('Недопустимый эффект достоинства.');
  const cost=choice.damage+Number(choice.ignoreArmor);if(cost>u.wp)throw Error('Недостаточно силы воли.');
  u.wp-=cost;const power={...choice,damage:choice.damage+(choice.damage&&u.kin==='halfelf'?1:0)};
  if(cost){const text=`${u.name}: СВ −${cost}${power.ignoreArmor?', броня игнорируется':''}${power.damage?`, урон +${power.damage}`:''}.`;s.log.push(text);s.commandLog.push(text);}
  return power;
 };
 try{execute(s,replay.command,die);}catch(e){if(e!==stop)throw e;}
 delete s.riskCheck;delete s.hitPower;
 const events=s.diceEvents.length,logs=s.commandLog.length;
 s.diceEvents=s.diceEvents.slice(replay.events);s.commandLog=s.commandLog.slice(replay.logs);
 if(s.pendingRisk){replay.events=events;replay.logs=logs;s.pendingRisk.replay=replay;}
 s.log=s.log.slice(-300);return s;
}
