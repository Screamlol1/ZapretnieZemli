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
