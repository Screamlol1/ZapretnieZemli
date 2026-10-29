import {combatOptions} from './combat-options.js';
import {activeUnit,BATTLE_MAPS,weaponFor,isAlive,canSpend,hexDistance,lineOfSight,movementReason} from './tools/battle-rules.js';
import {rank,weaponTalent,defenseCost,extraAttackAllowed} from './battle-talents.js';
import {paintSprites} from './appearance.js';
import {identityMarkup,controllerIdentity} from './player-identity.js';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const owns=(s,id)=>s.me.role==='gm'||s.characters.some(c=>c.id===id&&c.kind==='pc'&&c.owner===s.me.owner);
function controller(s,u){return controllerIdentity(s,s.characters.find(c=>c.id===u?.id)||u);}
const speedFor=(u,type)=>type==='shove'||type==='punch'&&rank(u,'brawler')>=2||type==='stab'&&weaponTalent(u,type)==='knife'&&rank(u,'knife')>=2?'fast':'slow';
const budget=u=>`<span class="combat-budget ${u.fast?'':'spent'}">Быстрое <b>${u.fast}</b></span><span class="combat-budget ${u.slow?'':'spent'}">Медленное <b>${u.slow}</b></span>`;
export function combatBlockReason(b){
 if(b.initiativeDraw)return 'Сначала выберите карту инициативы.';
 if(b.pendingRisk)return b.pendingRisk.kind==='power'?'Сначала решите, тратить ли силу воли.':'Сначала завершите решение по броску.';
 if(b.pendingTalent)return 'Сначала завершите выбор эффекта достоинства.';
 if(activeUnit(b)?.pendingMove)return 'Сначала выберите последствие перегруза.';
 if(b.pendingMishap)return 'Мастер должен разрешить магическую неудачу.';
 return '';
}
// These hints mirror the existing engine; the server remains authoritative.
export function combatActionReason(s,action,targetId,{extraAttack=false,index='random'}={}){
 const b=s.combat,u=activeUnit(b),v=b.units.find(x=>x.id===targetId),block=combatBlockReason(b);
 if(block)return block;
 if(action==='start')return b.phase!=='setup'?'Бой уже начат.':s.me.role!=='gm'?'Начать бой может Мастер.':'';
 if(b.phase!=='combat')return b.phase==='finished'?'Бой завершён.':'Сначала начните бой.';
 if(!u||!owns(s,u.id))return 'Сейчас действует другой участник.';
 if(action==='end')return '';
 if(!isAlive(u))return 'Боец сломлен.';
 const w=weaponFor(u),attacks=['slash','stab','shoot','punch','shove'];
 if(attacks.includes(action)){
  if(u.monster)return 'Чудовище использует таблицу атак.';
  if(!v||v.team===u.team||!isAlive(v))return 'Выберите действующего противника.';
  if(u.prone&&!['shove','shoot'].includes(action))return 'Сначала встаньте.';
  if(!lineOfSight(b,u,v))return 'Препятствие закрывает цель.';
  const distance=hexDistance(u,v);
  if(action==='shoot'){
   if(!w.ranged)return 'Нужно дальнобойное оружие.';
   if(!u.gear)return 'Оружие повреждено.';
   if(w.crossbow&&!u.ready)return 'Сначала зарядите арбалет.';
   if(u.aim&&distance===1)return 'Прицеливание мешает выстрелу на расстоянии руки.';
   if(distance>w.range)return 'Цель вне дальности оружия.';
  }else{
   if(distance!==1&&!(w.near&&distance===2))return 'Подойдите к цели ближе.';
   if(action==='slash'&&!w.slash||action==='stab'&&!w.stab)return 'Оружие не подходит для этой атаки.';
   if(!['punch','shove'].includes(action)&&!u.gear)return 'Оружие повреждено.';
  }
  if(extraAttack)return extraAttackAllowed(u,action)&&action!=='shove'?'':'Нужны ранг 2 Пути, 1 СВ и израсходованные действия.';
  return canSpend(u,speedFor(u,action))?'':`Нет ${speedFor(u,action)==='slow'?'медленного':'быстрого или медленного'} действия.`;
 }
 if(action==='monsterAttack'){
  if(!u.monster)return 'Выберите чудовище.';
  if(!u.slow)return 'Нет медленного действия.';
  if(!v||v.team===u.team||!isAlive(v))return 'Выберите действующего противника.';
  if(!lineOfSight(b,u,v))return 'Препятствие закрывает цель.';
  const attacks=u.monster.attacks||[],attack=index==='random'?null:attacks[Number(index)];
  if(attack?.type==='manual')return 'Этот эффект разрешает Мастер кнопкой «Магия / особый эффект».';
  if(attack?.type==='fear'&&v.monster)return 'Чудовища невосприимчивы к страху.';
  if(attack?hexDistance(u,v)>attack.range:attacks.length&&attacks.every(a=>hexDistance(u,v)>a.range))return 'Цель вне дальности атаки чудовища.';
  return '';
 }
 if(action==='manualMagic')return s.me.role!=='gm'?'Решение принимает Мастер.':!u.slow?'Нет медленного действия.':'';
 if(action==='ready'){
  if(!w.crossbow)return 'Перезарядка нужна арбалету.';
  if(!u.gear)return 'Оружие повреждено.';
  if(u.ready)return 'Арбалет уже заряжен.';
 }
 if(action==='aim'){
  if(!w.ranged)return 'Нужно дальнобойное оружие.';
  if(w.crossbow&&!u.ready)return 'Сначала зарядите арбалет.';
  if(u.aim)return 'Боец уже прицелился.';
 }
 if(action==='swing'&&(!w.heavy||!u.gear))return 'Нужно исправное тяжёлое оружие.';
 if(action==='cover'&&b.terrain[`${u.q},${u.r}`]!=='forest')return 'В этом гексе нет дерева для укрытия.';
 if(action==='extinguish'&&!u.burning)return 'Боец не горит.';
 const speed=['ready','extinguish'].includes(action)?'slow':'fast';
 return canSpend(u,speed)?'':`Нет ${speed==='slow'?'медленного':'быстрого или медленного'} действия.`;
}
export function combatUI(getState,act){
 const root=document.createElement('section');root.id='online-combat';document.getElementById('table').append(root);
 let last='',target='',selected='',lastEvent=null,lastActive='',retreat=false;
 function render(){
  const s=getState();if(!s)return;const b=s.combat,gm=s.me.role==='gm';root.dataset.combatRevision=String(s.combatRevision||0);
  const signature=JSON.stringify([b,s.combatRevision,s.characters.map(c=>[c.id,c.name,c.kind,c.hidden,c.owner,c.visual]),s.members,s.owners,s.me]);if(signature===last)return;last=signature;
  if(!b){root.innerHTML=`<h2>Общий бой</h2>${gm?`<p>Выберите 2–10 открытых персонажей и назначьте отряды. Проверьте характеристики и экипировку перед боем.</p><div class="combat-roster">${s.characters.filter(c=>!c.hidden).map(c=>`<label>${esc(c.name)}<select data-roster="${esc(c.id)}"><option value="">Не участвует</option><option value="A">Отряд A</option><option value="B">Отряд B</option></select></label>`).join('')}</div><label>Поле боя<select id="combat-map">${Object.entries(BATTLE_MAPS).map(([id,m])=>`<option value="${id}">${esc(m.name)}</option>`).join('')}</select></label><button data-combat-create>Подготовить бой</button>`:'<p>Мастер готовит поле и участников боя. Здесь появятся очередь инициативы и текущий шаг.</p>'}`;return;}
  const active=activeUnit(b);
  if(active?.id&&active.id!==lastActive)selected=active.id;lastActive=active?.id||'';
  const chosen=b.units.find(u=>u.id===selected)||active||b.units[0];selected=chosen.id;
  const event=b.event&&b.event.id!==lastEvent&&Date.now()/1000-b.event.time<10?b.event:null;if(b.event)lastEvent=b.event.id;
  const turn=active&&owns(s,active.id),mine=owns(s,chosen.id),block=combatBlockReason(b);
  const enemies=b.units.filter(u=>u.team!==active?.team&&isAlive(u));if(!enemies.some(u=>u.id===target))target=enemies[0]?.id||'';
  const order=b.order.length?b.order.map(id=>b.units.find(u=>u.id===id)).filter(Boolean):b.units;
  const future=active?Array.from({length:order.length-1},(_,i)=>order[(b.turn+i+1)%order.length]).filter(isAlive):[];
  const next=b.phase==='combat'?future[0]:null,nextRound=next&&order.indexOf(next)<=b.turn;
  let stage='turn',heading='Ход персонажа',text='Выберите цель и действие или соседний гекс для движения.',actor=active,primary='actions',primaryText='Выбрать действие',allowed=turn;
  if(b.initiativeDraw){stage='initiative';heading='Выбор инициативы';actor=b.units.find(u=>u.id===b.initiativeDraw.actor);text='Выберите одну из вытянутых карт. Остальные вернутся в колоду.';primary='initiative';primaryText='Выбрать карту';allowed=owns(s,actor?.id);}
  else if(b.pendingRisk){stage=b.pendingRisk.kind==='power'?'talent':'risk';heading=stage==='talent'?'Выбор силы воли':'Решение по броску';actor=b.units.find(u=>u.id===b.pendingRisk.actor);text=b.pendingRisk.waiting?'Мастер завершает скрытый бросок.':stage==='talent'?'Решите, тратить ли СВ на эффект Пути. Затем будут определены броня и урон.':'Примите результат или пойдите на риск в окне костей. Бой продолжится после решения.';primary='roll';primaryText='Открыть бросок';allowed=!!actor&&owns(s,actor.id);}
  else if(b.pendingTalent){stage='talent';heading='Выбор эффекта достоинства';actor=b.units.find(u=>u.id===b.pendingTalent.actor)||active;text='Завершите выбор эффекта в окне броска.';primary='roll';primaryText='Открыть бросок';allowed=actor&&owns(s,actor.id);}
  else if(active?.pendingMove){stage='move';heading='Последствие перегруза';text='Стойкость не пройдена, быстрое действие потрачено. Остаться или продолжить с потерей 1 Ловкости?';primary=null;}
  else if(b.pendingMishap){stage='mishap';heading='Магическая неудача';actor=b.units.find(u=>u.id===b.pendingMishap.caster);text=b.pendingMishap.description;primary='mishap';primaryText='Записать решение';allowed=gm;}
  else if(b.phase==='setup'){stage='setup';heading='Расстановка';text='Выберите бойца, затем свободный гекс. Мастер начинает бой после расстановки и настройки внезапности.';primary='start';primaryText='Начать бой';allowed=gm;}
  else if(b.phase==='finished'){stage='finished';heading='Бой завершён';text=b.winner==='draw'?'Все бойцы сломлены. Ничья.':`Победа отряда ${b.winner||'—'}. Текущее состояние персонажей сохранено.`;primary='close';primaryText='Закрыть бой';allowed=gm;actor=null;}
  else if(!active.fast&&!active.slow){text='Быстрое и медленное действия израсходованы. Можно завершить ход; доступные атаки за СВ показаны ниже.';primary='end';primaryText='Завершить ход';}
  else if(selected!==active.id){primary='active';primaryText='Выбрать ходящего';}
  const who=actor?controller(s,actor):null;
  const waiting=!allowed&&stage!=='finished'?(who?`Ожидаем: ${who.name}${who.id===s.me.owner?' (вы)':''}`:stage==='setup'?'Ожидаем Мастера':'Ожидаем решения Мастера'):'';
  const stageMarkup=`<section class="combat-turn-panel" data-combat-stage="${stage}" aria-label="Текущий шаг боя"><div class="combat-stage-copy" role="status" aria-live="polite"><span class="combat-eyebrow">${b.round?`Раунд ${b.round} · `:''}${esc(heading)}</span>${actor?`<h3>${esc(actor.name)}</h3><p class="combat-controller">Управляет: ${esc(who.name)}${who.id===s.me.owner?' · вы':''}${gm&&who.role!=='gm'?' · Мастер может действовать за него':''}</p>`:`<h3>${esc(heading)}</h3>`}<p>${esc(text)}</p>${stage==='turn'&&active?`<div class="combat-budgets">${budget(active)}<span class="combat-will">СВ ${active.wp}</span></div>`:''}${waiting?`<p class="combat-waiting">${esc(waiting)}. Можно осмотреть бойцов${stage==='turn'?' и настроить защиту своих героев':''}.</p>`:''}</div><div class="combat-next-step">${stage==='move'?`<button data-load-stop ${turn?'':'disabled'}>Остаться на месте</button><button data-load-go ${turn?'':'disabled'}>Продолжить · −1 Ловкость</button>`:primary&&allowed?`<button class="primary" data-combat-next="${primary}">${esc(primaryText)}</button>`:''}${next?`<p>Следующий${nextRound?' · новый раунд':''}<br><strong>${esc(next.name)}</strong><br><small>${esc(controller(s,next).name)}</small></p>`:''}</div></section>`;
  const queue=`<section class="combat-queue-section"><h3>${b.phase==='setup'?'Участники и карты инициативы':'Очередь инициативы'}</h3><div class="combat-queue" aria-label="Очередь инициативы">${order.map(u=>{const current=u.id===active?.id&&b.phase==='combat',person=controller(s,u),broken=!isAlive(u),status=broken?'Сломлен':current?'Ходит сейчас':u.id===next?.id?`Следующий${nextRound?' · раунд '+(b.round+1):''}`:b.phase==='setup'?'Ожидает начала':b.phase==='finished'?'Бой завершён':order.indexOf(u)<b.turn?'Ход завершён':'Ожидает хода';return `<button class="combat-queue-card ${current?'is-current':''} ${broken?'is-broken':''}" data-combat-select="${esc(u.id)}" aria-pressed="${u.id===selected}" ${current?'aria-current="step"':''}><span class="combat-queue-top"><b class="combat-initiative-number" title="Карта инициативы">${u.initiative||'?'}</b><span>${status}</span><small>Отряд ${u.team}</small></span><span class="combat-queue-person">${identityMarkup({...person,name:u.name},{size:'small',current})}<strong>${esc(u.name)}</strong></span><small class="combat-controller">${esc(person.name)}${person.id===s.me.owner?' · вы':''}</small><span class="combat-queue-budget">Быстр. ${u.fast} · Медл. ${u.slow} · СВ ${u.wp}</span></button>`;}).join('')}</div></section>`;
  // Defense is a standing reaction, available on other fighters' turns too.
  const defenseBlock=b.initiativeDraw||b.pendingRisk||b.pendingTalent||active?.pendingMove?block:!mine?'Защитой управляет владелец персонажа или Мастер.':'';
  const defense=defenseCost(chosen,chosen.defense||'none');
  const defenseHint=chosen.defense==='none'?'':defense.free?'Достоинство даёт бесплатную защиту.':canSpend(chosen,'fast')?'При атаке защита потратит быстрое действие или оставшееся медленное.':'Для платной защиты действий сейчас нет. Выбор сохранится на следующий раунд.';
  const inspector=`<section class="combat-inspector"><div class="toolbar"><label>Осматриваемый боец<select id="combat-unit">${b.units.map(u=>`<option value="${esc(u.id)}" ${u.id===selected?'selected':''}>${esc(u.name)} · отряд ${u.team} · ТЕЛ ${u.str}/${u.maxStr}</option>`).join('')}</select></label><label>Защита при атаке<select id="combat-defense" ${defenseBlock?'disabled':''} aria-describedby="combat-defense-help">${[['none','Без защиты'],['dodge','Уклониться и упасть'],['dodgeStand','Уклониться стоя'],['weapon','Парировать оружием'],['shield','Парировать щитом']].map(([v,l])=>`<option value="${v}" ${chosen.defense===v?'selected':''}>${l}</option>`).join('')}</select></label></div><p id="combat-defense-help" class="muted">Защиту своего персонажа можно выбрать вне его хода. ${esc(defenseBlock||defenseHint)}${chosen.defense==='shield'&&!chosen.shield?' Нет исправного щита: эта защита сейчас не сработает.':chosen.defense==='weapon'&&(!chosen.gear||weaponFor(chosen).ranged)?' Нет исправного оружия для парирования: эта защита сейчас не сработает.':''}</p><p class="combat-equipment">${esc(weaponFor(chosen).name)} · бонус ${chosen.gear} · урон ${weaponFor(chosen).damage}${chosen.weaponArtifact?' · D'+chosen.weaponArtifact:''} · броня ${chosen.armor} · щит ${chosen.shield}${chosen.overloaded?' · Перегруз':''}</p>${active&&selected!==active.id&&b.phase==='combat'?`<p class="combat-selection-note">Осмотр: <strong>${esc(chosen.name)}</strong>. Атаки и действия выполняет ходящий <strong>${esc(active.name)}</strong>. <button data-combat-next="active">Выбрать ходящего</button></p>`:''}</section>`;
  const moveReason=(q,r)=>b.phase==='setup'?(gm?block:'Расстановкой управляет Мастер.'):block||(!turn?'Сейчас действует другой участник.':selected!==active?.id?'Сначала выберите ходящего бойца.':b.phase!=='combat'?'Бой завершён.':movementReason(b,chosen,{q,r},retreat));
  const board=`<div class="board-wrap"><div class="combat-grid">${Array.from({length:117},(_,i)=>{const q=i%13,r=Math.floor(i/13),u=b.units.find(u=>u.q===q&&u.r===r),terrain=b.terrain[`${q},${r}`],reason=terrain==='wall'?'Стена.':u?'':moveReason(q,r);return `<button style="left:${r*24}px" data-combat-q="${q}" data-combat-r="${r}" ${u?`data-combat-select="${esc(u.id)}"`:''} class="${u?`team-${u.team} ${u.id===active?.id&&b.phase==='combat'?'active-fighter':''} ${u.id===selected?'selected-fighter':''}`:!reason?'reachable':''}" title="${q+1}, ${r+1}: ${esc(u?u.name+' · осмотреть бойца':reason||'Переместиться · быстрое действие')}" ${reason?'disabled':''}>${u?`<img data-sprite="${esc(u.id)}" style="--move-x:${event?.origin?((event.origin.q-u.q)*49+(event.origin.r-u.r)*24):0}px;--move-y:${event?.origin?(event.origin.r-u.r)*63:0}px" class="fighter-sprite ${event?.actor===u.id?'anim-'+event.kind:''} ${event?.hitIds?.includes(u.id)?'anim-hit':''} ${u.prone?'prone':''} ${!isAlive(u)?'broken':''}" alt="${esc(u.name)}"><span>${esc(u.name.slice(0,9))}</span>${u.burning?'<i class="status-fire">♨</i>':''}`:terrain==='wall'?'■':terrain==='forest'?'♠':terrain==='rough'?'·':''}</button>`;}).join('')}</div></div><p class="muted combat-map-help">${b.phase==='setup'?'Выберите фигуру, затем свободный гекс для расстановки.':'Золотая рамка — ходящий. Нажатие на фигуру открывает её осмотр; противник также становится целью. Доступные соседние гексы подсвечены.'}</p>`;
  const reasonFor=(a,o)=>combatActionReason(s,a,target,o);
  const actionButton=([a,label])=>{const reason=reasonFor(a),speed=['slash','stab','shoot','punch','shove'].includes(a)?speedFor(active,a):['ready','extinguish'].includes(a)?'slow':'fast';return `<div class="combat-action-choice"><button data-combat-action="${a}" ${reason?'disabled':''} aria-describedby="combat-reason-${a}" title="${esc(reason||label)}">${label}<small>${a==='end'?'Передать ход':speed==='slow'?'Медленное действие':'Быстрое действие'}</small></button><small id="combat-reason-${a}">${esc(turn&&!block?reason:'')}</small></div>`;};
  const actions=b.phase==='combat'?`<section class="combat-action-panel" id="combat-actions" tabindex="-1"><h3>Действия: ${esc(active?.name)}</h3>${block||!turn?`<p class="combat-action-block" role="status">${esc(block||'Сейчас действует другой участник. Вы можете настроить защиту своих героев выше.')}</p>`:''}<div class="toolbar"><label>Цель<select id="combat-target">${enemies.map(u=>`<option value="${esc(u.id)}" ${u.id===target?'selected':''}>${esc(u.name)}</option>`).join('')}</select></label><label><input id="combat-retreat" type="checkbox" ${retreat?'checked':''}> Отступление из ближнего боя</label></div>${!active?.monster?`<div class="combat-action-group" aria-label="Атаки">${[['slash','Рубящий'],['stab','Колющий'],['shoot','Выстрел'],['punch','Кулаком'],['shove','Толчок']].map(actionButton).join('')}</div>`:''}<div class="combat-action-group" aria-label="Подготовка и конец хода">${[['stand',active?.prone?'Встать':'Лечь'],['ready','Зарядить'],['aim','Прицелиться'],['swing','Замах'],['cover','Укрытие'],['extinguish','Тушить огонь'],['end','Завершить ход']].filter(([a])=>!active?.monster||['stand','cover','end'].includes(a)).map(actionButton).join('')}</div>${gm&&active?.monster?`<label>Атака чудовища<select id="monster-attack"><option value="random">Случайная D6</option>${active.monster.attacks.map((a,i)=>`<option value="${i}">${i+1}. ${esc(a.name)} · ${a.dice}D6</option>`).join('')}</select></label><button data-monster-attack ${reasonFor('monsterAttack')?'disabled':''} title="${esc(reasonFor('monsterAttack'))}">Атаковать по таблице · медленное</button><p class="muted" data-monster-reason>${esc(reasonFor('monsterAttack')||'Случайная атака может потребовать решения Мастера по таблице.')}</p>`:''}${gm?`<div class="combat-manual"><button data-manual-magic ${reasonFor('manualMagic')?'disabled':''} title="${esc(reasonFor('manualMagic'))}">Магия / особый эффект · решение Мастера</button><small>${esc(reasonFor('manualMagic')||'Расходует медленное действие. Урон и СВ подтверждает Мастер.')}</small></div>`:''}</section>`:'';
  root.innerHTML=`<h2>Общий бой</h2>${stageMarkup}${queue}<div class="combat-initiative-tools"></div>${inspector}${board}${actions}${b.phase==='setup'&&gm?`<button data-combat-action="start" ${block?'disabled':''}>Начать бой</button>`:''}<details class="combat-history"><summary>Журнал боя</summary><div class="combat-log">${b.log.slice(-15).map(x=>`<p>${esc(x)}</p>`).join('')}</div></details><div class="rule-help"><p><span class="rule-badge automatic">Автоматически</span> Инициатива, действия, атаки, выбранная экипировка, броня и урон.</p><p><span class="rule-badge manual">Решение Мастера</span> Критические травмы, ситуативные эффекты достоинств и магию разрешает Мастер. Чудовища используют атаки D6 без форсирования; СВ у ПВ не накапливается.</p></div>${gm&&b.phase!=='finished'?`<button data-combat-close ${b.pendingRisk||b.initiativeDraw?'disabled':''}>Закрыть бой</button>`:''}`;
  combatOptions(root,s,selected,target,command,{actionReason:reasonFor,blockReason:block});
  const queueEl=root.querySelector('.combat-queue'),currentCard=queueEl.querySelector('[aria-current=step]');
  if(currentCard)queueEl.scrollLeft=Math.max(0,currentCard.offsetLeft-queueEl.offsetLeft-10);
  paintSprites(root,b.units,event?{[event.actor]:event.kind}:{}).then(()=>{if(event)setTimeout(()=>paintSprites(root,getState()?.combat?.units||[]),900);});
 }
 function command(c){return act({action:'combatAction',revision:getState().combatRevision,command:{...c,interactive:true}});}
 function redraw(){last='';render();}
 function close(){if(confirm('Закрыть бой? Текущие характеристики персонажей сохранятся.'))act({action:'combatClose'});}
 root.addEventListener('change',e=>{
  if(e.target.id==='combat-unit'){selected=e.target.value;redraw();}
  if(e.target.id==='combat-target'){target=e.target.value;redraw();}
  if(e.target.id==='monster-attack'){const reason=combatActionReason(getState(),'monsterAttack',target,{index:e.target.value}),button=root.querySelector('[data-monster-attack]');button.disabled=!!reason;button.title=reason;root.querySelector('[data-monster-reason]').textContent=reason||(e.target.value==='random'?'Случайная атака может потребовать решения Мастера по таблице.':'Медленное действие чудовища.');}
  if(e.target.id==='combat-retreat'){retreat=e.target.checked;redraw();}
  if(e.target.id==='combat-defense')command({action:'defense',unit:selected,value:e.target.value});
 });
 root.onclick=e=>{
  const el=e.target.closest('button');if(!el||el.disabled)return;const s=getState(),b=s.combat;
  if(el.dataset.combatSelect){selected=el.dataset.combatSelect;const u=b.units.find(u=>u.id===selected),a=activeUnit(b);if(a&&u.team!==a.team&&isAlive(u))target=u.id;redraw();return;}
  if(el.dataset.combatNext){
   const step=el.dataset.combatNext;
   if(step==='active'){selected=activeUnit(b)?.id;redraw();}
   if(step==='actions')root.querySelector('#combat-actions')?.focus();
   if(step==='initiative')root.querySelector('[data-init-card]:not(:disabled)')?.focus();
   if(step==='roll')document.getElementById('dice-last')?.click();
   if(step==='start'||step==='end')command({action:step});
   if(step==='close')close();
   if(step==='mishap'){const note=prompt('Решение Мастера по магической неудаче',b.pendingMishap.description);if(note)command({action:'resolve',note,target});}
   return;
  }
  if(el.hasAttribute('data-combat-create')){const units=[...root.querySelectorAll('[data-roster]')].filter(s=>s.value).map(s=>({id:s.dataset.roster,team:s.value}));act({action:'combatCreate',units,mapId:root.querySelector('#combat-map').value});}
  if(el.hasAttribute('data-load-stop'))command({action:'resolveLoad',proceed:false});
  if(el.hasAttribute('data-load-go'))command({action:'resolveLoad',proceed:true});
  if(el.dataset.combatAction)command({action:el.dataset.combatAction,target});
  if(el.hasAttribute('data-monster-attack')){const value=root.querySelector('#monster-attack').value;command({action:'monsterAttack',index:value==='random'?value:Number(value),target});}
  if(el.hasAttribute('data-manual-magic')){const note=prompt('Решение по правилам: заклинание, сила эффекта, броня и последствия');if(!note)return;const value=prompt('Итоговый урон ТЕЛ после брони и защиты (0 для эффекта без урона)','0'),wp=prompt('Расход СВ героя; ПВ и чудовища — 0','0');if(value!==null&&wp!==null)act({action:'combatManual',revision:s.combatRevision,actor:activeUnit(b)?.id,target:target||selected,attribute:'str',damage:Number(value),wp:Number(wp),note,slow:true});}
  if(el.hasAttribute('data-combat-q'))command({action:'move',unit:selected,q:+el.dataset.combatQ,r:+el.dataset.combatR,retreat});
  if(el.hasAttribute('data-combat-close'))close();
 };
 return render;
}
