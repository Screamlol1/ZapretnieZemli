import {travelStatus} from './travel-status.js';
const jobs={hike:'Переход',watch:'Дозор',camp:'Устроить лагерь',rest:'Отдых',sleep:'Сон',forageFood:'Собирать пищу',forageWater:'Искать воду',hunt:'Охота',fish:'Рыбалка',explore:'Исследование',work:'Работа в цитадели'};
const skills={survive:'Выживание',endure:'Стойкость',craft:'Ремесло',shoot:'Стрельба'};
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function personalTurnUI(getState,send,details){
 const root=document.createElement('section');root.id='personal-turn';root.className='personal-turn';root.hidden=true;
 document.getElementById('journey-overview').before(root);
 root.innerHTML=`<div class="toolbar"><h3>Мой ход</h3><button type="button" data-details>Припасы и подробности</button></div><p data-empty></p><form><div class="personal-fields"><label>Мой герой<select name="hero" aria-label="Мой герой"></select></label><label>Занятие<select name="job">${Object.entries(jobs).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select></label><label>Роль при переходе<select name="role"><option value="none">Без дополнительной роли</option><option value="lead">Проводник</option><option value="watch">Дозорный</option></select></label></div><p data-plan-status role="status"></p><button type="submit" class="primary-action">Заявить занятие</button></form><div data-results></div><p data-wait role="status"></p><button type="button" data-complete class="primary-action">Мои действия и проверки завершены</button><p class="muted personal-rule"><span class="rule-badge automatic">Автоматически</span> Проверки выполнятся после всех заявок и готовности Мастера. Время сменится после всех подтверждений.</p>`;
 const form=root.querySelector('form'),hero=form.elements.hero,job=form.elements.job,role=form.elements.role,save=form.querySelector('[type=submit]'),complete=root.querySelector('[data-complete]');
 let selected='',version='',cycle='',dirty=false,pending=false,message='';const drafts=new Map();
 function roleVisible(){role.parentElement.hidden=job.value!=='hike';if(job.value!=='hike')role.value='none';}
 hero.onchange=()=>{if(dirty)drafts.set(selected,{version,job:job.value,role:role.value});selected=hero.value;version='';dirty=false;message='';render();};
 job.onchange=role.onchange=()=>{dirty=true;message='';roleVisible();root.querySelector('[data-plan-status]').textContent='Изменения ещё не заявлены.';};
 root.querySelector('[data-details]').onclick=details;
 async function run(data){if(pending)return;pending=true;const started=cycle;render();try{const ok=await send(data);if(ok){dirty=false;drafts.delete(selected);message=cycle!==started?'':data.action==='travelPlan'?'Заявка сохранена.':'Подтверждение сохранено.';}else message=document.getElementById('error')?.textContent||'Изменение не сохранено. Повторите попытку.';}finally{pending=false;render();}}
 form.onsubmit=e=>{e.preventDefault();run({action:'travelPlan',id:selected,job:job.value,role:role.value});};
 complete.onclick=()=>run({action:'travelComplete',complete:!getState().journey.completed?.[getState().me.owner]});
 function render(){
  const s=getState();if(!s)return;root.hidden=s.me.role==='gm';if(root.hidden)return;
  const status=travelStatus(s),t=s.journey,own=status.own,newCycle=JSON.stringify([s.id,t.day,t.quarter,t.cycleId]);
  if(cycle!==newCycle){cycle=newCycle;dirty=false;version='';message='';drafts.clear();}
  const choices=own.map(c=>`<option value="${esc(c.id)}">${esc(c.name)}</option>`).join('');
  if(hero.innerHTML!==choices)hero.innerHTML=choices;
  if(!own.some(c=>c.id===selected)){selected=own[0]?.id||'';version='';dirty=false;}
  root.querySelector('h3').textContent=own.length===1?'Мой ход · '+own[0].name:'Мой ход';
  hero.value=selected;hero.disabled=pending;hero.parentElement.hidden=own.length<2;
  const empty=root.querySelector('[data-empty]');empty.hidden=own.length>0;empty.textContent='Ваш герой пока не включён в отряд. Попросите Мастера добавить его в состав.';
  const planning=t.phase==='planning',plan=t.plans[selected],nextVersion=JSON.stringify([selected,t.planVersions?.[selected]||0,plan]);
  if(nextVersion!==version){const draft=drafts.get(selected);if(draft?.version===nextVersion){job.value=draft.job;role.value=draft.role;dirty=true;}else{if((version||draft)&&!pending)message='Заявка изменена в другом окне или Мастером. Показан сохранённый вариант.';job.value=plan?.job||'rest';role.value=plan?.role||'none';dirty=false;drafts.delete(selected);}version=nextVersion;}
  form.hidden=!own.length||!planning;job.disabled=role.disabled=pending||s.combat?.phase==='combat';save.disabled=job.disabled;roleVisible();
  save.textContent=plan?'Обновить заявку':'Заявить занятие';
  root.querySelector('[data-plan-status]').textContent=message||(dirty?'Изменения ещё не заявлены.':plan?'Заявлено: '+jobs[plan.job]+'. Можно изменить до выполнения проверок.':'Выберите занятие и отправьте заявку.');
  root.querySelector('[data-wait]').textContent=status.reason||status.text;
  const participant=(t.cycleParticipants||[]).some(p=>p.owner===s.me.owner);
  complete.hidden=planning||!participant;complete.disabled=pending||(t.pendingCount??t.pending.length)>0||s.combat?.phase==='combat';
  complete.textContent=t.completed?.[s.me.owner]?'Отменить моё подтверждение':'Мои действия и проверки завершены';
  const result=root.querySelector('[data-results]');result.hidden=planning;
  const checks=t.history.findLast(h=>h.plans&&h.day===t.day&&h.quarter===t.quarter)?.rolls||[];
  result.innerHTML=planning?'':checks.filter(r=>r.skill!=='scout'&&own.some(c=>c.id===r.character)).map(r=>`<p><strong>${esc(r.name)}</strong> · ${esc(skills[r.skill]||r.skill)}: ${r.hits} успехов · база [${esc(r.base)}], навык [${esc(r.skillDice)}], предмет [${esc(r.gear)}]</p>`).join('')||'<p>Открытых проверок нет. Проверьте результаты действий и решения Мастера.</p>';
 }
 return {render};
}
