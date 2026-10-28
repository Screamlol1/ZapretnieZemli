// Capture already resolved rolls; this module never draws random numbers.
const names={base:'Характеристика',skill:'Навык',gear:'Снаряжение',artifact:'Артефакт',armor:'Броня',cover:'Укрытие',magic:'Магия',table:'Таблица',monster:'Чудовище'};
export const diceGroup=(kind,values,sides=6,negative=false)=>({kind,label:names[kind],values:[...values],sides,negative});
export function traceDice(s,u,label,groups,result){
 if(!s.diceEvents)return; // Standalone sandbox keeps its existing journal.
 s.diceEvents.push({name:u.name,label,groups:structuredClone(groups.filter(g=>g.values.length)),result});
}
export function tracePool(s,u,label,p){
 const groups=[diceGroup('base',p.base),diceGroup('skill',p.skill,6,p.negative),diceGroup('gear',p.gear),...(p.artifact||[]).map(a=>diceGroup('artifact',[a.value],a.sides))];
 for(const [i,g] of groups.entries())g.held=i<3?(p.held?.[['base','skill','gear'][i]]||[]):[p.held?.artifact?.[i-3]||false];
 const hits=Math.max(0,p.base.filter(v=>v===6).length+p.gear.filter(v=>v===6).length+p.skill.filter(v=>v===6).length*(p.negative?-1:1)+(p.artifact||[]).reduce((n,a)=>n+Math.max(0,Math.floor(a.value/2)-2),0));
 traceDice(s,u,label,groups,`Успехов: ${hits}.`);
}
