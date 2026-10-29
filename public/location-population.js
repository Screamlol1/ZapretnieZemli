import tables from './settlement-population-data.json' with {type:'json'};
import {esc} from './location-render.js';
import {cultureAssets} from './location-themes.js';
import {buildingLabel} from './location-residents.js';

const option=(id,label,value)=>`<option value="${esc(id)}" ${id===value?'selected':''}>${esc(label)}</option>`;
const options=(labels,value)=>Object.entries(labels).map(([id,label])=>option(id,typeof label==='string'?label:label.label,value)).join('');
const input=(label,name,value='',limit=60)=>`<label>${label}<input name="${name}" value="${esc(value)}" maxlength="${limit}" ${name==='name'?'required':''}></label>`;
const textarea=(label,name,value='')=>`<label>${label}<textarea name="${name}" maxlength="1200" rows="3">${esc(value)}</textarea></label>`;
const checked=(label,name,value)=>`<label class="population-check"><input name="${name}" type="checkbox" ${value?'checked':''}> ${label}</label>`;
const roleName=id=>tables.roles[id]?.label||id||'Житель';
const kinName=id=>tables.kins[id]?.label||id||'';
const normalized=value=>String(value||'').toLowerCase().replaceAll('ё','е');

// Residents are address records, independent of combat tokens and actor sheets.
export function locationPopulation({root,current,seenMap,getState,run,showFeature}){
 const panel=document.createElement('details');panel.className='location-population';panel.dataset.populationPanel='';root.querySelector('.location-layout').after(panel);
 let signature='',query='',role='',limit=60,lastMap='';
 const canEdit=()=>getState()?.me.role==='gm'&&!root.querySelector('[data-location-player-view]').checked;
 const data=()=>{const raw=seenMap()?.population;return {...raw,households:raw?.households||[],residents:raw?.residents||[]};};
 const feature=id=>seenMap()?.features.find(f=>f.id===id);
 const household=id=>data().households.find(h=>h.id===id);
 const address=id=>id&&feature(id)?buildingLabel(seenMap(),feature(id)):'Не назначено';
 const visibilityReasons=r=>{const h=household(r.householdId);return [!r.revealed?'Житель скрыт':'',!h?.revealed?'Семья скрыта':'',feature(h?.homeFeatureId)?.secret?'Дом скрыт':'',feature(r.workplaceFeatureId)?.secret?'Место работы скрыто':''].filter(Boolean);};
 const jump=(id,label)=>id&&feature(id)?`<button type="button" class="population-address" data-pop-place="${esc(id)}">${esc(label==='Дом'?'Живёт':label==='Работа'?'Работает':label)} → ${esc(address(id))}</button>`:`<span class="muted">${esc(label)}: не назначено</span>`;
 const suitable=f=>{const art=f.art||f.style,role=f.themeRole||cultureAssets.find(a=>a.id===art)?.role;return ['building','thatch','shingle','tile','barn','tavern','smithy','chapel','manor','keep','tower','tent','pavilion','room','cave','ruin'].includes(art)||['home','hall','shelter'].includes(role);};
 function buildings(value,workplace=false){return '<option value="">Не назначено</option>'+seenMap().features.filter(f=>workplace||suitable(f)).map(f=>option(f.id,`${buildingLabel(seenMap(),f)}${f.secret?' · скрыто':''}`,value)).join('');}
 function modal(title,body,submit){
  const dialog=document.createElement('dialog');dialog.className='item-dialog population-dialog';dialog.innerHTML=`<form><h2>${esc(title)}</h2>${body}<p class="editor-error" role="alert"></p><div class="toolbar"><button>Сохранить</button><button type="button" data-cancel>Отмена</button></div></form>`;document.body.append(dialog);dialog.showModal();dialog.onclose=()=>dialog.remove();dialog.querySelector('[data-cancel]').onclick=()=>dialog.close();dialog.querySelector('form').onsubmit=async e=>{e.preventDefault();const button=dialog.querySelector('.toolbar button');button.disabled=true;try{if(await submit(new FormData(e.target)))dialog.close();else dialog.querySelector('.editor-error').textContent=root.querySelector('[data-location-error]').textContent||'Не удалось сохранить. Обновите данные и повторите.';}catch(error){dialog.querySelector('.editor-error').textContent=error.message;}finally{button.disabled=false;}};return dialog;
 }
 function residentForm(resident={}){
  if(!canEdit())return;const m=current(),p=data();
  modal(resident.id?'Изменить жителя':'Новый житель',`<div class="location-fields">${input('Имя','name',resident.name)}<label>Народ<select name="kin">${options(tables.kins,resident.kin||'human')}</select></label><label>Возраст<select name="ageGroup">${options(tables.ageGroups,resident.ageGroup||'adult')}</select></label><label>Роль<select name="role">${options(tables.roles,resident.role||'laborer')}</select></label></div>${input('Занятие','occupation',resident.occupation,80)}<label>Семья / дом<select name="householdId"><option value="">Создать отдельный дом для этого жителя</option>${p.households.map(h=>option(h.id,h.name,resident.householdId)).join('')}</select></label><label>Роль в семье<select name="familyRole">${options(tables.familyRoles,resident.familyRole||'member')}</select></label><label>Место работы / службы<select name="workplaceFeatureId">${buildings(resident.workplaceFeatureId,true)}</select></label><p class="muted">Адрес проживания задаётся у семьи. Место работы может находиться в другом здании.</p>${textarea('Описание для игроков','description',resident.description)}${textarea('Заметка Мастера','gmNote',resident.gmNote)}${checked('Показывать этого жителя игрокам','revealed',resident.revealed)}<p class="muted">Житель появится у игроков, когда открыты его семья, дом, место работы и сама карта. Заметка Мастера остаётся скрытой.</p>`,v=>run({action:'locationMapResidentSave',id:m.id,version:m.version,resident:{...resident,...Object.fromEntries(v),revealed:v.has('revealed')}}));
 }
 function householdForm(h={},home=''){
  if(!canEdit())return;const m=current();
  modal(h.id?'Изменить семью / дом':'Новая семья / дом',`${input('Название семьи / дома','name',h.name)}<label>Где живут<select name="homeFeatureId">${buildings(h.homeFeatureId||home)}</select></label><p class="muted">Все члены семьи используют этот адрес. В одном здании могут жить несколько семей.</p>${textarea('Описание для игроков','note',h.note)}${textarea('Заметка Мастера','gmNote',h.gmNote)}${checked('Показывать семью и её адрес игрокам','revealed',h.revealed)}`,v=>run({action:'locationMapHouseholdSave',id:m.id,version:m.version,household:{...h,...Object.fromEntries(v),revealed:v.has('revealed')}}));
 }
 function generate(){
  if(!canEdit())return;const m=current(),existing=data().residents.length,defaultCount=Math.min(20,400-existing)||1;
  const dialog=modal('Создать жителей',`<p>Создаются жители и семьи с адресами на существующем плане. Здания, дороги и ваши заметки сохраняются.</p><div class="location-fields"><label>Число новых жителей<input name="count" type="number" min="1" max="400" value="${defaultCount}" required></label><label>Состав<select name="mode">${options(tables.modes,'mixed')}</select></label><label>Народ<select name="kin"><option value="mixed">Разные народы</option>${options(tables.kins,m.culture)}</select></label>${input('Зерно генерации (необязательно)','seed','',80)}</div>${existing?'<label>Существующие жители<select name="operation"><option value="append">Сохранить и добавить новых</option><option value="replace">Заменить население целиком…</option></select></label>':''}${checked('Сразу показать жителей и семьи игрокам','revealed',false)}<p class="muted">Имена, родственные связи и занятия — авторские заготовки для игры. При необходимости измените их вручную. Максимум 400 жителей на локацию.</p>`,v=>{const replace=v.get('operation')==='replace';if(replace&&!confirm('Заменить всех жителей и семьи этого поселения? Их ручные изменения будут заменены. План останется прежним.'))return false;return run({action:'locationMapPopulationGenerate',id:m.id,version:m.version,count:Number(v.get('count')),mode:v.get('mode'),kin:v.get('kin'),seed:v.get('seed'),append:!!existing&&!replace,replace,revealed:v.has('revealed')});});dialog.querySelector('.toolbar button').textContent='Создать жителей';
 }
 function residentCard(r,compact=false){
  const h=household(r.householdId),gm=canEdit();
  return `<article class="population-resident" data-pop-resident="${esc(r.id)}"><div><strong>${esc(r.name)}</strong><span class="population-role">${esc(r.occupation||roleName(r.role))}</span>${gm&&visibilityReasons(r).length?`<small class="population-visibility" data-pop-visibility>Не виден игрокам: ${esc(visibilityReasons(r).join(' · '))}</small>`:''}</div><p>${esc([kinName(r.kin),tables.ageGroups[r.ageGroup],tables.familyRoles[r.familyRole],h?.name].filter(Boolean).join(' · '))}</p><div class="population-addresses">${jump(h?.homeFeatureId,'Дом')}${jump(r.workplaceFeatureId,'Работа')}</div>${r.description&&!compact?`<p class="location-note">${esc(r.description)}</p>`:''}${gm?`<div class="toolbar"><button type="button" data-pop-edit="${esc(r.id)}">Изменить</button><button type="button" data-pop-reveal="${esc(r.id)}">${r.revealed?'Скрыть':'Показать игрокам'}</button><button type="button" data-pop-delete="${esc(r.id)}">Удалить</button></div>`:''}</article>`;
 }
 function list(){
  const p=data(),q=normalized(query),filtered=p.residents.filter(r=>!role||r.role===role).filter(r=>normalized([r.name,r.occupation,roleName(r.role),household(r.householdId)?.name,r.description].join(' ')).includes(q));
  panel.querySelector('[data-pop-results]').innerHTML=filtered.slice(0,limit).map(r=>residentCard(r)).join('')||'<p>Подходящих жителей не найдено.</p>';
  panel.querySelector('[data-pop-count]').textContent=`Показано ${Math.min(limit,filtered.length)} из ${filtered.length}`;
  panel.querySelector('[data-pop-more]').hidden=filtered.length<=limit;
  const households=p.households.filter(h=>!q||normalized(h.name+' '+h.note).includes(q)||filtered.some(r=>r.householdId===h.id));
  panel.querySelector('[data-pop-households]').innerHTML=households.map(h=>`<article class="population-household" data-pop-household="${esc(h.id)}"><strong>${esc(h.name)}</strong>${canEdit()&&!h.revealed?'<small class="muted">Скрыта от игроков</small>':''}<p>${p.residents.filter(r=>r.householdId===h.id).length} жителей</p><ul class="population-family-members">${p.residents.filter(r=>r.householdId===h.id).map(r=>`<li>${esc(r.name)} · ${esc(tables.familyRoles[r.familyRole]||'Член дома')}</li>`).join('')}</ul>${jump(h.homeFeatureId,'Живут')}${h.note?`<p class="location-note">${esc(h.note)}</p>`:''}${canEdit()?`<button type="button" data-pop-edit-household="${esc(h.id)}">Изменить семью и адрес</button>`:''}</article>`).join('')||'<p>Семьи пока не указаны.</p>';
 }
 function render(){
  const m=seenMap(),gm=canEdit(),p=m?.population;panel.hidden=!m||!p&&!['settlement','camp','fortress'].includes(m.kind);root.querySelector('.location-controls [data-pop-open]').hidden=panel.hidden;root.querySelector('[data-location-population]').closest('label').hidden=panel.hidden;if(panel.hidden)return;
  if(lastMap!==m.id){lastMap=m.id;query='';role='';limit=60;signature='';}
  const next=JSON.stringify([m.id,p,m.features.map(f=>[f.id,f.label,f.secret]),gm]);if(signature===next)return;signature=next;
  const familyOpen=panel.querySelector('[data-pop-family-list]')?.open||false;
  panel.innerHTML=`<summary>Жители и семьи · ${p?.residents?.length||0} жителей · ${p?.households?.length||0} семей</summary><p>Дом и место работы показывают, где живёт и трудится персонаж. Это адреса, а не его текущее положение на карте.</p>${gm?`<div class="toolbar population-actions"><button type="button" data-pop-generate class="primary-action">Создать случайных жителей</button><button type="button" data-pop-new>＋ Житель вручную</button><button type="button" data-pop-new-household>＋ Семья / дом</button>${p?'<button type="button" data-pop-assign>Назначить недостающие адреса</button><button type="button" data-pop-reveal-all>Показать всех игрокам</button><button type="button" data-pop-hide-all>Скрыть всех</button>':''}</div><p class="muted">По умолчанию случайные жители создаются скрытыми. Откройте нужных людей, семьи и саму карту игрокам отдельно.</p>`:''}${!p?.residents?.length?'<p class="empty-guide">Здесь пока нет доступных жителей.</p>':''}<div class="location-fields population-filters"><label>Поиск по имени, занятию, семье<input type="search" data-pop-search value="${esc(query)}" placeholder="Кузнец, стражник, имя…"></label><label>Роль<select data-pop-role><option value="">Все занятия</option>${options(tables.roles,role)}</select></label></div><p data-pop-count class="muted"></p><div class="population-residents" data-pop-results></div><button type="button" data-pop-more>Показать ещё 60</button><details data-pop-family-list ${familyOpen?'open':''}><summary>Семьи и адреса</summary><div class="population-households" data-pop-households></div></details>`;list();
 }
 function featureContent(f){
  if(!f)return '';const p=data(),homes=p.households.filter(h=>h.homeFeatureId===f.id),ids=new Set(homes.map(h=>h.id)),living=p.residents.filter(r=>ids.has(r.householdId)),working=p.residents.filter(r=>r.workplaceFeatureId===f.id);
  if(!living.length&&!working.length&&!canEdit())return '';
  const people=rows=>rows.length?rows.map(r=>`<li><strong>${esc(r.name)}</strong> · ${esc(r.occupation||roleName(r.role))}${canEdit()?` <button type="button" data-pop-edit="${esc(r.id)}" aria-label="Изменить: ${esc(r.name)}">Изменить</button>`:''}</li>`).join(''):'<li class="muted">Пока никто не указан.</li>';
  return `<section class="population-feature" data-pop-feature="${esc(f.id)}"><h3>Здесь живут · ${living.length}</h3>${homes.map(h=>`<p>${esc(h.name)}${canEdit()?` <button type="button" data-pop-edit-household="${esc(h.id)}">Семья и адрес</button>`:''}</p>`).join('')}<ul>${people(living)}</ul><h3>Здесь работают · ${working.length}</h3><ul>${people(working)}</ul>${canEdit()&&suitable(f)?`<button type="button" data-pop-home="${esc(f.id)}">Поселить новую семью здесь</button>`:''}<button type="button" data-pop-open>Все жители и семьи</button></section>`;
 }
 function open(){render();if(panel.hidden)return;panel.open=true;panel.scrollIntoView({block:'start',behavior:'smooth'});}
 panel.addEventListener('input',e=>{if(e.target.hasAttribute('data-pop-search')){query=e.target.value;limit=60;list();}});
 panel.addEventListener('change',e=>{if(e.target.hasAttribute('data-pop-role')){role=e.target.value;limit=60;list();}});
 root.addEventListener('click',async e=>{
  const b=e.target.closest('button');if(!b)return;const d=b.dataset,m=current();
  if(d.popPlace){showFeature(d.popPlace);return;}if('popOpen'in d){open();return;}if(!m)return;
  if('popMore'in d){limit+=60;list();return;}if(!canEdit())return;
  if('popGenerate'in d)generate();if('popNew'in d)residentForm();if('popNewHousehold'in d)householdForm();if(d.popHome)householdForm({},d.popHome);
  if(d.popEdit)residentForm(data().residents.find(r=>r.id===d.popEdit));if(d.popEditHousehold)householdForm(household(d.popEditHousehold));
  if(d.popReveal){const r=data().residents.find(r=>r.id===d.popReveal);if(r)await run({action:'locationMapResidentSave',id:m.id,version:m.version,resident:{id:r.id,revealed:!r.revealed}});}
  if(d.popDelete&&confirm('Удалить этого жителя? Другие члены семьи останутся.'))await run({action:'locationMapResidentDelete',id:m.id,version:m.version,resident:d.popDelete,confirmed:true});
  if('popAssign'in d)await run({action:'locationMapPopulationAssign',id:m.id,version:m.version});
  if('popRevealAll'in d&&confirm('Показать игрокам всех жителей и семьи? Скрытые здания и заметки Мастера останутся скрытыми.'))await run({action:'locationMapPopulationReveal',id:m.id,version:m.version,revealed:true});
  if('popHideAll'in d)await run({action:'locationMapPopulationReveal',id:m.id,version:m.version,revealed:false});
 });
 return {render,open,featureContent};
}
