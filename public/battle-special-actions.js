import {activeUnit,attack,isAlive,hexDistance,lineOfSight} from './tools/battle-rules.js';
import {rank,weaponTalent} from './battle-talents.js';
export function doubleSlash(b,targets,d){
 const u=activeUnit(b);
 if(!u||weaponTalent(u,'slash')!=='sword'||rank(u,'sword')<2||!u.slow)throw Error('Два рубящих удара требуют меча, ранга 2 и медленного действия.');
 if(!Array.isArray(targets)||targets.length!==2||targets[0]===targets[1])throw Error('Выберите двух разных противников.');
 for(const id of targets){const v=b.units.find(v=>v.id===id);if(!v||v.team===u.team||!isAlive(v)||hexDistance(u,v)!==1||!lineOfSight(b,u,v))throw Error('Оба противника должны быть на расстоянии руки и видны.');}
 const note=`${u.name}: два рубящих удара одним медленным действием.`;b.log.push(note);b.commandLog?.push(note);
 attack(b,targets[0],'slash',{},d);
 if(isAlive(u)&&b.phase==='combat')attack(b,targets[1],'slash',{bonusAttack:true},d);
}
