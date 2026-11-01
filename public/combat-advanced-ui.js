import {activeUnit,isAlive} from './tools/battle-rules.js';
import {CARD_ACTIONS,CARD_NAMES,cardAt} from './card-combat.js';
import {available,closeNames} from './battle-close-actions.js';
import {rank} from './battle-talents.js';
import {pathRank} from './combat-abilities.js';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const own=(s,u)=>!!u&&(s.me.role==='gm'||s.characters.some(c=>c.id===u.id&&c.kind==='pc'&&c.owner===s.me.owner));
const opts=(list,current)=>list.map(([v,t])=>`<option value="${esc(v)}" ${v===current?'selected':''}>${esc(t)}</option>`).join('');
const button=(title,c,disabled=false)=>`<button type="button" data-advanced-command="${esc(JSON.stringify(c))}" ${disabled?'disabled':''}>${esc(title)}</button>`;
const coord=`<label>Гекс Q<input name="q" type="number" min="0" max="12" required></label><label>Гекс R<input name="r" type="number" min="0" max="8" required></label>`;
export function combatAdvancedUI(root,s,selected,target,command){
 const b=s.combat;if(!b)return;const u=b.units.find(u=>u.id===selected),a=activeUnit(b),gm=s.me.role==='gm',x=b.cardExchange;
 const el=document.createElement('section');el.className='combat-advanced';el.setAttribute('aria-label','Скрытые комбинации и тактика');
 const cmd=(action,unit=u?.id,extra={})=>({action,unit,...extra});let html='';
 if(x){
  const people=[x.attacker,x.defender].map(id=>b.units.find(u=>u.id===id));
  html+=`<section class="combat-card-exchange"><h3>Скрытая комбинация · шаг ${x.step+1} / ${x.steps}</h3><p>Сначала оба выбирают карты. На каждом шаге атакующий объявляет действие первым, защитник — вторым. После раскрытия остаётся решение по броску.</p><div class="combat-card-pair">`;
  for(const person of people){const other=people.find(p=>p!==person),mine=own(s,person),cards=x.choices[person.id],insight=x.insight;
   html+=`<article><h4>${esc(person.name)} · ${person.id===x.attacker?'атакующий':'защитник'}</h4><div class="combat-hidden-cards">${Array.from({length:x.steps},(_,i)=>`<span class="combat-hidden-card ${i===x.step?'current':''}">${i+1}<br><strong>${cards?.[i]?esc(CARD_NAMES[cards[i]]):x.ready?.[person.id]?'🔒 Выбрано':'Не выбрано'}</strong></span>`).join('')}</div>`;
   if(x.stage==='choose'&&mine&&!x.ready?.[person.id]){
    const wait=insight?.actor===person.id&&!insight.revealed?.length;
    html+=`<form data-advanced-form="cards" data-unit="${esc(person.id)}"><div class="toolbar"><label>Первая карта<select name="first">${opts(Object.entries(CARD_NAMES).filter(([k])=>k!=='double'))}</select></label>${x.steps===2?`<label>Вторая карта<select name="second">${opts(Object.entries(CARD_NAMES),'await')}</select></label>`:''}</div><button ${wait||b.pendingRisk?'disabled':''}>Зафиксировать скрытую комбинацию</button></form>`;
    if(pathRank(person,'enemy')&&!insight)html+=button('Путь врага · 1 СВ',cmd('cardInsight',person.id),!!b.pendingRisk);
    if(wait)html+='<p role="status">Ожидание выбора противника и раскрытия карты Пути врага.</p>';
   }
   if(insight&&insight.actor===person.id&&mine&&insight.revealed?.length)html+=`<p>Путь врага: ${insight.revealed.map(c=>`${c.index+1} — ${esc(CARD_NAMES[c.card])}`).join(', ')}.</p>`;
   if(insight&&x.stage==='choose'&&x.ready?.[insight.opponent]&&!insight.complete&&mine&&person.id===(insight.rank===1?insight.opponent:insight.actor))html+=`<p>Выберите, какую карту раскрыть:</p>${Array.from({length:x.steps},(_,i)=>button('Карта '+(i+1),cmd('cardPeek',person.id,{index:i}))).join('')}`;
   const expected=x.stage==='attacker'?x.attacker:x.stage==='defender'?x.defender:null;
   if(mine&&expected===person.id){const list=(CARD_ACTIONS[cardAt(x,person.id)]||[]).map(choice=>[choice,available(b,person,other,choice)]),possible=list.filter(([,reason])=>!reason);
    html+=`<form data-advanced-form="declare" data-unit="${esc(person.id)}"><label>Действие открытой карты<select name="choice">${possible.length?opts(possible.map(([k])=>[k,closeNames[k]])):opts([['await','Пропустить: все действия категории недоступны']])}</select></label>${possible.some(([k])=>k==='retreat')?`<p>Для отступления укажите соседний свободный гекс.</p><div class="toolbar">${coord.replaceAll(' required','')}</div>`:''}<button ${b.pendingRisk?'disabled':''}>Объявить действие</button></form>${list.filter(([,why])=>why).map(([k,why])=>`<p class="muted">${esc(closeNames[k])}: ${esc(why)}</p>`).join('')}`;
   }
   if(x.actions[person.id])html+=`<p>Объявлено: <strong>${esc(closeNames[x.actions[person.id].action])}</strong></p>`;
   html+='</article>';
  }
  html+='</div>';
  if(x.stage==='resolve')html+=button('Разрешить шаг и бросить кости',cmd('cardResolve',x.attacker),!own(s,people[0])||!!b.pendingRisk||b.units.some(v=>v.painRecovery));
  if(gm)html+=`<form data-advanced-form="cancel" data-unit="${esc(x.attacker)}"><label>Отмена Мастером с записью причины<input name="note" maxlength="500" required></label><button ${b.pendingRisk?'disabled':''}>Отменить комбинацию</button></form>`;
  html+='</section>';
 }else if(b.phase!=='finished'){
  html+=`<details ${b.settings.hiddenCombinations?'open':''}><summary>Скрытые комбинации ближнего боя</summary><p>Дополнительное правило книги игрока, с. 94–96. Применяется отдельно к каждой атаке, только между обычными противниками в досягаемости друг друга. Действия и последствия сохраняются сервером.</p>${gm?button(b.settings.hiddenCombinations?'Отключить комбинации':'Разрешить комбинации',cmd('cardEnable',a?.id,{value:!b.settings.hiddenCombinations}),!!b.pendingRisk):''}${b.settings.hiddenCombinations&&b.phase==='combat'?button('Начать комбинацию с выбранной целью',cmd('cardStart',a?.id,{target}),!own(s,a)||!!b.pendingRisk):''}</details>`;
 }
 const r=b.tacticalReactions?.[0];if(r){const fighter=b.units.find(v=>v.id===r.actor);html+=`<div class="combat-card-exchange"><h3>Перехват копьём · ${esc(fighter?.name)}</h3><p>Противник вошёл на расстояние руки. Укол выполняется до его атаки и тратит обычное медленное действие.</p>${button('Выполнить укол',cmd('tacticalReaction',r.actor,{accept:true}),!own(s,fighter)||!!b.pendingRisk)}${button('Пропустить',cmd('tacticalReaction',r.actor,{accept:false}),!own(s,fighter)||!!b.pendingRisk)}</div>`;}
 for(const person of b.units.filter(v=>v.painRecovery))html+=`<div class="combat-card-exchange"><h3>Стойкость к боли · ${esc(person.name)}</h3><p>Распределите ${person.painRecovery} восстановления утраченных характеристик.</p>${own(s,person)?`<form data-advanced-form="recover" data-unit="${esc(person.id)}"><div class="toolbar"><label>Характеристика<select name="attribute">${opts([['agi','Ловкость'],['wits','Разум'],['emp','Эмпатия']])}</select></label><label>Количество<input name="amount" type="number" min="1" max="${person.painRecovery}" value="1" required></label><button ${b.pendingRisk?'disabled':''}>Восстановить</button></div></form>${button('Отказаться от остатка',cmd('tacticalRecover',person.id,{attribute:'skip'}),!!b.pendingRisk)}`:'<p>Ожидание владельца персонажа.</p>'}</div>`;
 if(b.chargeContinuation&&!r)html+=button('Продолжить удар натиска',cmd('tacticalFinishCharge',b.chargeContinuation.actor),!own(s,b.units.find(v=>v.id===b.chargeContinuation.actor))||!!b.pendingRisk);
 if(u&&!u.monster&&own(s,u)){
  html+=`<details><summary>Тактика · ${esc(u.name)}${u.mounted?' · верхом':''}${u.disarmed?' · оружие выбито':''}${u.grappledBy?' · в захвате':''}</summary>`;
  if(b.phase==='setup'){
   if(gm)html+=`<form data-advanced-form="mount"><div class="toolbar"><label><input type="checkbox" name="mounted" ${u.mounted?'checked':''}> Верхом</label><label>Скорость животного<input name="rate" type="number" min="1" max="5" value="${u.mountRate||1}"></label><button>Сохранить</button></div></form>`;
   if(rank(u,'ambidextrous'))html+=`<form data-advanced-form="offhand"><label>Вторая рука<select name="item">${opts([['','Не использовать'],...(u.offhandOptions||[]).map(i=>[i.id,`${i.name} · бонус ${i.gear}`])],u.offhand?.id)}</select></label><button>Выбрать второе оружие</button></form>`;
  }else if(b.phase==='combat'&&!x&&!b.pendingRisk&&!r&&!b.chargeContinuation&&!b.units.some(v=>v.painRecovery)){
   if(pathRank(u,'shield'))html+=`<form data-advanced-form="guard"><h4>Путь щита · защита союзника</h4><div class="toolbar"><label>Кого прикрывать<select name="target">${opts([['','Снять защиту'],[u.id,'Себя (без расхода за союзника)'],...b.units.filter(v=>v.id!==u.id&&v.team===u.team&&isAlive(v)).map(v=>[v.id,v.name])],u.guardTarget)}</select></label><label>Парирование<select name="mode">${opts([['weapon','Оружием'],['shield','Щитом']],u.guardPlan?.mode)}</select></label></div>${pathRank(u,'shield')>=2?'<label><input type="checkbox" name="free"> Дополнительно 1 СВ вместо действия</label>':''}${pathRank(u,'shield')>=3?'<label>Предельный расход СВ на уменьшение урона после успешного парирования<input type="number" name="reduction" min="0" max="10" value="0"></label>':''}<p>1 СВ за защиту союзника. Расход подтверждается этим выбором и применяется при следующей подходящей атаке.</p><button>Сохранить защиту</button></form>`;
   if(u.id===a?.id){const victim=b.units.find(v=>v.id===target);html+='<div class="toolbar">';for(const choice of ['disarm','grapple','grappleAttack','breakFree','release','draw','feint']){const reason=available(b,u,victim,choice);html+=`<span title="${esc(reason)}">${button(closeNames[choice]||'Отпустить',cmd('closeAction',u.id,{choice,target}),!!reason)}</span>`;}html+='</div>';
    if(u.offhand)html+=`<p>Вторая рука: ${esc(u.offhand.name)}</p>${['slash','stab'].map(choice=>button('Второй рукой · '+closeNames[choice],cmd('tacticalOffhandAttack',u.id,{choice,target}),u.offhandRound===b.round)).join('')}`;
    if(u.mounted&&pathRank(u,'plains')>=3)html+=`<form data-advanced-form="speed"><label>Путь равнин 3: СВ на скорость этого раунда<input name="wp" type="number" min="1" max="10" value="1"></label><button>Ускорить животное</button></form>`;
    const modes=[];if(u.mounted)modes.push(['tacticalRide','Движение животного']);if(rank(u,'charge'))modes.push(['tacticalCharge','Натиск пешком']);if(u.mounted&&rank(u,'horsefight')>=3)modes.push(['tacticalMountedCharge','Конный натиск']);if(u.mounted&&pathRank(u,'plains')>=2)modes.push(['tacticalPlains','Путь равнин · отступление 1 СВ']);
    if(modes.length)html+=`<form data-advanced-form="charge"><h4>Движение и атака</h4><p>Цель берётся из обычного списка целей. Укажите конечный свободный гекс рядом с противником; для отступления — соседний гекс.</p><div class="toolbar"><label>Способ<select name="action">${opts(modes)}</select></label><label>Атака<select name="choice">${opts(['slash','stab','punch','shove'].map(k=>[k,closeNames[k]]))}</select></label>${coord}</div><button>Выполнить</button></form>`;
   }
  }
  html+='</details>';
 }
 el.innerHTML=html;root.querySelector('.combat-queue-section')?.before(el);
 el.addEventListener('click',e=>{const btn=e.target.closest('[data-advanced-command]');if(!btn||btn.disabled)return;command({...JSON.parse(btn.dataset.advancedCommand),...(x?{exchange:x.id}:{})});});
 el.addEventListener('submit',e=>{const form=e.target.closest('[data-advanced-form]');if(!form)return;e.preventDefault();const f=new FormData(form),kind=form.dataset.advancedForm,unit=form.dataset.unit||u?.id;let c;
  if(kind==='cards')c=cmd('cardChoose',unit,{cards:[f.get('first'),...(x.steps===2?[f.get('second')]:[])]});
  if(kind==='declare')c=cmd('cardDeclare',unit,{choice:f.get('choice'),...(f.get('choice')==='retreat'?{q:Number(f.get('q')),r:Number(f.get('r'))}:{})});
  if(kind==='cancel')c=cmd('cardCancel',unit,{note:f.get('note')});
  if(kind==='recover')c=cmd('tacticalRecover',unit,{attribute:f.get('attribute'),amount:Number(f.get('amount'))});
  if(kind==='mount')c=cmd('tacticalMount',unit,{mounted:f.has('mounted'),rate:Number(f.get('rate'))});
  if(kind==='offhand')c=cmd('tacticalOffhand',unit,{item:f.get('item')});
  if(kind==='guard')c=cmd('tacticalGuard',unit,{target:f.get('target'),mode:f.get('mode'),free:f.has('free'),reduction:Number(f.get('reduction')||0)});
  if(kind==='speed')c=cmd('tacticalPlainsSpeed',unit,{wp:Number(f.get('wp'))});
  if(kind==='charge')c=cmd(f.get('action'),unit,{target,choice:f.get('choice'),q:Number(f.get('q')),r:Number(f.get('r'))});
  if(c)command({...c,...(x?{exchange:x.id}:{})});
 });
}
