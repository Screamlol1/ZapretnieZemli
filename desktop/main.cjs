const {app,BrowserWindow,WebContentsView,ipcMain,Menu,dialog,shell,clipboard,net,powerSaveBlocker,screen}=require('electron');
const path=require('node:path'),fs=require('node:fs'),{pathToFileURL}=require('node:url');
const {GameHost}=require('./host.cjs'),{connectionURL,sameOrigin,safeExternal}=require('./policy.cjs');
const {DEFAULTS,preferences,fitBounds,screenChanged}=require('./preferences.cjs');
const {buildReport,errorCode,runtimeInfo,localHealth,reportFilename}=require('./diagnostics.cjs');
const os=require('node:os'),{spawn}=require('node:child_process');
const {Updates}=require('./updates.cjs'),{runRecovery}=require('./recovery.cjs');
let updates,maintenance=false;
const override=process.argv.find(a=>a.startsWith('--zz-data-dir='));
const base=override?path.resolve(override.slice('--zz-data-dir='.length)):path.join(process.env.LOCALAPPDATA||app.getPath('appData'),'ZapretnieZemli');
fs.mkdirSync(base,{recursive:true});app.setPath('userData',path.join(base,'profile'));app.setAppUserModelId('ru.zapretnie-zemli.table');
const settingsPath=path.join(base,'desktop.json'),homeFile=path.join(__dirname,'ui/index.html'),shellFile=path.join(__dirname,'ui/shell.html');
let settings={port:8791,recent:[],preferences:{...DEFAULTS},bounds:null};
try{const v=JSON.parse(fs.readFileSync(settingsPath,'utf8'));settings={port:Number.isInteger(v.port)&&v.port>0&&v.port<65536?v.port:8791,recent:(Array.isArray(v.recent)?v.recent:[]).slice(0,8).flatMap(url=>{try{return [connectionURL(url)];}catch{return [];}}),preferences:preferences(v.preferences||{}),bounds:v.bounds&&typeof v.bounds==='object'?v.bounds:null};}catch{}
let win,homeView,gameView,host,view='home',settingsOpen=false,quitting=false,exitPending=false,awake=null,gameOrigin='',targetOrigin='',displayPending=null,previewTimer=null,resizeTimer=null,applying=false,gameLoading=false,viewError='',loadingTheme='characters',gameVisible=null;
const BAR_HEIGHT=88;
let diagnosticsPending=false,lastDiagnosticError='';const recentDiagnosticErrors=[];
function saveSettings(){const saved=displayPending?{...settings,preferences:displayPending.previous,bounds:displayPending.bounds}:settings;fs.writeFileSync(settingsPath+'.tmp',JSON.stringify(saved,null,2));fs.renameSync(settingsPath+'.tmp',settingsPath);}
function live(contents){return contents&&!contents.isDestroyed();}
function display(){return win?screen.getDisplayMatching(win.getBounds()):screen.getPrimaryDisplay();}
function state(){const wc=gameView?.webContents,d=display();return {...host.state,updates:updates?.state,maintenance,version:app.getVersion(),dataPath:host.data,recent:settings.recent,view,settingsOpen,gameUrl:live(wc)?wc.getURL():'',gameTitle:live(wc)?wc.getTitle():'',canGoBack:!!(live(wc)&&wc.navigationHistory.canGoBack()),canGoForward:!!(live(wc)&&wc.navigationHistory.canGoForward()),loading:view==='game'&&gameLoading,viewError:view==='game'?viewError:'',loadingTheme,preferences:{...settings.preferences},display:{width:d.workArea.width,height:d.workArea.height,screenWidth:d.bounds.width,screenHeight:d.bounds.height},displayPending:displayPending?{seconds:Math.max(0,Math.ceil((displayPending.deadline-Date.now())/1000))}:null,maximized:win?.isMaximized()||false,fullscreen:win?.isFullScreen()||false};}
function publish(){if(!host||!win||win.isDestroyed())return;const s=state(),code=errorCode(s.viewError||s.error),source=s.viewError?'view':'host',signature=code?source+':'+code:'';if(signature&&signature!==lastDiagnosticError){recentDiagnosticErrors.push({source,code,at:new Date().toISOString()});if(recentDiagnosticErrors.length>8)recentDiagnosticErrors.shift();}lastDiagnosticError=signature;for(const wc of [win.webContents,homeView?.webContents])if(live(wc))wc.send('desktop:state',s);if(host.state.sharing==='running'&&awake===null)awake=powerSaveBlocker.start('prevent-app-suspension');if(host.state.sharing!=='running'&&awake!==null){powerSaveBlocker.stop(awake);awake=null;}}
function visibility(force=false){const active=!!(!settingsOpen&&view==='game'&&!gameLoading&&!viewError&&!win?.isMinimized());if(live(gameView?.webContents)&&(force||gameVisible!==active)){gameVisible=active;gameView.webContents.executeJavaScript(`window.dispatchEvent(new CustomEvent('zz-desktop-visibility',{detail:{active:${active}}}))`).catch(()=>{});}}
function layout(){if(!win||win.isDestroyed())return;const [width,height]=win.getContentSize();for(const v of [homeView,gameView])if(v){v.setBounds({x:0,y:BAR_HEIGHT,width,height:Math.max(1,height-BAR_HEIGHT)});v.setVisible(!settingsOpen&&(v===homeView?view==='home':view==='game'&&!gameLoading&&!viewError));}visibility();}
function activate(next){view=next;layout();publish();const wc=next==='game'?gameView?.webContents:homeView?.webContents;if(!settingsOpen&&live(wc))wc.focus();}
async function external(url){if(!safeExternal(url))return;const choice=await dialog.showMessageBox(win,{type:'question',buttons:['Отмена','Открыть в браузере'],defaultId:0,cancelId:0,message:'Открыть внешнюю ссылку?',detail:url});if(choice.response===1)await shell.openExternal(url);}
const configured=new WeakSet();
function configureSession(s){if(configured.has(s))return;configured.add(s);s.setPermissionRequestHandler((_w,_permission,callback)=>callback(false));s.setPermissionCheckHandler(()=>false);s.on('will-download',(_event,item)=>item.setSaveDialogOptions({title:'Сохранить файл из игры',defaultPath:path.join(app.getPath('downloads'),path.basename(item.getFilename()))}));}
function keyboard(wc){wc.on('before-input-event',(event,input)=>{if(input.type!=='keyDown')return;const key=input.key.toLowerCase(),ctrl=input.control||input.meta;let action;
 if(key==='f11'||input.alt&&key==='enter')action=()=>applyPreferences({mode:settings.preferences.mode==='fullscreen'?'windowed':'fullscreen'});
 else if(ctrl&&(key===','||key==='б'))action=()=>openSettings();
 else if(input.alt&&key==='arrowleft')action=()=>navigate('back');
 else if(input.alt&&key==='arrowright')action=()=>navigate('forward');
 else if(ctrl&&(key==='r'||key==='к')||key==='f5')action=()=>navigate('reload');
 else if(ctrl&&['+','=','-','0'].includes(key))action=()=>applyPreferences({zoom:key==='0'?100:Math.max(75,Math.min(150,settings.preferences.zoom+(key==='-'?-5:5)))});
 if(action){event.preventDefault();Promise.resolve().then(action).catch(e=>host.update({error:e.message}));}
 });}
