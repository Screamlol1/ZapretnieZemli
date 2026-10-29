import {pathRank,willpowerAvailable} from './combat-abilities.js';
export const rank=(u,id)=>u.talents?.[id]||0;
export function weaponTalent(u,type){return type==='shove'&&!['axe','halberd','staff'].includes(u.weapon)?null:type==='punch'?'brawler':type==='shoot'?'sharp':({sword:'sword',greatsword:'sword',axe:'axe',mace:'hammer',staff:'hammer',dagger:'knife',spear:'spear',halberd:'spear'})[u.weapon];}
export function attackTalents(u,v,type,d){
 const id=weaponTalent(u,type),n=rank(u,id),dragon=v.monster?rank(u,'dragon'):0;
 return {bonus:(n?1:0)+(dragon?1:0)+(u.prey?.target===v.id&&v.str>0&&v.agi>0&&v.wits>0&&v.emp>0?u.prey.bonus:0),damage:dragon>=2?1:0,artifacts:[...(n>=3?[{sides:8,value:d(8)}]:[]),...(dragon>=3?[{sides:8,value:d(8)}]:[])],name:id};
}
export function defenseCost(u,mode){
 const dodge=mode.startsWith('dodge'),key=dodge?'dodges':'parries',n=rank(u,dodge?'fastfoot':'defender'),used=u.reactions?.[key]||0;
 return {key,free:n>=3?used>0:n>=1&&used===0,bonus:n>=2?1:0};
}
export function extraAttackAllowed(u,type,b={round:0}){return !u.fast&&!u.slow&&willpowerAvailable(u,b)>=1&&pathRank(u,type==='shoot'?'arrow':'blade')>=2;}
export const powerAllowed=(u,type,b={round:0})=>pathRank(u,type==='shoot'?'arrow':'blade')>=1&&willpowerAvailable(u,b)>0;
