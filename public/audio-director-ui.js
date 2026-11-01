import {gameAudio} from './game-audio.js';

const AMBIENTS=[
 ['auto','По текущей сцене','Фон выбирается по месту и обстановке.','Режим'],
 ['silent','Без общего фона','Убрать атмосферу; разовые звуки остаются.','Режим'],
 ['forest','Лес','Шорохи и голоса леса.','Места'],['cave','Пещера','Глубина и эхо подземелья.','Места'],
 ['river','Река','Течение и плеск воды.','Места'],['marsh','Болото','Звуки топи и влажных низин.','Места'],
 ['city','Поселение','Улицы и повседневная жизнь.','Места'],['tavern','Таверна','Шум общего зала.','Места'],
 ['battle','Сражение','Столкновение оружия и шум боя.','Обстановка'],['wind','Ветер','Открытые пространства и перевалы.','Обстановка'],
 ['fire','Костёр','Потрескивание огня на привале.','Обстановка'],['rain','Дождь','Непогода над отрядом.','Обстановка'],['night','Ночь','Ночная атмосфера.','Обстановка']
];
const CUES=[['metal','Звон металла'],['footstep','Шаги по листве'],['monster','Рёв чудовища'],['wolf','Рычание волка'],['break','Разбитое стекло'],['thunder','Гром'],['bell','Колокол'],['blacksmith','Кузница'],['snow-step','Шаги по снегу'],['dice','Кости'],['magic','Магический отклик']];
const ambientNames=new Map(AMBIENTS.map(([id,name])=>[id,name])),cueNames=new Map(CUES);
const speaker='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9h4l5-4v14l-5-4H4Zm12-1a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/></svg>';
const director=s=>({version:Number.isInteger(s?.audioDirector?.version)?s.audioDirector.version:0,ambient:ambientNames.has(s?.audioDirector?.ambient)?s.audioDirector.ambient:'auto',cues:Array.isArray(s?.audioDirector?.cues)?s.audioDirector.cues:[]});
const supported=s=>Number.isInteger(s?.audioDirector?.version)&&ambientNames.has(s?.audioDirector?.ambient);

