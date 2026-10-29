export function injuryEffects(u){
 const total={modifiers:{},attributeModifiers:{},runSlow:false,noTwoHand:false,damageSkills:[],incapacitated:!!(u.dead||u.meditating),paralyzed:false};
 for(const i of u.injuries||[]){if(i.status==='fatal'||i.overdue){total.incapacitated=true;continue;}if(i.status!=='active')continue;const m=i.mechanics||{};
  for(const field of ['modifiers','attributeModifiers'])for(const [key,n] of Object.entries(m[field]||{}))total[field][key]=(total[field][key]||0)+n;
  for(const k of ['runSlow','noTwoHand','incapacitated','paralyzed'])total[k]||=!!m[k];
  total.damageSkills.push(...m.damageSkills||[]);
 }return total;
}
export const injuryPenalty=(u,skill,attribute)=>(injuryEffects(u).modifiers[skill]||0)+(injuryEffects(u).attributeModifiers[attribute==='wits'?'wit':attribute]||0);
export function injuryAfterCheck(s,u,skill){const pain=injuryEffects(u).damageSkills.filter(k=>k===skill).length;if(pain&&u.str>0){u.str=Math.max(0,u.str-pain);const line=`${u.name}: травмы, Телосложение −${pain} после проверки.`;s.log.push(line);s.commandLog?.push(line);}}
export function injuryEvent(s,u,attribute,table,source='attack'){s.injuryEvents??=[];s.injuryEvents.push({...(s.injuryCommandId?{id:s.injuryCommandId+':'+s.injuryEvents.length}:{}),character:u.id,attribute:attribute==='wits'?'wit':attribute,table,source});}
