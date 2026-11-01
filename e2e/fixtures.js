import {test as base,expect} from '@playwright/test';
import {spawn,spawnSync} from 'node:child_process';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const gameRoot=fileURLToPath(new URL('..',import.meta.url));
function pythonCommand(){
  const candidates=process.env.PYTHON?[[process.env.PYTHON,[]]]:[['python3',[]],['python',[]],...(process.platform==='win32'?[['py',['-3']]]:[])];
  for(const [command,args] of candidates){
    const result=spawnSync(command,[...args,'-c','import sys;sys.exit(0 if sys.version_info>=(3,11) else 1)'],{encoding:'utf8',windowsHide:true,timeout:10000});
    if(!result.error&&result.status===0)return {command,args};
  }
  throw Error('Python 3.11+ is required. Set PYTHON to its executable path (without shell arguments), or add python3/python to PATH.');
}

async function isolatedServer(){
  const directory=await mkdtemp(path.join(tmpdir(),'zz-playwright-')),python=pythonCommand();
  let child,url,logs='',exited;
  const append=data=>{logs=(logs+data.toString()).slice(-50000);};
  async function start(){
    child=spawn(python.command,[...python.args,'-u',path.join(gameRoot,'e2e/server.py'),'--data',directory],{
      cwd:gameRoot,windowsHide:true,stdio:['pipe','pipe','pipe'],
      env:{...process.env,ZZ_NODE:process.execPath,PYTHONIOENCODING:'utf-8',PYTHONDONTWRITEBYTECODE:'1'},
    });
    exited=new Promise(resolve=>child.once('close',(code,signal)=>resolve({code,signal})));
    child.stdin.on('error',()=>{});
    child.stderr.on('data',append);child.stdout.on('data',append);
    url=await new Promise((resolve,reject)=>{
      let buffer='';const timer=setTimeout(()=>reject(Error('E2E server startup timed out\n'+logs)),20000);
      const finish=(error,value)=>{clearTimeout(timer);child.stdout.off('data',read);error?reject(error):resolve(value);};
      const read=data=>{buffer+=data.toString();for(const line of buffer.split('\n').slice(0,-1)){try{const item=JSON.parse(line);if(/^http:\/\/127\.0\.0\.1:\d+\/$/.test(item.url))return finish(null,item.url);}catch{}}buffer=buffer.split('\n').at(-1);};
      child.stdout.on('data',read);child.once('error',error=>finish(error));child.once('exit',code=>finish(Error('E2E server exited '+code+'\n'+logs)));
    });
    const health=await fetch(url+'api/health',{signal:AbortSignal.timeout(5000)});expect(health.ok).toBeTruthy();
  }
  async function stop(){
    if(!child?.pid||child.exitCode!==null)return;
    child.stdin.end('stop\n');
    const timer=setTimeout(()=>child.kill(),6000);
    await exited;clearTimeout(timer);
  }
  try{await start();}catch(error){await stop();await rm(directory,{recursive:true,force:true});throw error;}
  return {
    get url(){return url;},get logs(){return logs;},
    async restart(){await stop();await start();},
    async close(){await stop();await rm(directory,{recursive:true,force:true,maxRetries:5,retryDelay:150});},
    async api(endpoint,data,auth,status=200){
      const response=await fetch(url+'api/'+endpoint,{method:data===undefined?'GET':'POST',headers:{...(data===undefined?{}:{'Content-Type':'application/json'}),...(auth?{Authorization:auth.token}:{})},body:data===undefined?undefined:JSON.stringify(data),signal:AbortSignal.timeout(15000)});
      const result=await response.json();expect(response.status,JSON.stringify(result)).toBe(status);return result;
    },
  };
}

export const test=base.extend({
  server:async({},use,testInfo)=>{
    const server=await isolatedServer();
    try{await use(server);}finally{if(testInfo.status!==testInfo.expectedStatus)await testInfo.attach('isolated-server.log',{body:server.logs,contentType:'text/plain'});await server.close();}
  },
  // Each participant has separate cookies/storage. Capture every participant on
  // failure, in addition to Playwright's retained traces and default page image.
  clients:async({browser},use,testInfo)=>{
    const contexts=[],errors=[];
    async function create(options={}){
      const context=await browser.newContext({viewport:{width:1440,height:1000},...options});contexts.push(context);
      context.on('page',page=>page.on('pageerror',e=>errors.push(e.message)));
      return context.newPage();
    }
    try{await use(create);expect(errors,'Browser JavaScript errors').toEqual([]);}finally{
      if(testInfo.status!==testInfo.expectedStatus||errors.length)for(const [i,context] of contexts.entries())for(const [j,page] of context.pages().entries())if(!page.isClosed()){
        await testInfo.attach(`client-${i}-${j}.png`,{body:await page.screenshot({fullPage:true,timeout:5000}).catch(()=>Buffer.alloc(0)),contentType:'image/png'});
      }
      for(const context of contexts)await context.close();
    }
  },
});
export {expect};

export async function openCampaign(page,server,credentials,{view='scene',muted=true}={}){
  await page.addInitScript(({credentials,view,muted})=>{
    sessionStorage.setItem('campaign',JSON.stringify(credentials));sessionStorage.setItem('campaign-view',view);
    localStorage.setItem('zz-interface-settings',JSON.stringify({version:1,audio:{muted,master:50,effects:65,ambience:25,hiddenBehavior:'pause'}}));
    window.testAudioCues=[];addEventListener('zz:audio-cue',event=>window.testAudioCues.push(event.detail));
  },{credentials,view,muted});
  await page.goto(server.url+'index.html');await expect(page.locator('#table')).toBeVisible();
}
export async function register(page,server,login,name){
  await page.goto(server.url);await page.getByRole('button',{name:'Регистрация',exact:true}).click();
  await page.getByLabel('Логин',{exact:true}).fill(login);await page.getByLabel('Имя за столом',{exact:true}).fill(name);
  await page.getByLabel('Пароль',{exact:true}).fill('e2e isolated account password 42');await page.getByRole('button',{name:'Создать аккаунт',exact:true}).click();
  await page.getByRole('button',{name:'Код сохранён · продолжить',exact:true}).click();await expect(page.locator('#account-dashboard')).toBeVisible();
}
export async function refresh(page){await page.evaluate(()=>dispatchEvent(new Event('online')));}
export async function editorReady(page,selector){
  await expect(page.locator(selector+':not([aria-busy])')).toBeVisible();
  const frame=page.frameLocator(selector);await expect(frame.locator('body:not([inert])')).toBeVisible();return frame;
}
