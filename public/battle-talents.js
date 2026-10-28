export const rank=(u,id)=>u.talents?.[id]||0;
export function weaponTalent(u,type){return type==='shove'&&!['axe','halberd','staff'].includes(u.weapon)?null:type==='punch'?'brawler':type==='shoot'?'sharp':({sword:'sword',greatsword:'sword',axe:'axe',mace:'hammer',staff:'hammer',dagger:'knife',spear:'spear',halberd:'spear'})[u.weapon];}
export function attackTalents(u,v,type,d){
 const id=weaponTalent(u,type),n=rank(u,id),dragon=v.monster?rank(u,'dragon'):0;
 return {bonus:(n?1:0)+(dragon?1:0),damage:dragon>=2?1:0,artifacts:[...(n>=3?[{sides:8,value:d(8)}]:[]),...(dragon>=3?[{sides:8,value:d(8)}]:[])],name:id};
}
export function defenseCost(u,mode){
 const dodge=mode.startsWith('dodge'),key=dodge?'dodges':'parries',n=rank(u,dodge?'fastfoot':'defender'),used=u.reactions?.[key]||0;
 return {key,free:n>=3||n>=1&&used===0,bonus:n>=2?1:0};
}
export function extraAttackAllowed(u,type){return !u.fast&&!u.slow&&u.wp>=1&&u.path===(type==='shoot'?'arrow':'blade')&&u.pathRank>=2;}
export const powerAllowed=(u,type)=>u.path===(type==='shoot'?'arrow':'blade')&&u.pathRank>=1&&u.wp>0;
