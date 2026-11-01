import {activeUnit,isAlive,hexDistance,weaponFor} from './tools/battle-rules.js';
import {pathRank,spendWillpower} from './combat-abilities.js';
import {rank} from './battle-talents.js';
import {available,closeAction,speed} from './battle-close-actions.js';
export const CARD_ACTIONS={strike:['slash','stab','punch','grapple'],defend:['dodge','dodgeStand','weapon','shield'],prepare:['draw','swing','stand'],hinder:['shove','disarm'],maneuver:['feint','retreat'],await:['await']};
export const CARD_NAMES={strike:'Удар',defend:'Защита',prepare:'Подготовка',hinder:'Помеха',maneuver:'Манёвр',await:'Ожидание',double:'Повтор'};
const log=(b,t)=>{b.log.push(t);b.commandLog?.push(t);};
const actors=x=>[x.attacker,x.defender];
export const cardAt=(x,id)=>{const cards=x.choices[id];return cards?.[x.step]==='double'?cards[0]:cards?.[x.step];};
function reveal(x){if(actors(x).every(id=>x.choices[id])){x.stage='attacker';x.actions={};}}
function refreshInsight(x){const i=x.insight;if(i&&x.choices[i.opponent]&&i.rank>=3)i.revealed=x.choices[i.opponent].map((card,index)=>({index,card}));}
export function cardCommand(b,c,d){
 if(c.action==='cardEnable'){
  if(b.cardExchange||b.pendingRisk||typeof c.value!=='boolean')throw Error('Сначала завершите текущую комбинацию.');b.settings.hiddenCombinations=c.value;return;
 }
 if(c.action==='cardStart'){
  const a=activeUnit(b),v=b.units.find(u=>u.id===c.target);
  if(!b.settings.hiddenCombinations||b.phase!=='combat'||b.cardExchange||b.pendingRisk||b.tacticalReactions?.length)throw Error('Мастер должен разрешить скрытые комбинации, а текущий выбор нужно завершить.');
  if(!a||!v||a.id!==c.unit||a.team===v.team||!isAlive(a)||!isAlive(v)||a.monster||v.monster||a.grappling||a.grappledBy||v.grappling||v.grappledBy)throw Error('Скрытые комбинации доступны двум действующим обычным противникам.');
  if(!a.fast&&!a.slow||!v.fast&&!v.slow)throw Error('У обеих сторон должно оставаться хотя бы одно действие.');
  if(hexDistance(a,v)>(weaponFor(a).near?2:1)||hexDistance(a,v)>(weaponFor(v).near?2:1))throw Error('Оба противника должны находиться в досягаемости оружия друг друга.');
  b.cardExchange={id:crypto.randomUUID(),attacker:a.id,defender:v.id,steps:a.fast+a.slow>=2?2:1,step:0,stage:'choose',choices:{},actions:{},history:[]};
  log(b,`${a.name} и ${v.name}: скрытая комбинация, ${b.cardExchange.steps} шага.`);return;
 }
 const x=b.cardExchange;if(!x||c.exchange!==x.id)throw Error('Эта комбинация уже завершена или изменена.');
 const u=b.units.find(u=>u.id===c.unit),other=b.units.find(u=>u.id===actors(x).find(id=>id!==c.unit));
 if(!u||!actors(x).includes(u.id))throw Error('Выберите участника этой комбинации.');
 if(c.action==='cardCancel'){
  if(typeof c.note!=='string'||!c.note.trim()||c.note.length>500)throw Error('Укажите причину отмены Мастером.');
  log(b,'Скрытая комбинация отменена Мастером: '+c.note.trim());delete b.cardExchange;return;
 }
 if(c.action==='cardInsight'){
  const n=pathRank(u,'enemy');if(!n||x.stage!=='choose'||x.choices[u.id]||x.insight)throw Error('Путь врага применяется до выбора собственной комбинации; сначала завершите уже заявленный просмотр.');
  spendWillpower(u,b,1);x.insight={actor:u.id,opponent:other.id,rank:n,revealed:[]};refreshInsight(x);return;
 }
 if(c.action==='cardPeek'){
  const i=x.insight;if(!i||x.stage!=='choose'||!x.choices[i.opponent]||i.revealed.length||u.id!==(i.rank===1?i.opponent:i.actor)||!Number.isInteger(c.index)||c.index<0||c.index>=x.steps)throw Error('Этот выбор раскрываемой карты недоступен.');
  i.revealed=[{index:c.index,card:x.choices[i.opponent][c.index]}];return;
 }
 if(c.action==='cardChoose'){
  if(x.stage!=='choose'||x.choices[u.id])throw Error('Комбинация уже зафиксирована.');
  if(x.insight?.actor===u.id&&!x.insight.revealed.length)throw Error('Сначала противник должен выбрать комбинацию и раскрыть карту Пути врага.');
  const cards=c.cards;if(!Array.isArray(cards)||cards.length!==x.steps||cards.some(k=>!Object.hasOwn(CARD_NAMES,k))||cards[0]==='double'||cards.length===2&&cards[0]===cards[1])throw Error('Выберите разные категории; для повторения первой используйте карту «Повтор» вторым шагом.');
  const effective=cards.map((k,i)=>k==='double'?cards[0]:k),used=effective.filter(k=>k!=='await').length;
  if(used>u.fast+u.slow)throw Error('Потраченные действия заменяются картой «Ожидание».');
  if(u.id===x.attacker&&effective.every(k=>k==='await'))throw Error('Атакующий должен выбрать хотя бы одно действие.');
  x.choices[u.id]=[...cards];refreshInsight(x);reveal(x);return;
 }
 if(c.action==='cardDeclare'){
  const expected=x.stage==='attacker'?x.attacker:x.stage==='defender'?x.defender:null;
  if(u.id!==expected)throw Error('Сначала конкретное действие объявляет атакующий, затем защитник.');
  const category=cardAt(x,u.id),allowed=CARD_ACTIONS[category]||[];
  const forfeited=c.choice==='await'&&!allowed.includes('await')&&allowed.every(choice=>available(b,u,other,choice));
  if(!forfeited&&!allowed.includes(c.choice))throw Error('Действие не относится к открытой карте.');
  const reason=available(b,u,other,c.choice);if(reason)throw Error(reason);
  if(c.choice==='retreat'&&(!Number.isInteger(c.q)||!Number.isInteger(c.r)))throw Error('Выберите соседний гекс для отступления.');
  x.actions[u.id]={action:c.choice,forfeit:forfeited,...(c.choice==='retreat'?{q:c.q,r:c.r}:{})};x.stage=u.id===x.attacker?'defender':'resolve';return;
 }
 if(c.action!=='cardResolve'||x.stage!=='resolve'||u.id!==x.attacker)throw Error('Этап пока нельзя разрешить.');
 const a=b.units.find(u=>u.id===x.attacker),v=b.units.find(u=>u.id===x.defender),aa=x.actions[a.id],va=x.actions[v.id],aDefense=CARD_ACTIONS.defend.includes(aa.action),vDefense=CARD_ACTIONS.defend.includes(va.action),attacks=['slash','stab','punch','grapple','shove','disarm'];
 const oldDefense=[a.defense,v.defense],before=v.str;a.defense=aDefense?aa.action:'none';v.defense=vDefense?va.action:'none';
 try{
  for(const fighter of [a,v])if(x.actions[fighter.id].forfeit){if(fighter.fast)fighter.fast--;else fighter.slow=Math.max(0,fighter.slow-1);log(b,`${fighter.name}: ни одно действие открытой категории недоступно, действие потрачено.`);}
  if(!(aDefense&&attacks.includes(va.action)))closeAction(b,a,v,aa.action,aa,d);
  const damage=Math.max(0,before-v.str),pain=rank(v,'pain'),lost=!vDefense&&va.action!=='await'&&damage>(pain>=2?Infinity:pain>=1?1:0);
  if(lost){const cost=speed(v,va.action);if(cost==='slow')v.slow=Math.max(0,v.slow-1);else if(v.fast)v.fast--;else v.slow=Math.max(0,v.slow-1);log(b,`${v.name}: действие шага потеряно из-за боли (${damage} урона).`);}
  else if(!(vDefense&&attacks.includes(aa.action))&&isAlive(v)&&b.phase==='combat'){
   const why=available(b,v,a,va.action);
   if(why){const cost=speed(v,va.action);if(cost==='slow')v.slow=Math.max(0,v.slow-1);else if(v.fast)v.fast--;else v.slow=Math.max(0,v.slow-1);log(b,`${v.name}: заявленное действие сорвано: ${why}`);}
   else closeAction(b,v,a,va.action,va,d);
  }
 }finally{a.defense=oldDefense[0];v.defense=oldDefense[1];}
 x.history.push({step:x.step+1,attacker:aa.action,defender:va.action});
 if(++x.step>=x.steps||b.phase!=='combat'||!isAlive(a)||!isAlive(v)||hexDistance(a,v)>Math.max(weaponFor(a).near?2:1,weaponFor(v).near?2:1)){
  b.lastCardExchange={attacker:a.id,defender:v.id,history:x.history};delete b.cardExchange;log(b,'Скрытая комбинация завершена. Дополнительные атаки достоинств выполняются отдельно.');
 }else{x.stage='attacker';x.actions={};}
}
