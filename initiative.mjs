import {initiativeSlots,sortInitiative,assignInitiativeCard,npcSignature} from './public/battle-initiative.js';
const shuffle=(cards,d)=>{for(let i=cards.length-1;i>0;i--){const j=d(i+1)-1;[cards[i],cards[j]]=[cards[j],cards[i]];}return cards;};
const log=(b,t)=>{b.log.push(t);b.commandLog?.push(t);};
export function initiative(b,c,d){
 if(c.action==='initiativeGroupNext'){
  const current=b.activationOrder?.[b.turn],slot=b.initiativeSlots?.find(slot=>slot.key===current?.key);
  if(b.phase!=='combat'||b.activationStarted||!slot?.group)throw Error('Порядок группы меняется перед первым действием текущего бойца.');
  const from=slot.members.indexOf(current.unit),to=slot.members.indexOf(c.target);
  if(to<from||!b.units.some(u=>u.id===c.target&&!u.dead&&u.str>0&&u.agi>0&&u.wits>0&&u.emp>0))throw Error('Выберите ещё не ходившего действующего участника этой группы.');
  [slot.members[from],slot.members[to]]=[slot.members[to],slot.members[from]];sortInitiative(b);log(b,'Мастер выбрал следующего участника группы: '+b.units.find(u=>u.id===c.target).name+'.');return;
 }
 if(c.action==='initiativeConfigure'){
  if(b.phase!=='setup'||b.initiativeDraw)throw Error('Группы меняются до розыгрыша инициативы.');
  const u=b.units.find(u=>u.id===c.unit);if(!u)throw Error('Боец не найден.');
  if(typeof c.group!=='string'||typeof c.sharedHeroes!=='boolean'||!Number.isInteger(c.activations))throw Error('Укажите группу и количество активаций.');
  u.initiativeGroup=c.group.trim();u.activations=c.activations;b.settings.sharedHeroInitiative=c.sharedHeroes;initiativeSlots(b);return;
 }
 if(c.action==='initiativeAutogroup'){
  if(b.phase!=='setup'||b.initiativeDraw)throw Error('Группы меняются до розыгрыша инициативы.');
  const groups=new Map();let count=0;
  for(const u of b.units.filter(u=>u.kind!=='pc'&&!u.monster)){const key=npcSignature(u);if(!groups.has(key))groups.set(key,'ПВ '+(++count));u.initiativeGroup=groups.get(key);}
  initiativeSlots(b);return;
 }
 if(c.action==='start'){
  if(b.phase!=='setup'||b.initiativeDraw)throw Error('Инициатива уже разыгрывается.');
  b.initiativeSlots=initiativeSlots(b);if(b.initiativeSlots.length>10)throw Error(`Нужно ${b.initiativeSlots.length} карт, в колоде 10. Объедините одинаковых ПВ; для большого отряда доступна явная настройка общей карты героев.`);
  for(const u of b.units){delete u.initiative;delete u.initiativeCards;}
  b.initiativeDraw={remaining:b.initiativeSlots.map(s=>s.key),deck:shuffle(Array.from({length:10},(_,i)=>i+1),d)};
 }else if(c.action==='initiativeChoose'){
  const draw=b.initiativeDraw;if(!draw||c.unit!==draw.actor||!draw.offered.includes(c.card))throw Error('Эта карта инициативы недоступна.');
  const slot=b.initiativeSlots.find(s=>s.key===draw.remaining[0]);assignInitiativeCard(b,slot,c.card);
  draw.deck=shuffle([...draw.deck,...draw.offered.filter(n=>n!==c.card)],d);draw.remaining.shift();delete draw.offered;
  log(b,`${slot.group||b.units.find(u=>u.id===draw.actor).name}: инициатива ${c.card}.`);
 }else if(c.action==='initiativeSurprise'){
  if(b.phase!=='setup'||b.initiativeDraw||typeof c.value!=='boolean')throw Error('Внезапность задаётся до инициативы.');
  const u=b.units.find(u=>u.id===c.unit);if(!u)throw Error('Боец не найден.');u.surprise=c.value;return;
 }else if(c.action==='initiativeOffer'||c.action==='initiativeAccept'){
  if(b.phase!=='combat'||b.turn!==0||b.roundStarted||b.pendingRisk)throw Error('Обмен возможен только до первого действия раунда.');
  if(c.action==='initiativeOffer'){
   const a=b.units.find(u=>u.id===c.unit),z=b.units.find(u=>u.id===c.target);
   if(!a||!z||a.id===z.id||a.kind!=='pc'||z.kind!=='pc'||a.team!==z.team)throw Error('Обмен: два героя одного отряда, способные разговаривать.');
   if([a,z].some(u=>b.initiativeSlots?.find(s=>s.members.includes(u.id))?.members.length>1))throw Error('Общая карта принадлежит группе; индивидуальный обмен для неё недоступен.');
   b.initiativeOffer={from:a.id,to:z.id};return;
  }
  const offer=b.initiativeOffer;if(!offer||c.unit!==offer.to)throw Error('Нет предложения обмена этому герою.');
  const a=b.units.find(u=>u.id===offer.from),z=b.units.find(u=>u.id===offer.to);[a.initiative,z.initiative]=[z.initiative,a.initiative];delete b.initiativeOffer;
  if(b.initiativeSlots){const x=b.initiativeSlots.find(s=>s.members.includes(a.id)),y=b.initiativeSlots.find(s=>s.members.includes(z.id));[x.card,y.card]=[y.card,x.card];}
  sortInitiative(b);log(b,`${a.name} и ${z.name} обменялись инициативой.`);return;
 }else throw Error('Неизвестное действие инициативы.');
 const draw=b.initiativeDraw;
 while(draw.remaining.length){
  const slot=b.initiativeSlots.find(s=>s.key===draw.remaining[0]);
  // A voluntary shared hero card uses the best participant's draw, once for the group.
  const u=slot.members.map(id=>b.units.find(u=>u.id===id)).sort((a,z)=>(z.talents?.lightning||0)+Number(!!z.surprise)-(a.talents?.lightning||0)-Number(!!a.surprise))[0];
  const count=Math.min(draw.deck.length,1+(u.talents?.lightning||0)+(u.surprise?1:0));
  draw.actor=u.id;draw.group=slot.group;draw.activation=slot.activation;draw.offered=draw.deck.splice(0,count);
  if(count>1)return;
  assignInitiativeCard(b,slot,draw.offered[0]);draw.remaining.shift();log(b,`${slot.group||u.name}${(u.activations||1)>1?' · активация '+slot.activation:''}: инициатива ${u.initiative}.`);
 }
 delete b.initiativeDraw;sortInitiative(b);b.phase='combat';b.round=1;b.turn=0;b.roundStarted=false;b.activationStarted=false;
 log(b,'Бой начался. Инициатива сохраняется между раундами; участники общей карты ходят последовательно.');
}
