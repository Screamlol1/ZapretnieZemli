const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pipSlots=[[],[4],[0,8],[0,4,8],[0,2,6,8],[0,2,4,6,8],[0,2,3,5,6,8]];
const face=(value,sides)=>sides===6?`<span class="die-pips">${Array.from({length:9},(_,i)=>`<i class="${pipSlots[value].includes(i)?'pip':'empty-pip'}"></i>`).join('')}</span>`:value;
const kinds=new Set(['penalty','base','skill','gear','artifact','armor','cover','magic','table','monster']);
// First connection shows history silently. Only new event IDs animate, including
// several rolls received in one poll. A state refresh cannot throw dice again.
export function diceFeed(){
 let campaign=null,seen=new Set();
 return s=>{const events=(s.diceRolls||[]).filter(e=>!e.private||s.me.role==='gm');
  if(campaign!==s.id){campaign=s.id;seen=new Set(events.map(e=>e.id));return [];}
  const fresh=events.filter(e=>!seen.has(e.id));for(const e of fresh)seen.add(e.id);
  if(seen.size>1000)seen=new Set(events.map(e=>e.id));return fresh;
 };
}
export function diceUI(getState){
 const feed=diceFeed(),stage=document.createElement('section');stage.id='dice-stage';stage.className='dice-stage';stage.hidden=true;stage.setAttribute('popover','manual');stage.setAttribute('aria-label','Бросок костей');
 const history=document.createElement('section');history.className='dice-history';document.querySelector('#journal-panel').append(history);document.body.append(stage);
 const live=document.createElement('div');live.className='dice-sr';live.setAttribute('role','status');live.setAttribute('aria-live','polite');document.body.append(live);
 const shortcut=document.createElement('button');shortcut.id='dice-last';shortcut.textContent='Кости · последний бросок';shortcut.disabled=true;document.querySelector('.campaign-bar').append(shortcut);
 let queue=[],current=null,finishTimer,lastSignature='',campaign='',events=[];
 let animate=true;try{animate=localStorage.getItem('dice-animation')!=='off';}catch{}
 const reduced=()=>!animate||matchMedia('(prefers-reduced-motion: reduce)').matches;
 function hide(){clearTimeout(finishTimer);if(stage.matches(':popover-open'))stage.hidePopover();stage.hidden=true;current=null;}
 function next(){hide();if(queue.length)show(queue.shift());}
 function show(e,replay=false){
  clearTimeout(finishTimer);current=e;
  const rolling=!reduced();let index=0;
  stage.dataset.rollId=e.id;stage.dataset.private=String(e.private);stage.dataset.phase=rolling?'rolling':'result';
  stage.innerHTML=`<div class="dice-heading"><div><small>${replay?'ПОВТОР · ':''}${e.private?'СКРЫТО · ТОЛЬКО МАСТЕРУ':'ОТКРЫТЫЙ БРОСОК'}</small><h3>${esc(e.name)} · ${esc(e.label)}</h3></div><button data-dismiss aria-label="Закрыть показ костей">×</button></div><div class="dice-tray">${e.groups.map(g=>`<div class="dice-group"><div class="dice-group-label">${esc(g.label)} · D${g.sides}${g.negative?' · успехи вычитаются':''}</div><div class="dice-row">${g.values.map((value,dieIndex)=>`<div class="roll-die die-${kinds.has(g.kind)?g.kind:'table'} ${g.sides!==6?'poly-die':''} ${g.held?.[dieIndex]?'die-held':''}" style="--i:${index++%10}" aria-label="${esc(g.label)} D${g.sides}: ${value}${g.held?.[dieIndex]?' · сохранён при форсировании':''}"><span class="die-face" aria-hidden="true">${face(value,g.sides)}</span><small>${g.held?.[dieIndex]?'✓ ':''}D${g.sides}</small></div>`).join('')}</div></div>`).join('')||'<p>В этом действии нет костей.</p>'}</div>${e.groups.some(g=>g.held?.some(Boolean))?'<small>✓ Сохранённые кости не перебрасываются.</small>':''}<div class="dice-outcome"><span data-rolling>${rolling?'Кости брошены…':''}</span><strong data-result ${rolling?'hidden':''}>${esc(e.result)}</strong><button type="button" data-next ${queue.length?'':'hidden'}>Следующий бросок</button><small data-queue>${queue.length?'Следующих бросков: '+queue.length:''}</small></div>`;
  stage.hidden=false;if(stage.showPopover&&!stage.matches(':popover-open'))stage.showPopover();
  function finish(){stage.dataset.phase='result';stage.querySelector('[data-rolling]').textContent='';stage.querySelector('[data-result]').hidden=false;live.textContent=`${e.private?'Скрытый бросок. ':''}${e.name}. ${e.label}. ${e.result}`;}
  if(rolling)finishTimer=setTimeout(finish,1050);else finish();
 }
 stage.addEventListener('click',e=>{if(e.target.closest('[data-next]'))next();if(e.target.closest('[data-dismiss]')){queue=[];hide();}});
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&current){queue=[];hide();}});
 shortcut.onclick=()=>{const latest=events.at(-1);if(latest){queue=[];show(latest,true);}};
 history.addEventListener('click',e=>{const b=e.target.closest('[data-dice-replay]');if(b){const event=events.find(r=>r.id===b.dataset.diceReplay);if(event){queue=[];show(event,true);}}});
 history.addEventListener('change',e=>{if(e.target.matches('[data-dice-animation]')){animate=e.target.checked;try{localStorage.setItem('dice-animation',animate?'on':'off');}catch{}}});
 return {render(){
  const s=getState();if(!s)return;
  if(campaign!==s.id){campaign=s.id;queue=[];hide();const select=document.getElementById('dice-visibility');try{select.value=sessionStorage.getItem('dice-visibility-'+s.id)==='hidden'?'hidden':'public';}catch{}select.onchange=()=>{try{sessionStorage.setItem('dice-visibility-'+s.id,select.value);}catch{}};}
  const fresh=feed(s);events=(s.diceRolls||[]).filter(e=>!e.private||s.me.role==='gm');shortcut.disabled=!events.length;
  queue.push(...fresh);if(!current&&queue.length)next();else if(current){stage.querySelector('[data-queue]').textContent=queue.length?'Следующих бросков: '+queue.length:'';stage.querySelector('[data-next]').hidden=!queue.length;}
  const sig=JSON.stringify([s.id,events]);if(sig===lastSignature)return;lastSignature=sig;
  history.innerHTML=`<h3>Кости за столом</h3><div class="dice-legend"><span class="legend-base">Характеристика</span><span class="legend-skill">Навык</span><span class="legend-penalty">Штраф · −успехи</span><span class="legend-gear">Снаряжение / броня</span><span class="legend-artifact">Артефакт</span><span class="legend-magic">Магия</span><span class="legend-table">Таблица</span><span class="legend-monster">Чудовище</span></div><label><input type="checkbox" data-dice-animation ${animate?'checked':''}> Анимация костей на этом устройстве</label><p class="muted">Открытые броски видны всем подключённым участникам в любом разделе. Повтор показывает сохранённые значения. При входе старые броски не анимируются. Результат остаётся открытым до закрытия вручную; накопившиеся броски переключаются кнопкой «Следующий бросок».</p><details><summary>Последние броски · ${events.length}</summary>${[...events].reverse().slice(0,30).map(e=>`<article class="dice-history-entry"><div><strong>${esc(e.name)} · ${esc(e.label)}</strong><p>${esc(e.result)} ${e.private?'· Только Мастеру':''}</p><small>${e.groups.map(g=>`${esc(g.label)} D${g.sides} [${g.values.join(', ')}]${g.negative?' (−)':''}`).join(' · ')||'Без костей'}</small></div><button data-dice-replay="${e.id}">Повторить показ</button></article>`).join('')||'<p>Бросков пока нет.</p>'}</details>`;
 }};
}