function createGameView(){
 const v=new WebContentsView({webPreferences:{nodeIntegration:false,contextIsolation:true,sandbox:true,webSecurity:true,allowRunningInsecureContent:false,partition:'persist:game'}});v.setBackgroundColor('#111916');win.contentView.addChildView(v);const wc=v.webContents;configureSession(wc.session);keyboard(wc);
 wc.setWindowOpenHandler(({url})=>{if(sameOrigin(url,gameOrigin))wc.loadURL(url).catch(()=>{});else if(url.startsWith('blob:'+gameOrigin+'/'))wc.downloadURL(url);else if(safeExternal(url))external(url);return {action:'deny'};});
 wc.on('will-navigate',(event,url)=>{if(!sameOrigin(url,gameOrigin)&&!sameOrigin(url,targetOrigin)){event.preventDefault();external(url);}});
 wc.on('will-redirect',(event,url)=>{if(!sameOrigin(url,gameOrigin)&&!sameOrigin(url,targetOrigin)){event.preventDefault();host.update({error:'Сервер перенаправляет на другой адрес. Введите его HTTPS-ссылку на экране подключения.'});}});
 wc.on('will-attach-webview',event=>event.preventDefault());
 wc.on('will-prevent-unload',event=>{const choice=dialog.showMessageBoxSync(win,{type:'question',buttons:['Продолжить редактирование','Уйти без сохранения'],defaultId:0,cancelId:0,message:'Есть несохранённые изменения',detail:'Сохраните лист перед переходом, если хотите оставить внесённые изменения.'});if(choice===1)event.preventDefault();else {targetOrigin='';gameLoading=false;layout();publish();}});
 wc.on('did-navigate',(_e,url)=>{if(sameOrigin(url,targetOrigin))gameOrigin=targetOrigin;targetOrigin='';publish();});
 wc.on('did-start-navigation',(_event,url,inPlace,main)=>{if(main&&!inPlace){gameLoading=true;viewError='';loadingTheme=url.includes('battle')?'battle':url.includes('/tools/')?'characters':url.includes('account')?'characters':'journey';layout();publish();}});
 wc.on('did-stop-loading',()=>{gameLoading=false;layout();publish();visibility(true);});
 for(const name of ['did-navigate-in-page','page-title-updated'])wc.on(name,publish);
 wc.on('did-fail-load',(_e,code,description,_url,main)=>{if(main&&code!==-3){gameLoading=false;viewError='Не удалось загрузить игру: '+description;layout();host.update({error:viewError+'. Нажмите «Обновить» или вернитесь к подключению.'});}});
 wc.on('render-process-gone',()=>{viewError='Окно игры остановилось. Нажмите «Обновить».';gameLoading=false;layout();host.update({error:viewError});});
 wc.setZoomFactor(settings.preferences.zoom/100);return v;
}
async function openGame(url){
 if(!gameView)gameView=createGameView();
 if(gameOrigin&&sameOrigin(url,gameOrigin)&&!viewError&&gameView.webContents.getURL()&&!gameView.webContents.getURL().startsWith('chrome-error:')){activate('game');return state();}
 targetOrigin=new URL(url).origin;gameLoading=true;viewError='';activate('game');
 try{await gameView.webContents.loadURL(url);}catch(e){targetOrigin='';gameLoading=false;layout();publish();if(e.code!=='ERR_ABORTED')throw Error('Не удалось открыть игру. Проверьте сервер и попробуйте обновить страницу.');}
 publish();return state();
}
function trusted(event,shellOnly=false){const candidates=shellOnly?[[win?.webContents,shellFile]]:[[win?.webContents,shellFile],[homeView?.webContents,homeFile]];if(!candidates.some(([wc,file])=>live(wc)&&event.sender===wc&&event.senderFrame===wc.mainFrame&&event.senderFrame.url===pathToFileURL(file).href))throw Error('Недоступное действие приложения.');}
function handle(name,fn,shellOnly=false){ipcMain.handle('desktop:'+name,async(event,...args)=>{trusted(event,shellOnly);if(maintenance&&name!=='state')throw Error('Дождитесь завершения обслуживания приложения.');try{return await fn(...args);}catch(e){host.update({error:e.message});throw Error(e.message);}});}
async function connect(raw){const url=connectionURL(raw);try{const r=await net.fetch(url+'api/health',{redirect:'error',signal:AbortSignal.timeout(15000)});if(!r.ok||!(await r.json()).ok)throw Error('health');}catch{throw Error('По этой ссылке игровой сервер не отвечает. Проверьте адрес и попросите Мастера оставить игру запущенной.');}await openGame(url);if(sameOrigin(gameView.webContents.getURL(),url)){settings.recent=[url,...settings.recent.filter(u=>u!==url)].slice(0,8);saveSettings();}publish();return state();}
async function local(){await host.start();settings.port=host.port;saveSettings();return openGame(host.state.localUrl);}
function openSettings(){settingsOpen=true;layout();publish();win.webContents.focus();return state();}
function closeSettings(){if(displayPending)revertDisplay();settingsOpen=false;activate(view);return state();}
async function saveDiagnostics(){
 if(diagnosticsPending)throw Error('Сохранение диагностики уже открыто.');if(displayPending)throw Error('Сначала подтвердите параметры экрана или верните прежние.');diagnosticsPending=true;
 try{
  const selected=await dialog.showSaveDialog(win,{title:'Сохранить диагностику',defaultPath:path.join(app.getPath('documents'),reportFilename(app.getVersion())),filters:[{name:'Диагностический отчёт JSON',extensions:['json']}],properties:['showOverwriteConfirmation','createDirectory']});
  if(selected.canceled||!selected.filePath)return {canceled:true};
  const snapshot=state(),resources=app.isPackaged?process.resourcesPath:__dirname;
  const report=buildReport({appVersion:app.getVersion(),packaged:app.isPackaged,versions:process.versions,os:{platform:process.platform,release:os.release(),arch:process.arch},runtime:runtimeInfo(resources,host.runtime),host:host.state,view:snapshot,preferences:settings.preferences,display:snapshot.display,health:await localHealth(host.state,(...args)=>net.fetch(...args)),recentErrors:recentDiagnosticErrors});
  await fs.promises.writeFile(selected.filePath,JSON.stringify(report,null,2)+'\n',{encoding:'utf8',mode:0o600});return {saved:true};
 }catch{throw Error('Не удалось сохранить диагностику. Выберите доступную папку и повторите.');}finally{diagnosticsPending=false;}
}
function applyWindow(p,bounds){
 applying=true;clearTimeout(resizeTimer);const d=display();win.setFullScreen(false);if(win.isMaximized())win.unmaximize();win.setResizable(p.mode!=='borderless');
 if(p.mode==='fullscreen')win.setFullScreen(true);
 else if(p.mode==='borderless')win.setBounds(d.bounds);
 else win.setBounds(fitBounds({...bounds,width:p.width,height:p.height},d.workArea));
 for(const v of [homeView,gameView])if(live(v?.webContents))v.webContents.setZoomFactor(p.zoom/100);
 layout();publish();setTimeout(()=>{applying=false;layout();publish();},300);
}
function clearPreview(){clearInterval(previewTimer);previewTimer=null;displayPending=null;}
function applyPreferences(patch){
 if(displayPending)throw Error('Сначала подтвердите текущий режим экрана или верните прежний.');
 const next=preferences({...settings.preferences,...patch},true),previous={...settings.preferences},bounds=win.getNormalBounds(),maximized=win.isMaximized();
 if(settings.preferences.mode==='windowed'&&!win.isMaximized()&&!win.isFullScreen())settings.bounds=win.getBounds();
 settings.preferences=next;
 if(screenChanged(previous,next)){
  displayPending={previous,bounds,maximized,deadline:Date.now()+15000};settingsOpen=true;
  applyWindow(next,settings.bounds);previewTimer=setInterval(()=>{if(displayPending&&Date.now()>=displayPending.deadline)revertDisplay();else publish();},250);win.webContents.focus();
 }else{for(const v of [homeView,gameView])if(live(v?.webContents))v.webContents.setZoomFactor(next.zoom/100);saveSettings();publish();}
 return state();
}
function confirmDisplay(){if(displayPending){clearPreview();if(settings.preferences.mode==='windowed'){settings.bounds=win.getBounds();settings.preferences.width=settings.bounds.width;settings.preferences.height=settings.bounds.height;}saveSettings();publish();}return state();}
function revertDisplay(){if(displayPending){const {previous,bounds,maximized}=displayPending;clearPreview();settings.preferences=previous;settings.bounds=bounds;applyWindow(previous.mode==='windowed'?{...previous,width:bounds.width,height:bounds.height}:previous,bounds);if(maximized&&previous.mode==='windowed')win.maximize();saveSettings();publish();}return state();}
async function navigate(action){if(!['home','back','forward','reload','game','game-settings'].includes(action))throw Error('Неизвестный переход.');if(settingsOpen)closeSettings();if(action==='game-settings'){if(!live(gameView?.webContents))throw Error('Сначала откройте игру.');activate('game');const available=await Promise.race([gameView.webContents.executeJavaScript('Boolean(window.ZZInterfaceSettings && (window.ZZInterfaceSettings.open(), true))'),new Promise(resolve=>setTimeout(()=>resolve(false),2000))]);if(!available)throw Error('Этот сервер ещё не поддерживает общие настройки. Обновите его версию.');return state();}if(action==='home'){activate('home');return state();}if(action==='game'){if(gameView)activate('game');return state();}const wc=view==='game'?gameView?.webContents:homeView?.webContents;if(live(wc)){if(action==='reload')wc.reload();else if(view==='game'&&action==='back'&&wc.navigationHistory.canGoBack())wc.navigationHistory.goBack();else if(view==='game'&&action==='forward'&&wc.navigationHistory.canGoForward())wc.navigationHistory.goForward();}return state();}
function windowControl(action){if(action==='minimize')win.minimize();else if(action==='maximize'){if(settings.preferences.mode==='windowed'){win.isMaximized()?win.unmaximize():win.maximize();}else applyPreferences({mode:'windowed'});}else if(action==='close')requestQuit();else throw Error('Неизвестное действие окна.');publish();return state();}
async function requireSavedGame(){
 if(displayPending)throw Error('Сначала подтвердите параметры экрана.');
 if(live(gameView?.webContents)){
  let dirty=true;try{dirty=await Promise.race([gameView.webContents.executeJavaScript('Boolean(window.zzHasUnsavedChanges && window.zzHasUnsavedChanges())'),new Promise(resolve=>setTimeout(()=>resolve(true),2000))]);}catch{}
  if(dirty)throw Error('Сохраните или закройте открытый редактор перед обновлением или восстановлением.');
 }
}
async function maintenanceOperation(work){
 if(maintenance)throw Error('Обслуживание приложения уже выполняется.');
 maintenance=true;publish();
 try{return await work();}finally{maintenance=false;publish();}
}
function installUpdate(){return maintenanceOperation(async()=>{
 if(!app.isPackaged)throw Error('Установка обновлений доступна в установленной Windows-версии.');
 await requireSavedGame();await updates.installer();
 const choice=await dialog.showMessageBox(win,{type:'question',buttons:['Позже','Создать копию и установить'],defaultId:0,cancelId:0,message:'Установить версию '+updates.entry.version+'?',detail:'Приложение закроется, свой сервер отключится от игроков. Перед установкой сохраним кампании, аккаунты и карты в резервную копию. После установки запустите игру снова.'});if(choice.response!==1)return {canceled:true};
 let stopped=false;
 try{
  const backup=await host.backup(path.join(base,'update-backups')),installer=await updates.installer();
  fs.writeFileSync(path.join(base,'last-update.json'),JSON.stringify({from:app.getVersion(),to:updates.entry.version,backup,at:new Date().toISOString()},null,2));
  await host.stop();stopped=true;
  const child=spawn(installer,['/S'],{detached:true,stdio:'ignore',windowsHide:true});await new Promise((resolve,reject)=>{child.once('spawn',resolve);child.once('error',reject);});child.unref();
  quitting=true;clearTimeout(resizeTimer);for(const v of [homeView,gameView])if(live(v?.webContents))v.webContents.close();app.quit();return {installing:true};
 }catch(e){if(stopped)await host.start().catch(()=>{});throw e;}
});}
function restoreGame(){return maintenanceOperation(async()=>{
 await requireSavedGame();const selected=await dialog.showOpenDialog(win,{title:'Выберите завершённую копию с COMPLETE.json',properties:['openDirectory'],defaultPath:path.join(base,'update-backups')});if(selected.canceled)return {canceled:true};
 const folder=selected.filePaths[0];await runRecovery(host,folder,true);
 const choice=await dialog.showMessageBox(win,{type:'warning',buttons:['Отмена','Сохранить текущее и восстановить'],defaultId:0,cancelId:0,message:'Восстановить все локальные аккаунты и кампании?',detail:'Будет восстановлено состояние из выбранной копии. Сначала сохраним текущее состояние отдельно. Свой сервер временно отключится, ссылки приглашений придётся создать заново.'});if(choice.response!==1)return {canceled:true};
 const previousUrl=host.state.localUrl;let stopped=false;
 try{
  const rescue=await host.backup(path.join(base,'update-backups'));await host.stop();stopped=true;
  await runRecovery(host,folder);await host.start();stopped=false;settings.port=host.port;saveSettings();
  if(live(gameView?.webContents)&&previousUrl&&sameOrigin(gameView.webContents.getURL(),previousUrl)){targetOrigin=new URL(host.state.localUrl).origin;await gameView.webContents.loadURL(host.state.localUrl);}
  host.update({error:'',message:'Данные восстановлены. Предыдущее состояние сохранено: '+rescue});return {restored:true};
 }catch(e){if(stopped)await host.start().catch(()=>{});throw e;}
});}
async function requestQuit(){
 if(quitting||exitPending||maintenance)return;exitPending=true;
 try{
  let dirty=false;try{if(live(gameView?.webContents))dirty=await Promise.race([gameView.webContents.executeJavaScript('Boolean(window.zzHasUnsavedChanges && window.zzHasUnsavedChanges())'),new Promise(resolve=>setTimeout(()=>resolve(true),2000))]);}catch{}
  if(dirty&&dialog.showMessageBoxSync(win,{type:'question',buttons:['Продолжить редактирование','Выйти без сохранения'],defaultId:0,cancelId:0,message:'Есть несохранённые изменения',detail:'Несохранённые правки листа будут потеряны.'})!==1)return;
  if(settings.preferences.confirmExit&&host?.state.server==='running'&&dialog.showMessageBoxSync(win,{type:'question',buttons:['Оставить игру работающей','Закрыть приложение'],defaultId:0,cancelId:0,message:'Завершить работу приложения?',detail:'Ваш сервер станет недоступен игрокам. Подтверждённые действия уже сохранены.'})!==1)return;
  quitting=true;if(displayPending)revertDisplay();clearTimeout(resizeTimer);await host?.stop();for(const v of [homeView,gameView])if(live(v?.webContents))v.webContents.close();app.quit();
 }finally{exitPending=false;}
}
if(!app.requestSingleInstanceLock({data:base}))app.quit();else{
 app.on('second-instance',()=>{if(win?.isMinimized())win.restore();win?.show();win?.focus();});
 app.on('before-quit',event=>{if(!quitting){event.preventDefault();requestQuit();}});
 app.whenReady().then(async()=>{
  const resources=app.isPackaged?process.resourcesPath:__dirname;
  host=new GameHost({resources,runtime:app.isPackaged?path.join(resources,'runtime'):path.join(__dirname,'.runtime'),data:path.join(base,'data'),port:settings.port,request:(url,options)=>net.fetch(url,options)});host.on('state',publish);
  updates=new Updates({directory:path.join(base,'updates'),current:app.getVersion(),request:(...args)=>net.fetch(...args)});updates.on('state',publish);
  const primary=screen.getPrimaryDisplay(),stored=settings.preferences.rememberWindow?settings.bounds:null,d=stored&&Number.isFinite(stored.x)&&Number.isFinite(stored.y)?screen.getDisplayNearestPoint({x:Math.round(stored.x),y:Math.round(stored.y)}):primary;
  const bounds=fitBounds(stored||{width:settings.preferences.width,height:settings.preferences.height},d.workArea);
  win=new BrowserWindow({...bounds,minWidth:Math.min(760,d.workArea.width),minHeight:Math.min(600,d.workArea.height),frame:false,backgroundColor:'#111916',title:'Запретные Земли',show:false,icon:path.join(__dirname,'ui/app-icon.png'),webPreferences:{preload:path.join(__dirname,'preload.cjs'),nodeIntegration:false,contextIsolation:true,sandbox:true,webSecurity:true}});
  configureSession(win.webContents.session);keyboard(win.webContents);win.webContents.setWindowOpenHandler(()=>({action:'deny'}));win.webContents.on('will-navigate',event=>event.preventDefault());
  homeView=new WebContentsView({webPreferences:{preload:path.join(__dirname,'preload.cjs'),nodeIntegration:false,contextIsolation:true,sandbox:true,webSecurity:true}});homeView.setBackgroundColor('#111916');win.contentView.addChildView(homeView);homeView.webContents.setWindowOpenHandler(()=>({action:'deny'}));homeView.webContents.on('will-navigate',event=>event.preventDefault());keyboard(homeView.webContents);
  handle('state',()=>state());handle('start',async()=>{await host.start();settings.port=host.port;saveSettings();return state();});handle('open',local);handle('connect',connect);
  handle('browser',async()=>{await host.start();await shell.openExternal(host.state.localUrl);return state();});handle('share',async()=>{await host.share();settings.port=host.port;saveSettings();return state();});handle('unshare',()=>{host.stopSharing();return state();});
  handle('copy',text=>{if(typeof text!=='string'||![host.state.localUrl,host.state.shareUrl].includes(text)||!text)throw Error('Нет адреса для копирования.');clipboard.writeText(text);return state();});
  handle('folder',async()=>{fs.mkdirSync(host.data,{recursive:true});await shell.openPath(host.data);return state();});
  handle('backup',async()=>{await host.start();const selected=await dialog.showOpenDialog(win,{title:'Папка для резервной копии кампаний',properties:['openDirectory','createDirectory'],defaultPath:app.getPath('documents')});if(selected.canceled)return state();const folder=await host.backup(selected.filePaths[0]);host.update({message:'Резервная копия создана: '+folder,error:''});return state();});
  handle('navigate',navigate,true);handle('window',windowControl,true);handle('settings-open',openSettings,true);handle('settings-close',closeSettings,true);handle('settings-apply',applyPreferences,true);handle('display-confirm',confirmDisplay,true);handle('display-revert',revertDisplay,true);
  handle('diagnostics-save',saveDiagnostics,true);
  handle('updates-check',()=>updates.check(),true);handle('updates-download',()=>updates.download(),true);handle('updates-install',installUpdate,true);handle('recovery-restore',restoreGame,true);handle('recovery-folder',async()=>{const folder=path.join(base,'update-backups');await fs.promises.mkdir(folder,{recursive:true});await shell.openPath(folder);return {opened:true};},true);
  Menu.setApplicationMenu(null);
  win.on('resize',()=>{layout();publish();clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if(!applying&&!displayPending&&settings.preferences.rememberWindow&&settings.preferences.mode==='windowed'&&!win.isMaximized()&&!win.isFullScreen()){settings.bounds=win.getBounds();settings.preferences.width=settings.bounds.width;settings.preferences.height=settings.bounds.height;saveSettings();}},350);});
  win.on('move',()=>{if(!applying&&!displayPending&&settings.preferences.rememberWindow&&settings.preferences.mode==='windowed'&&!win.isMaximized()&&!win.isFullScreen()){settings.bounds=win.getBounds();saveSettings();}});
  for(const event of ['maximize','unmaximize','enter-full-screen','leave-full-screen','minimize','restore'])win.on(event,()=>{layout();publish();});
  screen.on('display-removed',()=>{if(displayPending)revertDisplay();applyWindow(settings.preferences,settings.bounds);});
  win.on('close',event=>{if(!quitting){event.preventDefault();requestQuit();}});
  await win.loadFile(shellFile);await homeView.webContents.loadFile(homeFile);applyWindow(settings.preferences,bounds);layout();win.show();publish();
 }).catch(e=>{dialog.showErrorBox('Запретные Земли',e.message);quitting=true;if(host)host.stop().finally(()=>app.quit());else app.quit();});
}
