import {riskAction} from './dice-risk.js';
// Latest actionable event per roll, never a newer unrelated person's roll.
export function pendingDice(s){
 if(!s)return [];
 return [...(s.diceRolls||[])].reverse().filter(e=>riskAction(s,e));
}
export function decisionEvent(s,{event,roll}={}){
 const events=(s?.diceRolls||[]).filter(e=>!e.private||s.me.role==='gm');
 if(event)return events.find(e=>e.id===event)||null;
 if(roll)return [...events].reverse().find(e=>e.risk?.roll===roll)||null;
 const active=s?.afflictionCheck?.id||s?.expeditionCheck?.id||s?.waterCheck?.id||s?.coldCheck?.id||s?.combat?.pendingRisk?.id||s?.journeyRisk?.id||s?.treatment?.roll?.id;
 return (active&&[...events].reverse().find(e=>e.risk?.roll===active))||pendingDice(s)[0]||events.at(-1)||null;
}
