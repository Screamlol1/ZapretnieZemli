export const artifactHits=v=>v>=6?Math.floor(v/2)-2:0;
export const rollArtifact=(sides,d)=>[8,10,12].includes(sides)?[{sides,value:d(sides)}]:[];
export const artifactTotal=rolls=>(rolls||[]).reduce((n,r)=>n+artifactHits(r.value),0);
export function protection(u,damage,d){
 const sources=u.armorSources?.length?u.armorSources:null;
 const groups=sources?sources.map(p=>({source:p,dice:Array.from({length:p.current},()=>d(6)),artifact:rollArtifact(p.artifact,d)})):[{dice:Array.from({length:u.armor},()=>d(6)),artifact:[]}];
 const dice=groups.flatMap(g=>g.dice),artifacts=groups.flatMap(g=>g.artifact),stopped=dice.filter(v=>v===6).length+artifactTotal(artifacts),taken=Math.max(0,damage-stopped);
 if(taken){for(const g of groups)if(g.source)g.source.current=Math.max(0,g.source.current-g.dice.filter(v=>v===1).length);u.armor=sources?sources.reduce((n,p)=>n+p.current,0):Math.max(0,u.armor-dice.filter(v=>v===1).length);}
 return {dice,artifacts,stopped,taken};
}
