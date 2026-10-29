export const pathRank=(u,id)=>u.npc&&u.npcTalentsConfigured!==true?0:u.paths?.[id]??(u.path===id?u.pathRank||0:0);
export const willpowerAvailable=(u,b)=>u.dead||u.meditating||u.injuries?.some(i=>i.overdue)?0:u.npc?(u.talentUsedRound===b.round?0:1):u.wp||0;
export function spendWillpower(u,b,amount){
 if(!Number.isInteger(amount)||amount<1||amount>willpowerAvailable(u,b))throw Error(u.npc?'ПВ может активировать достоинство один раз за раунд с силой 1 СВ.':'Недостаточно силы воли.');
 if(u.npc)u.talentUsedRound=b.round;else u.wp-=amount;
 return amount+(u.kin==='halfelf'?1:0);
}
export function kinAbility(b,c){
 if(b.phase!=='combat'||b.pendingRisk||b.pendingMishap)throw Error('Способность доступна в бою после завершения текущего решения.');
 const u=b.units.find(u=>u.id===c.unit);if(!u||u.monster)throw Error('Персонаж не найден.');
 let text;
 if(c.ability==='prey'){
  if(u.kin!=='wolfkin'||b.order[b.turn]!==u.id||u.str<=0||u.agi<=0||u.wits<=0||u.emp<=0)throw Error('Выбор добычи доступен ходящему волколаку.');
  const target=b.units.find(v=>v.id===c.target);if(!target||target.dead||target.team===u.team||target.str<=0||c.visible!==true)throw Error('Выберите противника и подтвердите, что он виден или его запах доступен.');
  if(u.prey?.target===target.id)throw Error('Этот противник уже выбран добычей.');
  const bonus=spendWillpower(u,b,c.wp);u.prey={target:target.id,bonus,days:bonus};
  text=`${u.name}: добыча — ${target.name}, +${bonus} к атакам до сломленности добычи или отказа; след по запаху ${bonus} сут.`;
 }else if(c.ability==='orc'){
  const window=b.manualOrcWindow,attribute=c.attribute;
  if(u.kin!=='orc'||window?.actor!==u.id||window.attribute!==attribute||!['str','agi','wits','emp'].includes(attribute)||u[attribute]!==0)throw Error('Немедленный выбор Несокрушимости уже завершён.');
  const maximum=u[({str:'maxStr',agi:'maxAgi',wits:'maxWits',emp:'maxEmp'})[attribute]];
  if(!Number.isInteger(c.wp)||c.wp<1||c.wp>maximum)throw Error('Выберите допустимое восстановление.');
  spendWillpower(u,b,c.wp);u[attribute]=c.wp;u.prone=false;delete b.manualOrcWindow;
  text=`${u.name}: Несокрушимость, ${attribute} +${c.wp}; травмы сохраняются.`;
 }else if(c.ability==='releasePrey'){
  if(u.kin!=='wolfkin'||!u.prey)throw Error('Добыча не выбрана.');delete u.prey;text=`${u.name} отпускает добычу.`;
 }else throw Error('Неизвестная способность народа.');
 b.commandLog?.push(text);b.log.push(text);
}
export const kinNames={human:'Гибкость',elf:'Внутренний покой',halfelf:'Сила духа',dwarf:'Упорство',halfling:'Неуловимость',wolfkin:'Охотничий инстинкт',orc:'Несокрушимость',goblin:'Ночное зрение'};

export function endPreyOnBroken(b,target){if(target.dead||['str','agi','wits','emp'].some(k=>target[k]===0))for(const u of b.units)if(u.prey?.target===target.id)delete u.prey;}
