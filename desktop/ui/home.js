'use strict';
const api=window.desktop;
const $=id=>document.getElementById(id);
let state={version:'',localUrl:'',shareUrl:'',dataPath:'',server:'stopped',sharing:'stopped',message:'',error:'',recent:[]};
let pending='',localMessage='',localError='';
function setState(next){if(next&&typeof next==='object'&&typeof next.server==='string')state={...state,...next};render();}
function status(el,value,text){el.dataset.kind=value;el.textContent=text;}
function render(){
  $('version').textContent=state.version?'v'+state.version:'';
  $('data-path').textContent=state.dataPath||'Путь к сохранениям пока недоступен';
  const running=state.server==='running',starting=state.server==='starting';
  status($('server-status'),state.server,({stopped:'Готово к запуску',starting:'Запускаем игру…',running:'Игра работает',error:'Не удалось запустить'})[state.server]||'Готово к запуску');
  $('start-local-label').textContent=starting?'Запускаем игру…':running?'Вернуться в мою игру':'Открыть мою игру';
  $('hosting-panel').hidden=!running&&!starting&&state.sharing==='stopped';
  $('local-address').hidden=!state.localUrl;$('local-url').value=state.localUrl||'';
  $('share-address').hidden=!state.shareUrl;$('share-url').value=state.shareUrl||'';
  status($('sharing-status'),state.sharing,({stopped:'Доступ с этого компьютера',starting:'Создаём общую ссылку…',running:'Открыто для участников',error:'Общий доступ не включён'})[state.sharing]||'');
  $('start-sharing').hidden=state.sharing==='running';$('stop-sharing').hidden=state.sharing!=='running';
  $('start-sharing').textContent=state.sharing==='starting'?'Создаём общую ссылку…':'Пригласить через интернет';
  $('sharing-progress').textContent=state.sharing==='starting'?'Устанавливаем защищённое соединение. Это может занять около минуты.':'';
  const message=localMessage||state.message||'',error=localError||state.error||'';
  $('feedback').hidden=!message;$('feedback').textContent=message;
  $('error').hidden=!error;$('error').textContent=error;
  document.querySelectorAll('button').forEach(button=>button.disabled=!!pending);
  $('start-local').disabled=!!pending||starting;
  $('start-sharing').disabled=!!pending||!running||state.sharing==='starting';
  $('copy-local').disabled=!!pending||!state.localUrl;$('open-browser').disabled=!!pending||!state.localUrl;
  $('copy-share').disabled=!!pending||!state.shareUrl;
  $('open-data').disabled=!!pending||!state.dataPath;
  $('backup').disabled=!!pending||starting;
  const recent=Array.isArray(state.recent)?state.recent.filter(url=>typeof url==='string').slice(0,5):[];
  $('recent-wrap').hidden=!recent.length;
  const list=$('recent-list'),signature=JSON.stringify(recent);
  if(list.dataset.urls!==signature){list.dataset.urls=signature;list.replaceChildren();for(const url of recent){const button=document.createElement('button');button.type='button';button.textContent=url;button.title=url;button.disabled=!!pending;button.onclick=()=>{$('server-url').value=url;connect();};list.append(button);}}
  document.body.setAttribute('aria-busy',String(!!pending));
}
async function run(name,operation,success=''){
  if(pending)return;
  pending=name;localError='';localMessage='';render();
  try{const result=await operation();setState(result);if(success)localMessage=success;}
  catch(error){localError=String(error?.message||error||'Не удалось выполнить действие.');}
  finally{pending='';render();}
}
function validServer(value){
  let url;try{url=new URL(value);}catch{throw Error('Вставьте полный адрес игры, например https://example.com.');}
  const loopback=url.hostname==='127.0.0.1'||url.hostname==='localhost'||url.hostname==='[::1]';
  if(url.protocol!=='https:'&&!(url.protocol==='http:'&&loopback))throw Error('Для игры через интернет нужна HTTPS-ссылка. Локальный адрес этого компьютера может начинаться с http://127.0.0.1.');
  if(url.username||url.password)throw Error('Вставьте ссылку без логина и пароля. Вход выполняется внутри игры.');
  return url.href;
}
async function connect(){
  if(!$('join-form').reportValidity())return;
  await run('connect',()=>api.connect(validServer($('server-url').value.trim())));
}
$('join-form').addEventListener('submit',event=>{event.preventDefault();connect();});
$('start-local').onclick=()=>run('local',async()=>{if(state.server!=='running')setState(await api.startLocal());return api.openLocal();});
$('start-sharing').onclick=()=>run('share',()=>api.startSharing());
$('stop-sharing').onclick=()=>run('stop-share',()=>api.stopSharing(),'Общий доступ выключен. Локальная игра продолжает работать.');
$('copy-local').onclick=()=>run('copy-local',()=>api.copy(state.localUrl),'Локальный адрес скопирован. Он работает только на этом компьютере.');
$('copy-share').onclick=()=>run('copy-share',()=>api.copy(state.shareUrl),'Общая ссылка скопирована. Отправьте её участникам вместе с приглашением в кампанию.');
$('open-browser').onclick=()=>run('browser',()=>api.openBrowser());
$('open-data').onclick=()=>run('data',()=>api.openData());
$('backup').onclick=()=>run('backup',()=>api.backup());
if(!api){localError='Не удалось загрузить управление приложением. Закройте окно и запустите игру снова.';render();document.querySelectorAll('button').forEach(button=>button.disabled=true);}
else{api.onState(next=>{localMessage='';setState(next);});run('load',()=>api.getState());}
