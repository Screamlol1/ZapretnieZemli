const shuffle=(cards,d)=>{for(let i=cards.length-1;i>0;i--){const j=d(i+1)-1;[cards[i],cards[j]]=[cards[j],cards[i]];}return cards;};
const log=(b,t)=>{b.log.push(t);b.commandLog?.push(t);};
export function initiative(b,c,d){
 if(c.action==='start'){
  if(b.phase!=='setup'||b.initiativeDraw)throw Error('Инициатива уже разыгрывается.');
  b.initiativeDraw={remaining:b.units.map(u=>u.id),deck:shuffle(Array.from({length:10},(_,i)=>i+1),d)};
 }else if(c.action==='initiativeChoose'){
  const draw=b.initiativeDraw;if(!draw||c.unit!==draw.actor||!draw.offered.includes(c.card))throw Error('Эта карта инициативы недоступна.');
  const u=b.units.find(u=>u.id===draw.actor);u.initiative=c.card;
  draw.deck=shuffle([...draw.deck,...draw.offered.filter(n=>n!==c.card)],d);draw.remaining.shift();delete draw.offered;
  log(b,`${u.name}: инициатива ${c.card}.`);
 }else if(c.action==='initiativeSurprise'){
  if(b.phase!=='setup'||b.initiativeDraw||typeof c.value!=='boolean')throw Error('Внезапность задаётся до инициативы.');
  const u=b.units.find(u=>u.id===c.unit);if(!u)throw Error('Боец не найден.');u.surprise=c.value;return;
 }else if(c.action==='initiativeOffer'||c.action==='initiativeAccept'){
  if(b.phase!=='combat'||b.turn!==0||b.roundStarted||b.pendingRisk)throw Error('Обмен возможен только до первого действия раунда.');
  if(c.action==='initiativeOffer'){
   const a=b.units.find(u=>u.id===c.unit),z=b.units.find(u=>u.id===c.target);
   if(!a||!z||a.id===z.id||a.kind!=='pc'||z.kind!=='pc'||a.team!==z.team)throw Error('Обмен: два героя одного отряда, способные разговаривать.');
   b.initiativeOffer={from:a.id,to:z.id};return;
  }
  const offer=b.initiativeOffer;if(!offer||c.unit!==offer.to)throw Error('Нет предложения обмена этому герою.');
  const a=b.units.find(u=>u.id===offer.from),z=b.units.find(u=>u.id===offer.to);[a.initiative,z.initiative]=[z.initiative,a.initiative];delete b.initiativeOffer;
  b.order=[...b.units].sort((a,z)=>a.initiative-z.initiative).map(u=>u.id);log(b,`${a.name} и ${z.name} обменялись инициативой.`);return;
 }else throw Error('Неизвестное действие инициативы.');
 const draw=b.initiativeDraw;
 while(draw.remaining.length){
  const u=b.units.find(u=>u.id===draw.remaining[0]),count=Math.min(draw.deck.length,1+(u.talents?.lightning||0)+(u.surprise?1:0));
  draw.actor=u.id;draw.offered=draw.deck.splice(0,count);
  if(count>1)return;
  u.initiative=draw.offered[0];draw.remaining.shift();log(b,`${u.name}: инициатива ${u.initiative}.`);
 }
 delete b.initiativeDraw;b.order=[...b.units].sort((a,z)=>a.initiative-z.initiative).map(u=>u.id);b.phase='combat';b.round=1;b.turn=0;b.roundStarted=false;
 log(b,'Бой начался. Инициатива сохраняется между раундами.');
}
