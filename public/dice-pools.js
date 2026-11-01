// Agreed table rule: keep skill/bonus dice and roll penalties separately.
import {artifactTotal} from './equipment-dice.js';
export function skillCounts(skill,...modifiers){return {skill:skill+modifiers.reduce((n,m)=>n+Math.max(0,m),0),penalty:modifiers.reduce((n,m)=>n+Math.max(0,-m),0)};}
const sixes=values=>(values||[]).filter(v=>v===6).length;
export function poolScore(p){
 // Legacy saved rolls retain their original sign when replayed or pushed.
 const positive=sixes(p.base)+sixes(p.gear)+(p.negative?0:sixes(p.skill))+artifactTotal(p.artifact);
 const penalty=sixes(p.penalty)+(p.negative?sixes(p.skill):0);
 return {positive,penalty,hits:Math.max(0,positive-penalty)};
}
export function rollPool(base,skill,gear,modifiers,d){
 const counts=skillCounts(skill,...(Array.isArray(modifiers)?modifiers:[modifiers]));
 const roll=n=>Array.from({length:Math.max(0,n)},()=>d(6));
 return {base:roll(base),skill:roll(counts.skill),gear:roll(gear),penalty:roll(counts.penalty),negative:false,poolRule:'separate-penalties-v1'};
}
export function scoreText(p){const s=poolScore(p);return s.penalty?`Успехов: ${s.positive} − ${s.penalty} = ${s.hits}.`:`Успехов: ${s.hits}.`;}
export function canPushPool(p){return ['base','skill','gear','penalty'].some(k=>(p[k]||[]).some(v=>v!==6&&(['skill','penalty'].includes(k)||v!==1)))||(p.artifact||[]).some(a=>a.value<6);}
export function pushPool(p,die){
 p.held={};for(const key of ['base','skill','gear','penalty']){p.held[key]=(p[key]||[]).map(v=>v===6||!['skill','penalty'].includes(key)&&v===1);p[key]=(p[key]||[]).map((v,i)=>p.held[key][i]?v:die(6));}
 p.held.artifact=(p.artifact||[]).map(a=>a.value>=6);for(const a of p.artifact||[])if(a.value<6)a.value=die(a.sides);
 return {damage:p.base.filter(v=>v===1).length,wear:p.gear.filter(v=>v===1).length};
}
