const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const journalKinds={chat:'Сообщения',check:'Проверки',journey:'Путешествие',decision:'Решения Мастера',inventory:'Предметы',stronghold:'Цитадели',event:'События',other:'Прочее'};
const quarters=['утро','день','вечер','ночь'];
const skills={survive:'Выживание',scout:'Наблюдательность',endure:'Стойкость',craft:'Ремесло',shoot:'Стрельба'};
export function journalEntries(s){
 const entries=(s.log||[]).map((e,i)=>({...e,index:i,kind:journalKinds[e.kind]?e.kind:e.name==='Путешествие'?'journey':/^Проверка:/.test(e.text)?'check':'other'}));
 for(const h of s.journey?.history||[]){
  if(h.private&&s.me.role!=='gm')continue;
  for(const r of h.rolls||[]){
   if(s.me.role!=='gm'&&(r.skill==='scout'||!s.characters.some(c=>c.id===r.character&&c.owner===s.me.owner)))continue;
   entries.push({name:r.name,kind:'check',day:h.day,quarter:h.quarter,index:entries.length,text:`${skills[r.skill]||r.skill}: ${r.hits} успехов. База [${r.base}], навык [${r.skillDice}]${r.negative?' (отрицательный)':''}, снаряжение [${r.gear}]${(r.artifacts||[]).map(a=>`, D${a.sides} [${a.value}]`).join('')}.`,private:r.skill==='scout'});
  }
 }
 return entries.sort((a,b)=>(a.day??-1)-(b.day??-1)||(a.quarter??-1)-(b.quarter??-1)||(a.time??0)-(b.time??0)||a.index-b.index);
}
export function filterJournal(entries,f){const q=(f.search||'').trim().toLocaleLowerCase('ru');return entries.filter(e=>(!f.kind||e.kind===f.kind)&&(!f.author||e.name===f.author)&&(!f.day||(e.day==null?'unknown':String(e.day))===f.day)&&(!q||(e.name+' '+e.text).toLocaleLowerCase('ru').includes(q)));}
export function journalUI(getState){
 const log=document.getElementById('log'),controls=document.createElement('form');controls.className='journal-filters';controls.setAttribute('aria-label','Фильтры журнала');
 controls.innerHTML=`<label>Поиск по журналу<input name="search" type="search" placeholder="Герой, событие или слово"></label><label>Тип записи<select name="kind"><option value="">Все типы</option>${Object.entries(journalKinds).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select></label><label>Автор или герой<select name="author"></select></label><label>Игровой день<select name="day"></select></label><button type="reset">Сбросить фильтры</button><p data-count role="status"></p><small>Фильтры работают по сохранённым сообщениям и проверкам путешествия. Старые сообщения могут быть без даты.</small>`;
 log.before(controls);let campaign='',signature='',entries=[];
 const values=()=>Object.fromEntries(new FormData(controls));
 function options(field,rows){const el=controls.elements[field],value=el.value,markup=rows.map(([v,n])=>`<option value="${esc(v)}">${esc(n)}</option>`).join('');if(el.innerHTML!==markup){el.innerHTML=markup;el.value=rows.some(([v])=>v===value)?value:'';}}
 function draw(changed=false){
  const bottom=log.scrollHeight-log.scrollTop-log.clientHeight<30,f=values(),filtered=filterJournal(entries,f);
  controls.querySelector('[data-count]').textContent=`Показано ${filtered.length} из ${entries.length}`;
  log.innerHTML=filtered.map(e=>`<article class="journal-entry"><div><strong>${esc(e.name)}</strong><span class="journal-kind">${esc(journalKinds[e.kind])}</span>${e.private?'<span class="rule-badge manual">Скрытая проверка Мастера</span>':''}</div><small>${e.day==null?'День не записан':`День ${e.day} · ${quarters[e.quarter]||'четверть не записана'}`}</small><p>${esc(e.text)}</p></article>`).join('')||'<p class="empty-guide">Записей по этим условиям нет. Измените поиск или сбросьте фильтры.</p>';
  if(changed)log.scrollTop=0;else if(bottom)log.scrollTop=log.scrollHeight;
 }
 controls.onsubmit=e=>e.preventDefault();controls.oninput=()=>{sessionStorage.setItem('journal-filters-'+campaign,JSON.stringify(values()));draw(true);};controls.onreset=e=>{e.preventDefault();for(const el of controls.querySelectorAll('input,select'))el.value='';sessionStorage.removeItem('journal-filters-'+campaign);draw(true);};
 function render(){const s=getState();if(!s)return;const next=JSON.stringify([s.id,s.log,s.journey.history,s.me.owner,s.me.role]);if(next===signature)return;signature=next;entries=journalEntries(s);options('author',[['','Все авторы'],...[...new Set(entries.map(e=>e.name))].sort().map(n=>[n,n])]);options('day',[['','Все дни'],...[...new Set(entries.filter(e=>e.day!=null).map(e=>e.day))].sort((a,b)=>a-b).map(n=>[String(n),'День '+n]),...(entries.some(e=>e.day==null)?[['unknown','Без даты']]:[])]);if(campaign!==s.id){campaign=s.id;for(const el of controls.querySelectorAll('input,select'))el.value='';try{const f=JSON.parse(sessionStorage.getItem('journal-filters-'+campaign)||'{}');for(const [k,v] of Object.entries(f))if(controls.elements[k])controls.elements[k].value=v;}catch{} }draw();}
 return {render};
}
