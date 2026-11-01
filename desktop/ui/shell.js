'use strict';
const shellApi=window.desktop,$=id=>document.getElementById(id);
let state={view:'home',preferences:{mode:'windowed',width:1440,height:1000,zoom:100,rememberWindow:true,confirmExit:true},display:{width:1920,height:1080}},busy=false,dirty=false,opened=false,restoreFocus=null,pendingSignature='',pendingUntil=0;
let diagnosticsBusy=false;
const inputs=[...document.querySelectorAll('#settings-dialog input,#settings-dialog select')];
const sceneCopy={journey:['Дороги Запретных Земель','Лесные тропы, дальние перевалы и ещё не открытые места.'],settlement:['Огни поселения','За стенами ждут жители, ремесленные мастерские и новые истории.'],ruins:['Следы забытых времён','Старые стены хранят то, о чём давно перестали говорить.'],battle:['Перед схваткой','Отряд собирается у костра. Скоро каждый сделает свой ход.'],magic:['На границе незримого','Древние знаки проступают в тишине между мирами.'],characters:['Привал у дороги','Каждое приключение начинается с тех, кто идёт рядом.']};
let sceneKey='',sceneTimer=null,sceneTimeout=null,sceneFailed=false;
function desktopSceneTheme(value){if(Object.hasOwn(sceneCopy,value.loadingTheme))return value.loadingTheme;const url=String(value.gameUrl||'');return /battle|combat/.test(url)?'battle':/tools|account/.test(url)?'characters':'journey';}
function sceneFailure(message){clearTimeout(sceneTimer);clearTimeout(sceneTimeout);sceneFailed=true;$('workspace-fallback').hidden=false;$('workspace-fallback').dataset.failed='true';$('workspace-fallback').setAttribute('aria-busy','false');$('desktop-loading-title').textContent='Не удалось закончить загрузку';$('desktop-loading-detail').textContent=message||'Сервер отвечает дольше обычного. Проверьте соединение или повторите загрузку.';$('desktop-loading-status').textContent='Загрузка не завершена';$('desktop-loading-actions').hidden=false;}
function renderLoadingScene(){
 if(state.view!=='game'||!state.loading&&!state.viewError){clearTimeout(sceneTimer);clearTimeout(sceneTimeout);sceneKey='';sceneFailed=false;$('workspace-fallback').hidden=true;return;}
 const theme=desktopSceneTheme(state),key=theme+'|'+String(state.gameUrl||'');
 if(key!==sceneKey){clearTimeout(sceneTimer);clearTimeout(sceneTimeout);sceneKey=key;sceneFailed=false;$('workspace-fallback').hidden=true;$('workspace-fallback').dataset.theme=theme;$('workspace-fallback').dataset.failed='false';$('workspace-fallback').setAttribute('aria-busy','true');$('desktop-loading-art').src='loading/'+theme+'.svg';$('desktop-loading-place').textContent=sceneCopy[theme][0];$('desktop-loading-title').textContent='Открываем игровой стол';$('desktop-loading-detail').textContent=sceneCopy[theme][1];$('desktop-loading-status').textContent='Загружаем…';$('desktop-loading-actions').hidden=true;sceneTimer=setTimeout(()=>{if(state.view==='game'&&state.loading)$('workspace-fallback').hidden=false;},150);sceneTimeout=setTimeout(()=>{if(state.view==='game'&&state.loading)sceneFailure();},20000);}
 if(state.viewError)sceneFailure(String(state.viewError));
}
function setError(message){$('settings-feedback').hidden=!message;$('settings-feedback').dataset.error='true';$('settings-feedback').textContent=message||'';}
function navigationError(message){$('page-address').textContent=message;$('page-address').title=message;$('page-address').dataset.error='true';$('connection-dot').dataset.error='true';$('connection-dot').title='Действие не выполнено';}
async function invoke(name,...args){try{const value=await shellApi[name](...args);if(value&&typeof value==='object'&&value.preferences)setState(value);return value;}catch(error){const message=String(error?.message||error||'Не удалось выполнить действие.').replace(/^Error invoking remote method '[^']+': Error: /,'');if($('settings-dialog').open)setError(message);else navigationError(message);return null;}}
function sizeOptions(){
  const p=state.preferences,screen=state.display||{},limitW=Number(screen.width)||3840,limitH=Number(screen.height)||2160;
  const values=[[1024,720],[1280,720],[1280,800],[1366,768],[1440,900],[1440,1000],[1600,900],[1920,1080],[2560,1440],[3840,2160]].filter(([w,h])=>w<=limitW&&h<=limitH);
  values.push([p.width,p.height]);
  const unique=[...new Map(values.map(([w,h])=>[`${w}x${h}`,[w,h]])).values()].filter(([w,h])=>Number.isInteger(w)&&Number.isInteger(h)).sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
  $('resolution').replaceChildren(...unique.map(([w,h])=>{const option=document.createElement('option');option.value=`${w}x${h}`;option.textContent=`${w} × ${h}`;return option;}));
}
function fillFields(){
  const p=state.preferences;sizeOptions();
  for(const input of document.querySelectorAll('[name=screen-mode]'))input.checked=input.value===p.mode;
  $('resolution').value=`${p.width}x${p.height}`;$('interface-zoom').value=String(p.zoom);$('zoom-value').textContent=p.zoom+'%';$('remember-window').checked=p.rememberWindow!==false;$('confirm-exit').checked=p.confirmExit!==false;
  dirty=false;fieldStatus();
}
function formSettings(){const [width,height]=$('resolution').value.split('x').map(Number);return {mode:document.querySelector('[name=screen-mode]:checked')?.value||'windowed',width,height,zoom:Number($('interface-zoom').value),rememberWindow:$('remember-window').checked,confirmExit:$('confirm-exit').checked};}
function fieldStatus(){
  const mode=document.querySelector('[name=screen-mode]:checked')?.value||'windowed',pending=!!state.displayPending;
  for(const input of inputs)input.disabled=busy||pending;
  $('resolution').disabled=busy||pending||mode!=='windowed';
  $('resolution-hint').textContent=mode==='windowed'?'Слишком большой размер будет ограничен рабочей областью экрана.':mode==='fullscreen'?'Полноэкранный режим использует размер текущего монитора.':'Окно без рамки подстраивается под текущий экран.';
  $('zoom-value').textContent=$('interface-zoom').value+'%';
  $('apply-settings').disabled=busy||pending||!dirty;
  $('confirm-display').disabled=busy;$('revert-display').disabled=busy;
  $('save-diagnostics').disabled=diagnosticsBusy||busy||pending;
  $('settings-status').textContent=pending?'Подтвердите новый режим или верните прежний.':busy?'Применяем изменения…':dirty?'Есть неприменённые изменения':'Настройки сохранены на этом компьютере';
}
function showTab(id,{focus=false}={}){for(const tab of document.querySelectorAll('[data-tab]')){const selected=tab.dataset.tab===id;tab.setAttribute('aria-selected',String(selected));tab.tabIndex=selected?0:-1;$(tab.getAttribute('aria-controls')).hidden=!selected;if(selected&&focus)tab.focus();}}
function setState(next){
  const oldPending=!!state.displayPending;state={...state,...next,preferences:{...state.preferences,...next.preferences}};
  $('app-version').textContent=state.version?'v'+state.version:'';
  const game=state.view==='game';$('page-title').textContent=game?(state.gameTitle||'Игровой стол'):'Подключения и приглашения';
  let address='Своя игра или сервер Мастера';if(game&&state.gameUrl)try{const url=new URL(state.gameUrl);address=['127.0.0.1','localhost','[::1]'].includes(url.hostname)?'Игра на этом компьютере · '+url.host:url.host;}catch{address='Игровой сервер';}
  $('page-address').textContent=address;$('page-address').title=address;$('go-back').disabled=!game||!state.canGoBack;$('go-forward').disabled=!game||!state.canGoForward;$('reload').disabled=!game;
  $('resume-game').hidden=game||!state.gameUrl;$('page-address').dataset.error='false';$('connection-dot').dataset.error='false';
  $('game-settings').disabled=!state.gameUrl||!!state.displayPending;$('game-settings-hint').textContent=state.gameUrl?'Открыть общие настройки игрового стола в этом же окне.':'Сначала откройте игру.';
  $('go-home').setAttribute('aria-current',game?'false':'page');$('connection-dot').dataset.connected=String(game);$('connection-dot').title=game?'Открыт игровой сервер':'Окно подключения';$('loading-line').hidden=!state.loading;
  if(state.error)navigationError(String(state.error));
  const expanded=state.maximized||state.fullscreen||state.preferences.mode!=='windowed';$('maximize-icon').setAttribute('href',expanded?'#i-restore':'#i-maximize');$('maximize').title=expanded?'Вернуть в окно':'Развернуть';$('maximize').setAttribute('aria-label',expanded?'Вернуть в окно':'Развернуть окно');
  if(state.settingsOpen&&!opened){opened=true;restoreFocus=document.activeElement;fillFields();setError('');$('settings-dialog').showModal();showTab('display',{focus:true});}
  if(!state.settingsOpen&&opened){opened=false;$('settings-dialog').close();restoreFocus?.focus();dirty=false;setError('');}
  if(opened&&(!dirty||oldPending&&!state.displayPending))fillFields();
  const pending=state.displayPending;$('display-confirm').hidden=!pending;$('settings-dialog').dataset.confirming=String(!!pending);
  if(pending){const seconds=Number(pending.seconds)||15,signature=JSON.stringify(pending);if(signature!==pendingSignature){pendingSignature=signature;pendingUntil=Date.now()+seconds*1000;}if(!oldPending)$('confirm-display').focus();updateCountdown();}else{pendingSignature='';pendingUntil=0;}
  fieldStatus();
  renderLoadingScene();renderUpdates();
}
function updateCountdown(){if(state.displayPending)$('confirm-seconds').textContent=String(Math.max(0,Math.ceil((pendingUntil-Date.now())/1000)));}
async function closeSettings(){if(busy)return;if(state.displayPending){await invoke('revertDisplay');return;}await invoke('closeSettings');}
for(const action of ['home','back','forward'])$('go-'+action).onclick=()=>invoke('navigate',action);
$('reload').onclick=()=>invoke('navigate','reload');$('open-settings').onclick=()=>invoke('openSettings');
$('resume-game').onclick=()=>invoke('navigate','game');
$('game-settings').onclick=()=>invoke('navigate','game-settings');
$('save-diagnostics').onclick=async()=>{if(diagnosticsBusy||busy||state.displayPending)return;diagnosticsBusy=true;const status=$('diagnostics-status');status.hidden=false;status.dataset.error='false';status.textContent='Выберите место для отчёта…';fieldStatus();try{const result=await shellApi.saveDiagnostics();status.textContent=result?.saved?'Диагностика сохранена. Передайте JSON-файл разработчику удобным для вас способом.':'Сохранение отменено. Файл не создан.';}catch{status.dataset.error='true';status.textContent='Не удалось сохранить отчёт. Выберите доступную папку и повторите.';}finally{diagnosticsBusy=false;fieldStatus();}};
$('desktop-loading-retry').onclick=()=>{sceneKey='';invoke('navigate','reload');};$('desktop-loading-home').onclick=()=>invoke('navigate','home');
for(const [id,command] of [['minimize','minimize'],['maximize','maximize'],['close-window','close']])$(id).onclick=()=>invoke('windowControl',command);
$('titlebar').ondblclick=event=>{if(!event.target.closest('button'))invoke('windowControl','maximize');};
$('close-settings').onclick=closeSettings;$('cancel-settings').onclick=closeSettings;
$('settings-dialog').addEventListener('cancel',event=>{event.preventDefault();closeSettings();});
for(const input of inputs)input.addEventListener('input',()=>{dirty=true;setError('');fieldStatus();});
for(const tab of document.querySelectorAll('[data-tab]')){tab.onclick=()=>showTab(tab.dataset.tab);tab.onkeydown=event=>{const tabs=[...document.querySelectorAll('[data-tab]')],index=tabs.indexOf(tab);let target;if(event.key==='ArrowDown'||event.key==='ArrowRight')target=tabs[(index+1)%tabs.length];if(event.key==='ArrowUp'||event.key==='ArrowLeft')target=tabs[(index+tabs.length-1)%tabs.length];if(event.key==='Home')target=tabs[0];if(event.key==='End')target=tabs.at(-1);if(target){event.preventDefault();showTab(target.dataset.tab,{focus:true});}};}
$('apply-settings').onclick=async()=>{if(busy||state.displayPending)return;busy=true;setError('');fieldStatus();const next=await invoke('applySettings',formSettings());if(next){dirty=false;fillFields();}busy=false;fieldStatus();};
for(const [id,method] of [['confirm-display','confirmDisplay'],['revert-display','revertDisplay']])$(id).onclick=async()=>{if(busy)return;busy=true;fieldStatus();await invoke(method);dirty=false;fillFields();busy=false;fieldStatus();};
document.addEventListener('keydown',event=>{if(event.ctrlKey&&event.key===','){event.preventDefault();if(!state.settingsOpen)invoke('openSettings');}});
setInterval(updateCountdown,250);
if(shellApi){shellApi.onState(setState);invoke('getState');}else{sceneFailure('Не удалось загрузить управление приложением. Закройте его и запустите снова.');document.querySelectorAll('button').forEach(button=>button.disabled=true);}

let updateBusy=false;
function renderUpdates(){const u=state.updates||{},working=updateBusy||state.maintenance||['checking','downloading'].includes(u.status);$('update-status').textContent=u.message||'Проверка обновлений запускается вручную.';$('update-progress').hidden=u.status!=='downloading';$('update-progress').value=u.progress||0;$('check-updates').disabled=working;$('download-update').hidden=!u.version||!['available','error'].includes(u.status);$('download-update').disabled=working;$('install-update').hidden=u.status!=='ready';$('install-update').disabled=working;for(const id of ['restore-backup','update-backups'])$(id).disabled=working;$('update-notes-box').hidden=!u.notes;$('update-notes').textContent=u.notes||'';}
for(const [id,method] of [['check-updates','checkUpdates'],['download-update','downloadUpdate'],['install-update','installUpdate'],['update-backups','openUpdateBackups'],['restore-backup','restoreBackup']])$(id).onclick=async()=>{if(updateBusy)return;updateBusy=true;setError('');renderUpdates();const result=await invoke(method);if(method==='restoreBackup')$('recovery-status').textContent=result?.restored?'Данные восстановлены. Предыдущее состояние сохранено в папке копий.':result?.canceled?'Восстановление отменено.':'';updateBusy=false;renderUpdates();};
