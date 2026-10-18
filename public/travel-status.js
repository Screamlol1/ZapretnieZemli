import {label} from './world-hex.js';
const jobs={hike:'переход',watch:'дозор',camp:'лагерь',rest:'отдых',sleep:'сон',forageFood:'сбор пищи',forageWater:'поиск воды',hunt:'охота',fish:'рыбалка',explore:'исследование',work:'работа в цитадели'};
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function travelStatus(s){
 const t=s.journey,gm=s.me.role==='gm',who=gm?'gm':s.me.owner,party=t.party.map(id=>s.characters.find(c=>c.id===id)).filter(Boolean),own=party.filter(c=>gm||c.kind==='pc'&&c.owner===s.me.owner),missing=party.filter(c=>!t.plans[c.id]),ownMissing=own.filter(c=>!t.plans[c.id]),pending=t.pendingCount??t.pending.length;
 const result={stage:t.phase==='planning'?0:2,action:'wait',text:'Ожидаем участников',reason:'',missing,party,own};
 if(s.combat?.phase==='combat')return {...result,text:'Идёт бой',reason:'Завершите бой перед действиями путешествия.'};
 if(!party.length)return {...result,action:gm?'setup':'wait',text:gm?'Собрать отряд':'Мастер собирает отряд',reason:'Выберите участников и начальный гекс.'};
 if(pending)return {...result,stage:1,action:gm?'events':'wait',text:gm?'Разрешить события':'Ожидаем решения Мастера',reason:`Незавершённых событий: ${pending}.`};
 if(t.phase==='resolving'){
  const participant=(t.cycleParticipants||[]).some(p=>p.owner===who);
  const waiting=(t.cycleParticipants||[]).filter(p=>!p.complete).map(p=>p.name);
  return {...result,action:participant&&!t.completed[who]?'complete':'wait',text:participant&&!t.completed[who]?'Подтвердить результаты':'Ожидаем подтверждений',reason:'Ожидаем: '+(waiting.join(', ')||'смену четверти')};
 }
 if(ownMissing.length)return {...result,action:'plan',text:'Заявить действие: '+ownMissing[0].name,character:ownMissing[0].id,reason:'Ещё без заявки: '+missing.map(c=>c.name).join(', ')};
 if(missing.length)return {...result,text:'Ожидаем заявки',reason:'Ещё без заявки: '+missing.map(c=>c.name).join(', ')};
 if(gm&&party.some(c=>t.plans[c.id]?.job==='hike')&&!t.route?.length)return {...result,action:'route',text:'Выбрать маршрут',reason:'Заявлен переход. Укажите соседние гексы.'};
 if(gm&&!t.gmReady)return {...result,action:t.blocker?'review':'ready',text:t.blocker?'Исправить условия':'Подтвердить условия и выполнить проверки',reason:t.blocker||'Все заявки готовы. Подтверждение запустит проверки текущей четверти.'};
 return {...result,text:'Ожидаем Мастера',reason:'Заявки сохранены. Мастер подтверждает маршрут и условия.'};
}
export function renderTravelStatus(s){
 const status=travelStatus(s),t=s.journey,button=document.getElementById('map-advance'),panel=document.getElementById('journey-overview');
 button.textContent=status.text;button.disabled=status.action==='wait';
 document.getElementById('map-readiness').textContent=t.phase==='planning'?`Заявки ${t.party.length-status.missing.length}/${t.party.length}`:`Подтверждения ${(t.cycleParticipants||[]).filter(p=>p.complete).length}/${t.cycleParticipants?.length||0}`;
 const markup=`<div class="journey-progress" aria-label="Этапы четверти">${['1 · Заявки','2 · Проверки и события','3 · Подтверждения'].map((v,i)=>`<span class="${status.stage===i?'current':''}">${v}</span>`).join('')}</div><p><strong>Отряд: ${label(t.position)}</strong> · ${t.route?.length?'Маршрут: '+t.route.map(label).join(' → '):'Маршрут не выбран'}</p><p class="${t.blocker?'editor-error':''}">${esc(status.reason)}</p><ul>${status.party.map(c=>{const p=t.plans[c.id],present=s.members?.some(m=>m.owner===c.owner),own=s.me.role==='gm'||c.owner===s.me.owner;return `<li>${esc(c.name)} — ${p?esc(jobs[p.job]||p.job)+(p.role==='lead'?' · проводник':p.role==='watch'?' · дозорный':''):'ожидается заявка'}${!present?' · владелец не в сети':''}${own&&c.load?.overloaded?' · перегруз':''}</li>`;}).join('')}</ul><small>Четверть сменится после разрешения событий и подтверждения всех владельцев героев и Мастера.</small>`;
 if(panel.innerHTML!==markup)panel.innerHTML=markup;
 return status;
}
