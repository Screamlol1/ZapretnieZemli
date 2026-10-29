import {canPushPool} from './dice-pools.js';
const repeatDwarf=(c,r)=>!!(r?.pushed&&!r.accepted&&c.kind==='pc'&&c.sheet?.kin==='dwarf'&&!c.runtime?.dead&&Object.values(c.runtime?.current||{}).every(n=>n>0)&&c.runtime?.wp>0&&canPushPool({...r,skill:r.skillDice,artifact:[...(r.artifacts||[]),...(r.artifact||[]).map(value=>({sides:r.sides,value}))]}));
export function riskAction(s,e){
 const r=e?.risk;if(!r||!s)return null;
 const c=s.characters.find(c=>c.id===r.character),gm=s.me.role==='gm';
 if(r.action==='free')return (gm&&e.private||r.owner===s.me.owner)&&s.freeRisk?.roll===r.roll?{action:'freePush',roll:r.roll}:null;
 if(!c||!gm&&(c.owner!==s.me.owner||c.kind!=='pc')||e.private&&!gm)return null;
 if(r.action==='opposed'){
  const pair=s.opposedChecks?.find(p=>p.id===r.opposed),check=e.private?s.gmChecks?.[c.id]:c.runtime?.lastCheck;
  if(check?.diceEvent&&check.diceEvent!==e.id)return null;
  const repeat=repeatDwarf(c,check);return pair&&!pair.done&&pair.attacker.rolled&&pair.defender.rolled&&check?.id===r.roll?{action:'opposedPush',id:r.opposed,...(repeat?{kinRepeat:true,kinAttempt:check.kinPushes||0,kinWP:c.runtime.wp}:{}),pushAvailable:!check.pushed||repeat}:null;
 }
 if(r.action==='combat')return s.combat?.pendingRisk?.id===r.roll?{action:'combatAction',revision:s.combatRevision,command:{action:'risk',roll:r.roll,push:true}}:null;
 if(r.action==='journey')return s.journeyRisk?.id===r.roll?{action:'travelRisk',roll:r.roll,push:true}:null;
 if(r.action==='treatment'){const p=s.treatment;return p?.healer===c.id&&p.roll?.id===r.roll?{action:'injury',op:'push',roll:r.roll,pushAvailable:p.roll.pushAvailable!==false&&!p.roll.pushed&&canPushPool({...p.roll,skill:p.roll.skillDice,artifact:p.roll.artifacts})}:null;}
 if(r.action==='repair'){
  const item=s.items?.find(i=>i.id===r.item),p=item?.repair;
  return p?.status==='rolled'&&p.roll?.id===r.roll?{action:'inventoryRepair',op:'push',id:item.id,version:item.version,roll:r.roll,pushAvailable:!p.roll.pushed&&canPushPool({...p.roll,skill:p.roll.skillDice,artifact:p.roll.artifacts})}:null;
 }
 if(r.action==='character'){
  const check=e.private?s.gmChecks?.[c.id]:c.runtime?.lastCheck;
  if(check?.diceEvent&&check.diceEvent!==e.id)return null;
  const repeat=repeatDwarf(c,check);
  if(check?.id!==r.roll||check.pushed&&!repeat||check.accepted||['setup','combat'].includes(s.combat?.phase)&&s.combat.units.some(u=>u.id===c.id)||s.journey.phase==='resolving'&&s.journey.party.includes(c.id))return null;
  return {action:'characterPush',character:c.id,roll:r.roll,...(repeat?{kinRepeat:true,kinAttempt:check.kinPushes||0,kinWP:c.runtime.wp}:{})};
 }
 return null;
}
