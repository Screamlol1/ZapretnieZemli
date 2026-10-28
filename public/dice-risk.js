export function riskAction(s,e){
 const r=e?.risk;if(!r||!s)return null;
 const c=s.characters.find(c=>c.id===r.character),gm=s.me.role==='gm';
 if(r.action==='free')return (gm&&e.private||r.owner===s.me.owner)&&s.freeRisk?.roll===r.roll?{action:'freePush',roll:r.roll}:null;
 if(!c||!gm&&(c.owner!==s.me.owner||c.kind!=='pc')||e.private&&!gm)return null;
 if(r.action==='opposed'){
  const pair=s.opposedChecks?.find(p=>p.id===r.opposed),check=e.private?s.gmChecks?.[c.id]:c.runtime?.lastCheck;
  return pair&&!pair.done&&pair.attacker.rolled&&pair.defender.rolled&&check?.id===r.roll?{action:'opposedPush',id:r.opposed}:null;
 }
 if(r.action==='combat')return s.combat?.pendingRisk?.id===r.roll?{action:'combatAction',revision:s.combatRevision,command:{action:'risk',roll:r.roll,push:true}}:null;
 if(r.action==='journey')return s.journeyRisk?.id===r.roll?{action:'travelRisk',roll:r.roll,push:true}:null;
 if(r.action==='character'){
  const check=e.private?s.gmChecks?.[c.id]:c.runtime?.lastCheck;
  if(check?.id!==r.roll||check.pushed||check.accepted||['setup','combat'].includes(s.combat?.phase)&&s.combat.units.some(u=>u.id===c.id)||s.journey.phase==='resolving'&&s.journey.party.includes(c.id))return null;
  return {action:'characterPush',character:c.id,roll:r.roll};
 }
 return null;
}
