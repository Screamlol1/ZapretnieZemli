const {app,BrowserWindow,ipcMain,Menu,dialog,shell,clipboard,net,powerSaveBlocker}=require('electron');
const path=require('node:path'),fs=require('node:fs'),{pathToFileURL}=require('node:url');
const {GameHost}=require('./host.cjs'),{connectionURL,sameOrigin,safeExternal}=require('./policy.cjs');
const override=process.argv.find(a=>a.startsWith('--zz-data-dir='));
const base=override?path.resolve(override.slice('--zz-data-dir='.length)):path.join(process.env.LOCALAPPDATA||app.getPath('appData'),'ZapretnieZemli');
fs.mkdirSync(base,{recursive:true});app.setPath('userData',path.join(base,'profile'));app.setAppUserModelId('ru.zapretnie-zemli.table');
let home,host,quitting=false,awake=null,settings={port:8791,recent:[]};
const settingsPath=path.join(base,'desktop.json'),homeFile=path.join(__dirname,'ui/index.html');
try{const value=JSON.parse(fs.readFileSync(settingsPath,'utf8'));settings={port:Number.isInteger(value.port)&&value.port>0&&value.port<65536?value.port:8791,recent:(value.recent||[]).slice(0,8).flatMap(url=>{try{return [connectionURL(url)];}catch{return [];}})};}catch{}
function saveSettings(){fs.writeFileSync(settingsPath+'.tmp',JSON.stringify(settings,null,2));fs.renameSync(settingsPath+'.tmp',settingsPath);}
function state(){return {...host.state,version:app.getVersion(),dataPath:host.data,recent:settings.recent};}
function publish(){if(home&&!home.isDestroyed())home.webContents.send('desktop:state',state());if(host.state.sharing==='running'&&awake===null)awake=powerSaveBlocker.start('prevent-app-suspension');if(host.state.sharing!=='running'&&awake!==null){powerSaveBlocker.stop(awake);awake=null;}}
async function external(url){if(!safeExternal(url))return;const choice=await dialog.showMessageBox({type:'question',buttons:['Отмена','Открыть в браузере'],defaultId:0,cancelId:0,message:'Открыть внешнюю ссылку?',detail:url});if(choice.response===1)await shell.openExternal(url);}
const configured=new WeakSet();
function configureSession(s){if(configured.has(s))return;configured.add(s);s.setPermissionRequestHandler((_w,_permission,callback)=>callback(false));s.setPermissionCheckHandler(()=>false);s.on('will-download',(_event,item)=>{item.setSaveDialogOptions({title:'Сохранить файл из игры',defaultPath:path.join(app.getPath('downloads'),path.basename(item.getFilename()))});});}
function gameWindow(url){
 const win=new BrowserWindow({width:1440,height:1000,minWidth:800,minHeight:600,backgroundColor:'#111916',title:'Запретные Земли',show:false,icon:path.join(__dirname,'ui/app-icon.png'),webPreferences:{nodeIntegration:false,contextIsolation:true,sandbox:true,webSecurity:true,allowRunningInsecureContent:false,partition:'persist:game'}});
 configureSession(win.webContents.session);
 win.webContents.setWindowOpenHandler(({url:target})=>{if(sameOrigin(target,url))gameWindow(target);else if(safeExternal(target))external(target);return {action:'deny'};});
 win.webContents.on('will-navigate',(e,target)=>{if(!sameOrigin(target,url)){e.preventDefault();external(target);}});
 win.webContents.on('will-redirect',(e,target)=>{if(!sameOrigin(target,url)){e.preventDefault();dialog.showErrorBox('Подключение остановлено','Сервер перенаправляет на другой адрес. Введите новую HTTPS-ссылку в окне подключения.');}});
 win.webContents.on('will-attach-webview',event=>event.preventDefault());
 win.webContents.on('did-fail-load',(_e,code,description,failed,isMain)=>{if(isMain&&code!==-3){dialog.showErrorBox('Не удалось открыть игру',description+'\n'+failed);home?.show();}});
 win.once('ready-to-show',()=>win.show());win.loadURL(url).catch(()=>{});return win;
}
function trusted(event){if(!home||event.sender!==home.webContents||event.senderFrame!==home.webContents.mainFrame||event.senderFrame.url!==pathToFileURL(homeFile).href)throw Error('Недоступное действие приложения.');}
function handle(name,fn){ipcMain.handle('desktop:'+name,async(event,...args)=>{trusted(event);try{return await fn(...args);}catch(e){host.update({error:e.message});throw Error(e.message);}});}
async function connect(raw){const url=connectionURL(raw);let r;try{r=await net.fetch(url+'api/health',{redirect:'error',signal:AbortSignal.timeout(10000)});if(!r.ok||!(await r.json()).ok)throw Error('health');}catch{throw Error('По этой ссылке игровой сервер не отвечает. Проверьте адрес и попросите Мастера оставить игру запущенной.');}settings.recent=[url,...settings.recent.filter(u=>u!==url)].slice(0,8);saveSettings();gameWindow(url);publish();return state();}
async function local(){await host.start();settings.port=host.port;saveSettings();gameWindow(host.state.localUrl);return state();}
async function quit(){if(quitting)return;quitting=true;if(host)await host.stop();app.quit();}
const locked=app.requestSingleInstanceLock({data:base});
if(!locked)app.quit();else{
 app.on('second-instance',()=>{home?.show();home?.focus();});
 app.on('before-quit',event=>{if(!quitting){event.preventDefault();quit();}});
 app.whenReady().then(()=>{
  const resources=app.isPackaged?process.resourcesPath:__dirname;
  host=new GameHost({resources,runtime:app.isPackaged?path.join(resources,'runtime'):path.join(__dirname,'.runtime'),data:path.join(base,'data'),port:settings.port,request:(url,options)=>net.fetch(url,options)});host.on('state',publish);
  home=new BrowserWindow({width:1040,height:850,minWidth:760,minHeight:600,backgroundColor:'#111916',title:'Запретные Земли · подключение',show:false,icon:path.join(__dirname,'ui/app-icon.png'),webPreferences:{preload:path.join(__dirname,'preload.cjs'),nodeIntegration:false,contextIsolation:true,sandbox:true,webSecurity:true}});
  configureSession(home.webContents.session);home.webContents.setWindowOpenHandler(()=>({action:'deny'}));home.webContents.on('will-navigate',event=>event.preventDefault());
  handle('state',()=>state());handle('start',async()=>{await host.start();settings.port=host.port;saveSettings();return state();});handle('open',local);handle('connect',connect);
  handle('browser',async()=>{await host.start();await shell.openExternal(host.state.localUrl);return state();});
  handle('share',async()=>{await host.share();settings.port=host.port;saveSettings();return state();});handle('unshare',()=>{host.stopSharing();return state();});
  handle('copy',text=>{if(typeof text!=='string'||![host.state.localUrl,host.state.shareUrl].includes(text)||!text)throw Error('Нет адреса для копирования.');clipboard.writeText(text);return state();});
  handle('folder',async()=>{fs.mkdirSync(host.data,{recursive:true});await shell.openPath(host.data);return state();});
  handle('backup',async()=>{await host.start();const selected=await dialog.showOpenDialog(home,{title:'Папка для резервной копии кампаний',properties:['openDirectory','createDirectory'],defaultPath:app.getPath('documents')});if(selected.canceled)return state();const folder=await host.backup(selected.filePaths[0]);host.update({message:'Резервная копия создана: '+folder,error:''});return state();});
  Menu.setApplicationMenu(Menu.buildFromTemplate([
   {label:'Игра',submenu:[{label:'Подключение и приглашения',click:()=>{home.show();home.focus();}},{label:'Открыть свою игру',click:()=>local().catch(e=>host.update({error:e.message}))},{type:'separator'},{label:'Выход',click:()=>home.close()}]},
   {label:'Правка',submenu:[{role:'undo',label:'Отменить'},{role:'redo',label:'Повторить'},{type:'separator'},{role:'cut',label:'Вырезать'},{role:'copy',label:'Копировать'},{role:'paste',label:'Вставить'},{role:'selectAll',label:'Выделить всё'}]},
   {label:'Вид',submenu:[{role:'reload',label:'Обновить'},{role:'resetZoom',label:'Масштаб 100%'},{role:'zoomIn',label:'Приблизить'},{role:'zoomOut',label:'Отдалить'},{role:'togglefullscreen',label:'Полный экран'}]}
  ]));
  home.on('close',event=>{if(quitting)return;event.preventDefault();if(host.state.server==='running'){const response=dialog.showMessageBoxSync(home,{type:'question',buttons:['Оставить игру работающей','Закрыть приложение'],defaultId:0,cancelId:0,message:'Завершить работу приложения?',detail:'Ваша игра на этом компьютере станет недоступна подключённым игрокам. Подтверждённые действия уже сохранены.'});if(response!==1)return;}quit();});
  home.once('ready-to-show',()=>home.show());home.loadFile(homeFile);
 }).catch(e=>{dialog.showErrorBox('Запретные Земли',e.message);quitting=true;app.quit();});
}
