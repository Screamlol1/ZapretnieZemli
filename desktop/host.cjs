const {EventEmitter}=require('node:events'),{spawn}=require('node:child_process');
const fs=require('node:fs'),fsp=fs.promises,path=require('node:path'),crypto=require('node:crypto');
const pause=ms=>new Promise(r=>setTimeout(r,ms));
class GameHost extends EventEmitter{
 constructor({resources,data,runtime=path.join(resources,'runtime'),port=8791,request=(...args)=>fetch(...args)}){super();this.resources=resources;this.runtime=runtime;this.data=data;this.port=port;this.request=request;this.state={localUrl:'',shareUrl:'',server:'stopped',sharing:'stopped',message:'',error:''};this.pending=new Map();this.closing=false;}
 update(patch){Object.assign(this.state,patch);this.emit('state',{...this.state});}
 log(name,chunk){const file=path.join(this.data,name);try{if(fs.existsSync(file)&&fs.statSync(file).size>2*1024*1024)fs.renameSync(file,file+'.previous');fs.appendFileSync(file,chunk);}catch{}}
 rejectPending(error){for(const pending of this.pending.values())pending.reject(error);this.pending.clear();}
 async start(){
  if(this.stopping)await this.stopping;
  if(this.child&&this.state.server==='running')return this.state;
  if(this.starting)return this.starting;
  this.closing=false;this.update({server:'starting',error:'',message:'Открываем сохранённые кампании…'});
  this.starting=this._start().catch(e=>{if(!this.closing)this.update({server:'error',error:e.message,message:''});throw e;}).finally(()=>this.starting=null);return this.starting;
 }
 async _start(){
  await fsp.mkdir(this.data,{recursive:true});
  const python=path.join(this.runtime,'python/python.exe'),node=path.join(this.runtime,'node/node.exe'),script=path.join(this.resources,'desktop_server.py');
  for(const file of [python,node,script])await fsp.access(file);
  if(this.closing)throw Error('Приложение закрывается.');
  const child=this.child=spawn(python,['-I','-X','utf8',script,'--data',this.data,'--port',String(this.port)],{cwd:this.data,windowsHide:true,stdio:['pipe','pipe','pipe'],env:{...process.env,ZZ_NODE:node,PYTHONIOENCODING:'utf-8'}});
  child.stdin.on('error',error=>{this.log('server.log',`stdin ${error.code||'error'}: ${error.message}\n`);if(this.child===child)this.rejectPending(Error('Связь со встроенным сервером прервалась: '+error.message));});
  child.stderr.on('data',chunk=>this.log('server.log',chunk));let buffer='';
  await new Promise((resolve,reject)=>{
   const timeout=setTimeout(()=>{child.kill();reject(Error('Сервер не запустился за 45 секунд. Подробности — server.log в папке сохранений.'));},45000);
   child.once('error',e=>{clearTimeout(timeout);reject(Error('Не удалось запустить встроенный сервер: '+e.message));});
   child.on('exit',code=>{clearTimeout(timeout);if(this.child===child){this.child=null;this.stopSharing();this.update({server:this.closing?'stopped':'error',localUrl:'',error:this.closing?'':'Сервер остановился. Откройте папку сохранений и проверьте server.log.'});this.rejectPending(Error('Сервер остановился.'));}reject(Error('Встроенный сервер завершился с кодом '+code));});
   child.stdout.on('data',chunk=>{buffer+=chunk.toString('utf8');let cut;while((cut=buffer.indexOf('\n'))>=0){const line=buffer.slice(0,cut);buffer=buffer.slice(cut+1);let msg;try{msg=JSON.parse(line);}catch{continue;}
    if(msg.type==='ready'&&/^http:\/\/127\.0\.0\.1:\d+\/$/.test(msg.url)){clearTimeout(timeout);if(this.closing){reject(Error('Приложение закрывается.'));continue;}this.port=Number(new URL(msg.url).port);this.update({server:'running',localUrl:msg.url,message:'Игра готова. Сохранения записываются автоматически.',error:''});resolve();}
    if(msg.id&&this.pending.has(msg.id)){const pending=this.pending.get(msg.id);this.pending.delete(msg.id);msg.type==='error'?pending.reject(Error(msg.message)):pending.resolve(msg.path);}
   }});
  });return this.state;
 }
 async backup(output){
  await this.start();const id=crypto.randomUUID(),child=this.child;
  if(this.closing||!child||this.state.server!=='running')throw Error('Сервер остановился.');
  return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{this.pending.delete(id);reject(Error('Копирование ещё не подтверждено. Проверьте выбранную папку.'));},60000);this.pending.set(id,{resolve:p=>{clearTimeout(timer);resolve(p);},reject:e=>{clearTimeout(timer);reject(e);}});try{child.stdin.write(JSON.stringify({op:'backup',id,output})+'\n');}catch(error){const pending=this.pending.get(id);this.pending.delete(id);pending.reject(error);}});
 }
 async share(){
  if(this.state.sharing==='running')return this.state;
  if(this.sharingPromise)return this.sharingPromise;
  this.sharingPromise=this._share().catch(e=>{this.stopSharing();if(!this.closing)this.update({sharing:'error',error:e.message,message:''});throw e;}).finally(()=>this.sharingPromise=null);return this.sharingPromise;
 }
 async _share(){
  await this.start();if(this.closing)throw Error('Приложение закрывается.');
  this.update({sharing:'starting',error:'',message:'Создаём ссылку для игроков. Обычно это занимает до минуты…'});
  const config=path.join(this.data,'quick-tunnel.yml');await fsp.writeFile(config,'{}\n');
  if(this.closing)throw Error('Приложение закрывается.');
  const tunnel=this.tunnel=spawn(path.join(this.runtime,'cloudflared/cloudflared.exe'),['tunnel','--config',config,'--url',this.state.localUrl,'--no-autoupdate','--protocol','auto'],{cwd:this.data,windowsHide:true,stdio:['ignore','pipe','pipe']});
  let url='',failure='',text='';const output=chunk=>{this.log('sharing.log',chunk);text=(text+chunk.toString('utf8')).slice(-12000);const match=text.match(/https:\/\/[a-z0-9-]+\.trycloudflare\.com/);if(match)url=match[0]+'/';};
  tunnel.stdout.on('data',output);tunnel.stderr.on('data',output);
  tunnel.on('error',e=>failure=e.message);tunnel.on('exit',()=>{failure='Соединение для приглашений завершилось.';if(this.tunnel===tunnel){this.tunnel=null;this.update({sharing:'stopped',shareUrl:'',message:failure});}});
  const until=Date.now()+110000;
  while(Date.now()<until){
   if(this.tunnel!==tunnel||this.closing||failure)throw Error(failure||'Создание ссылки отменено.');
   if(url){try{const r=await this.request(url+'api/health',{signal:AbortSignal.timeout(5000)});const health=await r.json();if(r.ok&&health.ok===true&&health.publicTest===true&&this.tunnel===tunnel&&!this.closing){this.update({sharing:'running',shareUrl:url,message:'Приглашение готово. Отправьте ссылку и код кампании игрокам.',error:''});return this.state;}}catch{}}
   await pause(750);
  }
  throw Error('Не удалось проверить ссылку через интернет. Проверьте сеть и повторите. Локальная игра продолжает работать.');
 }
 stopSharing(){const child=this.tunnel;this.tunnel=null;if(child)child.kill();this.update({sharing:'stopped',shareUrl:'',message:'Доступ через интернет выключен.'});return this.state;}
 async stop(){
  if(this.stopping)return this.stopping;
  this.closing=true;this.stopSharing();const child=this.child,starting=this.starting;
  this.stopping=(async()=>{
   if(child)await new Promise(resolve=>{const timer=setTimeout(()=>{child.kill();resolve();},8000);const done=()=>{clearTimeout(timer);resolve();};child.once('exit',done);child.once('close',done);if(child.exitCode!==null){done();}else try{child.stdin.end(JSON.stringify({op:'stop'})+'\n');}catch(error){this.log('server.log',`stdin stop: ${error.message}\n`);child.kill();}});
   // _start may still be waiting for filesystem checks when shutdown begins.
   // It checks closing before spawning; wait until it has actually settled.
   if(starting)await starting.catch(()=>{});
   this.update({server:'stopped',localUrl:'',error:''});
  })().finally(()=>this.stopping=null);
  return this.stopping;
 }
}
module.exports={GameHost};
