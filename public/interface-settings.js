/* Personal display preferences. No campaign state or account permissions change. */
const KEY='zz-interface-settings',VERSION=1;
const audioDefaults={muted:false,master:50,effects:65,ambience:25,hiddenBehavior:'pause'};
const defaults={version:VERSION,textSize:100,density:'comfortable',motion:'system',contrast:'normal',audio:{...audioDefaults}};
const scriptURL=document.currentScript?.src||new URL('interface-settings.js',location.href).href;
const audioEngine=import(new URL('game-audio.js',scriptURL).href).then(module=>module.gameAudio).catch(()=>null);
import(new URL('loading-scenes.js',scriptURL).href).then(module=>module.installLoadingScenes()).catch(()=>{});
const root=document.documentElement,media=matchMedia('(prefers-reduced-motion: reduce)');
root.dataset.interfaceFamily=location.pathname.endsWith('/tools/index.html')?'sheet':location.pathname.endsWith('/tools/battle.html')?'battle':'table';
function normalize(raw){
 const value=raw&&typeof raw==='object'&&raw.version===VERSION?raw:{};
 const audio=value.audio&&typeof value.audio==='object'?value.audio:{};
 const level=key=>typeof audio[key]==='number'&&Number.isFinite(audio[key])?Math.max(0,Math.min(100,Math.round(audio[key]))):audioDefaults[key];
 return {version:VERSION,textSize:[100,110,125].includes(value.textSize)?value.textSize:100,density:['comfortable','compact'].includes(value.density)?value.density:'comfortable',motion:['system','reduce','full'].includes(value.motion)?value.motion:'system',contrast:value.contrast==='high'?'high':'normal',audio:{muted:typeof audio.muted==='boolean'?audio.muted:false,master:level('master'),effects:level('effects'),ambience:level('ambience'),hiddenBehavior:['pause','duck','continue'].includes(audio.hiddenBehavior)?audio.hiddenBehavior:'pause'}};
}
function read(){
 try{
  const stored=localStorage.getItem(KEY);
  if(stored)return normalize(JSON.parse(stored));
  const reduced=localStorage.getItem('zz-reduced-motion'),dice=localStorage.getItem('dice-animation');
  return {...defaults,motion:reduced==='true'||dice==='off'?'reduce':reduced==='false'?'full':'system'};
 }catch{return {...defaults};}
}
let preferences=read(),dialog,opener,storageAvailable=true,syncing=false;
const reduced=()=>preferences.motion==='reduce'||preferences.motion==='system'&&media.matches;
function announce(message){if(dialog)dialog.querySelector('[data-ui-status]').textContent=message;}
function syncLegacyControls(){
 syncing=true;
 try{
  document.querySelectorAll('[data-reduced-motion]').forEach(control=>{control.checked=reduced();});
  document.querySelectorAll('[data-dice-animation]').forEach(control=>{
   if(control.checked===!reduced())return;
   control.checked=!reduced();control.dispatchEvent(new Event('change',{bubbles:true}));
  });
 }finally{syncing=false;}
}
function save(){
 try{localStorage.setItem(KEY,JSON.stringify(preferences));storageAvailable=true;}
 catch{storageAvailable=false;}
}
function apply(){
 root.dataset.uiText=String(preferences.textSize);root.dataset.uiDensity=preferences.density;root.dataset.uiContrast=preferences.contrast;
 root.style.setProperty('--ui-text-factor',String(preferences.textSize/100));
 root.dataset.reducedMotion=String(reduced());
 try{localStorage.setItem('zz-reduced-motion',String(reduced()));localStorage.setItem('dice-animation',reduced()?'off':'on');}catch{storageAvailable=false;}
 syncLegacyControls();
 if(dialog){
  for(const name of ['textSize','density','motion','contrast'])dialog.querySelector(`[name="${name}"]`).value=String(preferences[name]);
  for(const name of ['master','effects','ambience']){dialog.querySelector(`[data-audio-setting="${name}"]`).value=String(preferences.audio[name]);dialog.querySelector(`[data-audio-value="${name}"]`).textContent=preferences.audio[name]+'%';}
  dialog.querySelector('[data-audio-setting="muted"]').checked=preferences.audio.muted;
  dialog.querySelector('[data-audio-setting="hiddenBehavior"]').value=preferences.audio.hiddenBehavior;
 }
 audioEngine.then(engine=>engine?.configure(preferences.audio));
 window.dispatchEvent(new CustomEvent('zz:interface-settings',{detail:{...preferences,reducedMotion:reduced()}}));
}
function update(value){preferences=normalize({...preferences,...value,audio:{...preferences.audio,...value?.audio},version:VERSION});save();apply();announce(storageAvailable?'Настройки сохранены на этом устройстве.':'Изменения применены. Хранилище недоступно: после закрытия страницы настройки могут сброситься.');}
function createDialog(){
 dialog=document.createElement('dialog');dialog.id='interface-settings-dialog';dialog.className='interface-settings-dialog';dialog.setAttribute('aria-labelledby','interface-settings-title');
 dialog.innerHTML=`<div class="interface-settings-heading"><div><span class="interface-settings-eyebrow">ВАШ ИНТЕРФЕЙС</span><h2 id="interface-settings-title">Настройки</h2></div><button type="button" class="interface-settings-close" data-ui-close aria-label="Закрыть настройки">×</button></div>
 <p class="interface-settings-intro">Настройте удобный вид. Эти параметры действуют только на этом устройстве и не меняют кампанию других участников.</p>
 <div class="interface-settings-fields">
 <label class="interface-setting"><span><strong>Размер текста</strong><small>Более крупные подписи и элементы управления.</small></span><select name="textSize"><option value="100">Обычный · 100%</option><option value="110">Крупный · 110%</option><option value="125">Очень крупный · 125%</option></select></label>
 <label class="interface-setting"><span><strong>Плотность интерфейса</strong><small>Расстояния между карточками и кнопками.</small></span><select name="density"><option value="comfortable">Комфортная</option><option value="compact">Компактная</option></select></label>
 <label class="interface-setting"><span><strong>Анимации</strong><small>Движение костей, вспышки результатов и переходы. Результаты бросков остаются видны.</small></span><select name="motion"><option value="system">Как в системе</option><option value="full">Включены</option><option value="reduce">Меньше движения</option></select></label>
 <label class="interface-setting"><span><strong>Контраст</strong><small>Более чёткие границы и подписи.</small></span><select name="contrast"><option value="normal">Обычный</option><option value="high">Повышенный</option></select></label>
 </div><section class="interface-audio-section" aria-labelledby="interface-audio-title"><h3 id="interface-audio-title">Звук и окружение</h3><p class="interface-settings-intro">Окружение меняется вместе со сценой. Звук включается после первого нажатия; старые броски не озвучиваются повторно.</p><label class="interface-audio-mute"><input type="checkbox" data-audio-setting="muted"> Выключить весь звук</label>
 ${[['master','Общая громкость'],['effects','Действия и броски'],['ambience','Окружение']].map(([name,title])=>`<label class="interface-audio-level"><span>${title}<output data-audio-value="${name}"></output></span><input type="range" min="0" max="100" step="5" data-audio-setting="${name}" aria-label="${title}"></label>`).join('')}
 <label class="interface-setting"><span><strong>Когда игра скрыта</strong><small>При другой вкладке, сворачивании или переходе к настройкам приложения.</small></span><select data-audio-setting="hiddenBehavior"><option value="pause">Приостановить звук</option><option value="duck">Сделать тише</option><option value="continue">Продолжать</option></select></label><label class="interface-setting"><span><strong>Пробный звук</strong><small>Короткий пример только для вас. Не меняет сцену и не звучит у других игроков.</small></span><select data-audio-preview aria-label="Пробный звук"><option value="metal" data-kind="effect">Звон металла</option></select></label><button type="button" data-audio-test>Проверить звук</button></section>
 <p class="interface-settings-status" data-ui-status role="status" aria-live="polite">Изменения применяются сразу.</p>
 <div class="interface-settings-footer"><button type="button" data-ui-reset>Сбросить настройки</button><button type="button" class="interface-settings-done" data-ui-close>Готово</button></div><p class="interface-settings-shortcut"><kbd>Ctrl</kbd> + <kbd>,</kbd> — открыть · <kbd>Esc</kbd> — закрыть</p>`;
 document.body.append(dialog);
 const changeAudio=event=>{const control=event.target,name=control.dataset.audioSetting;if(name)update({audio:{[name]:control.type==='checkbox'?control.checked:control.type==='range'?Number(control.value):control.value}});};
 dialog.addEventListener('input',event=>{if(event.target.matches('input[type=range][data-audio-setting]'))changeAudio(event);});
 dialog.addEventListener('change',event=>{const control=event.target;if(control.dataset.audioSetting){if(control.type!=='range')changeAudio(event);return;}if(!control.matches('.interface-setting select')||!['textSize','density','motion','contrast'].includes(control.name))return;update({[control.name]:control.name==='textSize'?Number(control.value):control.value});});
 const preview=dialog.querySelector('[data-audio-preview]');
 fetch(new URL('audio-catalog.json',scriptURL),{cache:'force-cache'}).then(response=>{if(!response.ok)throw Error('catalog');return response.json();}).then(catalog=>{
  const selected=preview.value,groups=new Map();
  for(const [kind,label] of [['effect','Эффекты'],['ambience','Окружение · до 5 секунд'],['synthetic','Синтезированные']]){const group=document.createElement('optgroup');group.label=label;groups.set(kind,group);}
  for(const clip of [...(catalog.clips||[]),...(catalog.synthesized||[]).map(clip=>({...clip,kind:'synthetic'}))]){
   if(!/^[a-z0-9-]+$/.test(clip.id)||!groups.has(clip.kind)||typeof clip.title!=='string')continue;
   const option=document.createElement('option');option.value=clip.id;option.textContent=clip.title;option.dataset.kind=clip.kind;groups.get(clip.kind).append(option);
  }
  preview.replaceChildren(...groups.values());preview.value=[...preview.options].some(option=>option.value===selected)?selected:'metal';
 }).catch(()=>{});
 dialog.querySelector('[data-audio-test]').addEventListener('click',async()=>{const engine=await audioEngine;if(!engine){announce('Звуковой модуль пока недоступен. Попробуйте обновить страницу.');return;}const ambient=preview.selectedOptions[0]?.dataset.kind==='ambience';if(preferences.audio.muted||!preferences.audio.master||!(ambient?preferences.audio.ambience:preferences.audio.effects)){announce('Для проверки включите звук и поднимите общую громкость и громкость '+(ambient?'окружения.':'действий.'));return;}announce(await engine.test(preview.value)?'Пробный звук: '+preview.selectedOptions[0].textContent+'. Остановится автоматически.':'Звук пока недоступен. Проверьте соединение и нажмите «Проверить звук» ещё раз.');});
 dialog.querySelectorAll('[data-ui-close]').forEach(button=>button.addEventListener('click',()=>dialog.close()));
 dialog.querySelector('[data-ui-reset]').addEventListener('click',()=>update(defaults));
 dialog.addEventListener('close',()=>{if(opener?.isConnected)opener.focus({preventScroll:true});});
}
function open(){if(!dialog)createDialog();opener=document.activeElement;apply();if(!dialog.open)dialog.showModal();dialog.querySelector('[name=textSize]').focus();}
document.addEventListener('click',event=>{if(event.target.closest('[data-interface-settings]'))open();});
document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.code==='Comma'&&!event.altKey){event.preventDefault();open();}});
document.addEventListener('change',event=>{
 if(syncing)return;
 if(event.target.matches('[data-reduced-motion]'))update({motion:event.target.checked?'reduce':'full'});
 if(event.target.matches('[data-dice-animation]'))update({motion:event.target.checked?'full':'reduce'});
});
window.addEventListener('storage',event=>{
 if(event.key===KEY||event.key===null){preferences=read();apply();announce('Настройки обновлены в другой вкладке.');}
 // The two legacy keys are outputs, not another source of truth: system
 // motion can differ between windows, and echoing these writes causes loops.
});
media.addEventListener('change',()=>{if(preferences.motion==='system')apply();});
window.ZZInterfaceSettings=Object.freeze({open,get:()=>({...preferences,audio:{...preferences.audio}}),set:value=>update(value)});
save();apply();
