import {identityMarkup,campaignParticipants,escapeIdentity as esc} from './player-identity.js';
import {sessionFlow} from './session-flow.js';
import {paintSprites} from './appearance.js';
export function sessionFlowUI(getState,navigate,openInventory=()=>{}){
 const root=document.createElement('section');root.id='session-flow';root.className='session-flow';root.setAttribute('aria-label','Текущий этап игры');
 root.innerHTML='<div class="session-flow-main"></div><p class="sr-only" data-turn-announcement role="status" aria-live="polite" aria-atomic="true"></p>';
 const roster=document.createElement('details');roster.id='session-roster';roster.className='session-roster';
 document.querySelector('.workspace-nav').after(root,roster);
 new ResizeObserver(()=>document.documentElement.style.setProperty('--session-flow-offset',root.getBoundingClientRect().height+16+'px')).observe(root);
 let signature='',announcement='',lastCampaign='',currentFlow;
 root.onclick=e=>{if(!e.target.closest('[data-session-next]'))return;const f=currentFlow;if(!f)return;if(f.action==='dice'){document.getElementById('dice-last')?.click();return;}navigate(f.view);if(f.view==='inventory'&&f.actor)openInventory(f.actor);requestAnimationFrame(()=>{const gm=getState().me.role==='gm',hero=document.querySelector('#personal-turn [name=hero]');if(f.view==='travel'&&!gm&&f.actor&&hero){hero.value=f.actor;hero.dispatchEvent(new Event('change'));}const target=f.action==='events'?document.querySelector('.journey-pending'):f.view==='inventory'?document.querySelector('.inventory-repair'):f.view==='travel'?(gm&&f.actor?document.querySelector(`[data-plan="${CSS.escape(f.actor)}"]`):null)||document.getElementById(gm?'journey-panel':'personal-turn'):null;target?.scrollIntoView({behavior:'smooth',block:'start'});});};
 roster.onclick=e=>{const b=e.target.closest('[data-participant]');if(!b)return;navigate('crew');const c=getState().characters.find(c=>c.id===b.dataset.participant);const card=c&&document.querySelector(`[data-character-card="${CSS.escape(c.id)}"]`);card?.scrollIntoView({block:'center',behavior:'smooth'});};
 function render(){
  const s=getState();if(!s)return;const flow=sessionFlow(s),members=campaignParticipants(s),sig=JSON.stringify([flow,members,s.journey?.cycleParticipants,s.journey?.phase,s.characters.map(c=>[c.id,c.visual,c.sheet?.kin||c.kin]),s.id]);currentFlow=flow;if(signature===sig)return;signature=sig;
  const owner=flow.identity,waiting=flow.waiting||[],isWaiting=p=>waiting.includes(p.role==='gm'?'gm':p.owner)||!!owner&&owner.id===p.id;
  const waitingNames=members.filter(isWaiting).map(p=>p.name).join(', ');
  root.classList.toggle('session-your-turn',flow.yourTurn);root.dataset.stage=flow.stage;root.dataset.context=flow.view;
  root.querySelector('.session-flow-main').innerHTML=`${owner?identityMarkup(owner,{current:true}):'<span class="session-step-number" aria-hidden="true">'+(flow.stage+1)+'</span>'}<div class="session-flow-copy"><small>${esc(flow.eyebrow)}</small><strong>${esc(flow.title)}</strong><span class="session-who">${flow.yourTurn?'Вам доступно действие':owner?'Ожидаем: '+esc(owner.name):waitingNames?'Ожидаем: '+esc(waitingNames):'Ожидаем участников'}${owner&&flow.yourTurn?' · '+esc(owner.name):''}</span><p>${esc(flow.detail)}</p></div><button type="button" data-session-next class="${flow.yourTurn?'primary-action':''}">${esc(flow.button)}</button>${flow.stages.length?`<ol class="session-steps" aria-label="Порядок действий">${flow.stages.map((name,i)=>`<li ${i===flow.stage?'aria-current="step"':''} class="${i<flow.stage?'done':''}"><span>${i<flow.stage?'✓':i+1}</span>${esc(name)}</li>`).join('')}</ol>`:''}`;
  roster.innerHTML=`<summary><span class="participant-miniatures">${members.map(p=>identityMarkup(p,{size:'small',current:isWaiting(p)})).join('')}</span><span>Участники · ${members.filter(p=>p.online).length} в сети<span class="roster-hint"> · показать готовность</span></span></summary><div class="participant-list">${members.map(p=>{const mine=p.owner===s.me.owner,cycle=s.journey?.cycleParticipants?.find(c=>c.owner===(p.role==='gm'?'gm':p.owner)),pending=isWaiting(p),status=pending?'Ожидается действие':s.combat&&['setup','combat'].includes(s.combat.phase)?'Ожидает очереди':cycle?(s.journey.phase==='resolving'?cycle.complete?'Подтверждено':'Ожидает результатов':cycle.declared?'Заявка готова':'Ожидает заявки'):'Вне отряда';return `<button type="button" class="participant-card ${pending?'participant-waiting':''}" data-participant="${esc(p.characterId)}" ${!p.characterId?'disabled':''}>${identityMarkup(p,{current:pending})}<span><strong>${esc(p.name)}${mine?' · вы':''}</strong><small>${p.role==='gm'?'Мастер':'Игрок'} · ${p.online?'в сети':'не в сети'}</small><span>${esc(status)}</span></span></button>`;}).join('')}</div>`;
  const text=flow.title+'. '+(owner?'Ожидаем: '+owner.name+'. ':'')+(flow.yourTurn?'Вам доступно действие.':'');
  if(lastCampaign!==s.id){lastCampaign=s.id;announcement='';}
  if(text!==announcement){announcement=text;root.querySelector('[data-turn-announcement]').textContent=text;}
  paintSprites(root,s.characters);paintSprites(roster,s.characters);
 }
 return {render};
}