export function audioDirectorUI(getState,send){
 if(!document.getElementById('audio-director-style')){const link=document.createElement('link');link.id='audio-director-style';link.rel='stylesheet';link.href=new URL('./audio-director-ui.css',import.meta.url).href;document.head.append(link);}
 const bar=document.createElement('div');bar.className='audio-director-status';
 bar.innerHTML=`<div class="audio-director-status-copy"><span class="audio-director-status-icon">${speaker}</span><div><strong data-audio-shared></strong><small data-audio-local></small><small data-audio-compat hidden>Пульт станет доступен после обновления сервера.</small></div></div><div class="audio-director-status-actions"><button type="button" data-audio-open>Атмосфера и звуки</button><button type="button" data-audio-settings>Мой звук</button></div>`;
 let dialog=null,host=null,scope='',baseAmbient='auto',baseVersion=0,dirty=false,stale=false,pending='',previewGeneration=0,restoreFocus=null,lastStatus='';
 const query=selector=>dialog?.querySelector(selector);
 function localStatus(){const audio=gameAudio.getState(),o=audio.options||{};if(o.muted||o.master===0)return 'У вас: звук выключен';if(audio.hidden&&o.hiddenBehavior==='pause')return 'У вас: звук на паузе';if(o.ambience===0)return 'У вас: фоновая громкость 0%';if(!audio.unlocked)return 'У вас: звук включится после нажатия';return `У вас: громкость ${o.master??50}%, фон ${o.ambience??25}%`;}
 function feedback(message='',error=false){if(!dialog)return;const element=query('[data-audio-feedback]');element.textContent=message;element.hidden=!message;element.dataset.error=String(error);}
 function personalSettings(){if(window.ZZInterfaceSettings?.open)window.ZZInterfaceSettings.open();else feedback('Настройки звука ещё загружаются. Попробуйте через несколько секунд.',true);}
 function cancelPreview(message=false){previewGeneration++;gameAudio.stopPreview?.();if(pending==='preview')pending='';if(message)feedback('Локальная проба остановлена. Общая атмосфера не изменена.');updateControls();}
 function close(){if(pending&&pending!=='preview')return;cancelPreview();dialog?.close();}
 function fillAmbient(){const d=director(getState());baseAmbient=d.ambient;baseVersion=d.version;dirty=false;stale=false;for(const input of dialog.querySelectorAll('[name="audio-ambient"]'))input.checked=input.value===d.ambient;updateControls();}
 function selectAmbient(){if(pending)return;const d=director(getState());baseAmbient=d.ambient;baseVersion=d.version;stale=false;dirty=query('[name="audio-ambient"]:checked')?.value!==d.ambient;feedback();updateControls();}
 function tab(name){for(const button of dialog.querySelectorAll('[data-audio-tab]')){const selected=button.dataset.audioTab===name;button.setAttribute('aria-selected',String(selected));button.tabIndex=selected?0:-1;query('#'+button.getAttribute('aria-controls')).hidden=!selected;}updateControls();}
 function updateControls(){
  if(!dialog)return;const s=getState(),d=director(s),gm=s?.me?.role==='gm',selected=query('[name="audio-ambient"]:checked')?.value||'auto',cue=query('[name="audio-cue"]')?.value||'metal';
  for(const input of dialog.querySelectorAll('input,select'))input.disabled=!!pending||!gm;
  for(const button of dialog.querySelectorAll('button'))button.disabled=!!pending;
  for(const button of dialog.querySelectorAll('[data-audio-close]'))button.disabled=!!pending&&pending!=='preview';
  query('[data-audio-ambient-apply]').disabled=!!pending||!gm||stale||selected===d.ambient;
  query('[data-audio-ambient-preview]').disabled=!!pending||['auto','silent'].includes(selected);
  query('[data-audio-cue-send]').disabled=!!pending||!gm;
  query('[data-audio-stop]').disabled=typeof gameAudio.stopPreview!=='function';
  query('[data-audio-stale]').hidden=!stale;
  query('[data-audio-current]').textContent='Общая атмосфера: '+ambientNames.get(d.ambient);
  query('[data-audio-local-status]').textContent=localStatus();
  query('[data-audio-selected-cue]').textContent=cueNames.get(cue)||'Разовый звук';
  query('[data-audio-ambient-apply]').textContent=pending==='ambient'?'Сохраняем атмосферу…':selected==='silent'?'Убрать общий фон':selected==='auto'?'Включить выбор по сцене':'Применить атмосферу';
  query('[data-audio-cue-send]').textContent=pending==='cue'?'Отправляем звук…':'Воспроизвести всем';
  query('[data-audio-pending]').textContent=pending==='preview'?'Загружаем локальную пробу…':pending?'Дожидаемся подтверждения сервера.':'';
  const last=d.cues.at(-1);let lastText='Общие разовые звуки пока не отправлялись.';
  if(last&&cueNames.has(last.type)){const date=new Date(Number(last.at)*1000),time=Number.isNaN(date.getTime())?'':date.toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit',second:'2-digit'});lastText='Последний общий звук: '+cueNames.get(last.type)+(time?' · '+time:'');}
  query('[data-audio-last]').textContent=lastText;
 }
 async function run(kind,operation,success){if(pending)return;pending=kind;feedback();updateControls();try{const result=await operation();if(result===false)throw Error(document.getElementById('error')?.textContent?.trim()||'Действие не подтверждено. Проверьте связь и повторите после обновления состояния.');if(kind==='ambient'){dirty=false;stale=false;fillAmbient();}feedback(success);}catch(error){feedback(String(error?.message||'Не удалось выполнить действие.'),true);}finally{pending='';render();updateControls();}}
 async function preview(type){if(pending)return;const generation=++previewGeneration;pending='preview';feedback();updateControls();try{const played=await gameAudio.test(type);if(generation!==previewGeneration)return;feedback(played?'Проба запущена только у вас. Участники её не получают.':'Проба не запущена. Проверьте «Мой звук», общую громкость и громкость нужного канала.',!played);}catch{if(generation===previewGeneration)feedback('Не удалось загрузить локальную пробу. Проверьте соединение и настройки звука.',true);}finally{if(generation===previewGeneration){pending='';updateControls();}}}
 function makeDialog(){
  dialog=document.createElement('dialog');dialog.id='audio-director-dialog';dialog.className='audio-director-dialog';dialog.setAttribute('aria-labelledby','audio-director-title');
  dialog.innerHTML=`<header class="audio-director-heading"><div><span class="audio-director-eyebrow">ПУЛЬТ МАСТЕРА</span><h2 id="audio-director-title">Атмосфера и звуки</h2></div><button type="button" data-audio-close aria-label="Закрыть пульт звука">×</button></header><p class="audio-director-intro">Общий фон и звуковые акценты для кампании. У каждого участника остаются свои громкость и выключатель звука.</p><div class="audio-director-now"><div><strong data-audio-current></strong><small data-audio-local-status></small></div><button type="button" data-audio-personal>Мои настройки звука</button></div><nav class="audio-director-tabs" role="tablist" aria-label="Разделы пульта звука"><button type="button" role="tab" id="audio-tab-ambient" data-audio-tab="ambient" aria-controls="audio-panel-ambient" aria-selected="true">Атмосфера</button><button type="button" role="tab" id="audio-tab-cues" data-audio-tab="cues" aria-controls="audio-panel-cues" aria-selected="false" tabindex="-1">Разовые звуки</button></nav><div class="audio-director-body"><section id="audio-panel-ambient" role="tabpanel" aria-labelledby="audio-tab-ambient"><p class="audio-director-explanation">Выбор карточки ещё ничего не меняет у игроков. Примените атмосферу, когда будете готовы.</p>${['Режим','Места','Обстановка'].map(group=>`<fieldset class="audio-director-group"><legend>${group}</legend><div class="audio-director-options">${AMBIENTS.filter(item=>item[3]===group).map(([id,name,description])=>`<label class="audio-director-option"><input type="radio" name="audio-ambient" value="${id}"><span><strong>${name}</strong><small>${description}</small></span><i aria-hidden="true">✓</i></label>`).join('')}</div></fieldset>`).join('')}<div class="audio-director-conflict" data-audio-stale hidden><p>Общая атмосфера изменилась, пока вы выбирали. Ваш выбор сохранён в форме. Выберите фон ещё раз либо загрузите актуальный общий выбор.</p><button type="button" data-audio-refresh>Обновить общий выбор</button></div><div class="audio-director-apply"><button type="button" data-audio-ambient-preview>Прослушать у себя · до 5 сек.</button><button type="button" class="audio-director-primary" data-audio-ambient-apply>Применить атмосферу</button></div><p class="audio-director-hint">«Без общего фона» выключает только атмосферу. Кости и разовые эффекты сохраняют свои настройки.</p></section><section id="audio-panel-cues" role="tabpanel" aria-labelledby="audio-tab-cues" hidden><label class="audio-director-cue-label" for="audio-director-cue">Звуковой акцент<select id="audio-director-cue" name="audio-cue">${CUES.map(([id,name])=>`<option value="${id}">${name}</option>`).join('')}</select></label><div class="audio-director-cue-card"><span class="audio-director-cue-art">${speaker}</span><div><small>РАЗОВЫЙ ЗВУК</small><h3 data-audio-selected-cue>Звон металла</h3><p>Сначала можно прослушать пробу у себя. Кнопка «Воспроизвести всем» отправляет один новый звук участникам кампании.</p></div></div><div class="audio-director-cue-actions"><button type="button" data-audio-cue-preview>Прослушать у себя</button><button type="button" class="audio-director-primary" data-audio-cue-send>Воспроизвести всем</button></div><p class="audio-director-last" data-audio-last></p><p class="audio-director-hint">Отправка не включает звук принудительно: каждый игрок управляет своей громкостью. Быстрые повторные нажатия ограничены.</p></section></div><p class="audio-director-feedback" data-audio-feedback role="status" aria-live="polite" hidden></p><footer class="audio-director-footer"><div><button type="button" data-audio-stop>Остановить пробу</button><span data-audio-pending role="status"></span></div><button type="button" data-audio-close>Закрыть</button></footer>`;
  document.body.append(dialog);
  dialog.querySelectorAll('[data-audio-close]').forEach(button=>button.onclick=close);
  dialog.addEventListener('cancel',event=>{event.preventDefault();close();});
  dialog.addEventListener('close',()=>{cancelPreview();if(restoreFocus?.isConnected)restoreFocus.focus();restoreFocus=null;});
  query('[data-audio-personal]').onclick=personalSettings;query('[data-audio-refresh]').onclick=()=>{fillAmbient();feedback('Общий выбор обновлён. Теперь можно выбрать другую атмосферу.');};
  for(const input of dialog.querySelectorAll('[name="audio-ambient"]')){input.onclick=selectAmbient;input.onchange=selectAmbient;}
  query('[name="audio-cue"]').onchange=()=>{feedback();updateControls();};
  for(const button of dialog.querySelectorAll('[data-audio-tab]')){button.onclick=()=>tab(button.dataset.audioTab);button.onkeydown=event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const next=event.key==='Home'?'ambient':event.key==='End'?'cues':button.dataset.audioTab==='ambient'?'cues':'ambient';tab(next);query('[data-audio-tab="'+next+'"]').focus();};}
  query('[data-audio-ambient-preview]').onclick=()=>preview(query('[name="audio-ambient"]:checked')?.value);
  query('[data-audio-cue-preview]').onclick=()=>preview(query('[name="audio-cue"]').value);
  query('[data-audio-stop]').onclick=()=>cancelPreview(true);
  query('[data-audio-ambient-apply]').onclick=()=>{
   const s=getState(),d=director(s);if(s?.me?.role!=='gm'||pending)return;
   if(d.ambient!==baseAmbient){stale=true;feedback('Общая атмосфера уже изменилась. Обновите общий выбор или выберите фон ещё раз.',true);updateControls();return;}
   baseVersion=d.version;const ambient=query('[name="audio-ambient"]:checked')?.value||'auto';
   run('ambient',()=>send({action:'audioDirector',op:'ambient',version:baseVersion,ambient}),'Общая атмосфера сохранена. Каждый участник слышит её с собственной громкостью.');
  };
  query('[data-audio-cue-send]').onclick=()=>{if(getState()?.me?.role!=='gm')return;run('cue',()=>send({action:'audioDirector',op:'cue',cue:query('[name="audio-cue"]').value}),'Звуковой акцент отправлен участникам. Их личные настройки громкости сохранены.');};
 }
 function open(){const s=getState();if(s?.me?.role!=='gm'||!supported(s))return;if(!dialog)makeDialog();if(dialog.open)return;scope=String(s.id||s.code||'');pending='';restoreFocus=document.activeElement;fillAmbient();feedback();tab('ambient');dialog.showModal();query('[data-audio-tab="ambient"]').focus();}
 bar.querySelector('[data-audio-open]').onclick=open;bar.querySelector('[data-audio-settings]').onclick=personalSettings;
 function render(mount){
  if(mount&&mount!==host){host=mount;host.append(bar);}const s=getState();bar.hidden=!s;if(!s){if(dialog?.open)dialog.close();return;}
  const d=director(s),local=localStatus(),available=supported(s),signature=JSON.stringify([s.me?.role,d.ambient,local,available]);if(signature!==lastStatus){lastStatus=signature;bar.querySelector('[data-audio-shared]').textContent='Атмосфера: '+ambientNames.get(d.ambient);bar.querySelector('[data-audio-local]').textContent=local;bar.querySelector('[data-audio-open]').hidden=s.me?.role!=='gm';bar.querySelector('[data-audio-open]').disabled=!available;bar.querySelector('[data-audio-compat]').hidden=available||s.me?.role!=='gm';}
  if(dialog?.open){if(s.me?.role!=='gm'||!available||String(s.id||s.code||'')!==scope){dialog.close();return;}if(!pending){if(d.ambient!==baseAmbient){if(dirty)stale=true;else fillAmbient();}else if(!stale)baseVersion=d.version;}updateControls();}
 }
 for(const event of ['zz:interface-settings','zz:audio-status','zz:audio-ambience'])window.addEventListener(event,()=>render());
 return {render,open};
}
