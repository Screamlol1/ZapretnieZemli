import {test,expect,_electron} from '@playwright/test';
import {mkdtemp,rm,readdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root=path.resolve(fileURLToPath(new URL('../../desktop/',import.meta.url)));
test('Native update status and recovery preserve a rescue copy of real isolated campaigns',async({},info)=>{
 test.skip(process.platform!=='win32');
 const directory=await mkdtemp(path.join(tmpdir(),'zz-native-recovery-')),backups=path.join(directory,'manual-copies'),env={...process.env};delete env.ELECTRON_RUN_AS_NODE;let app;
 try{
  app=await _electron.launch({executablePath:process.env.ZZ_TEST_EXE||path.join(root,'node_modules/electron/dist/electron.exe'),args:[...(!process.env.ZZ_TEST_EXE?[root]:[]),'--zz-data-dir='+directory],env});
  await expect.poll(()=>app.context().pages().some(p=>p.url().endsWith('/shell.html'))).toBe(true);
  const shell=app.context().pages().find(p=>p.url().endsWith('/shell.html')),errors=[];shell.on('pageerror',e=>errors.push(e.message));
  await shell.locator('#open-settings').click();await shell.locator('#tab-updates').click();
  await app.evaluate(({net})=>{const real=net.fetch;net.fetch=(url,options)=>String(url).startsWith('https://api.github.com/repos/Screamlol1/ZapretnieZemli/releases/')?Promise.resolve({ok:false,status:404}):real(url,options);});
  await shell.locator('#check-updates').click();await expect(shell.locator('#update-status')).toContainText('Публичного выпуска пока нет');
  await expect(shell.locator('#download-update')).toBeHidden();await expect(shell.locator('#install-update')).toBeHidden();
  await shell.screenshot({path:info.outputPath('updates-native.png')});
  await shell.locator('#close-settings').click();
  const home=app.context().pages().find(p=>p.url().endsWith('/ui/index.html'));await home.locator('#start-local').click();
  await expect.poll(async()=>(await shell.evaluate(()=>desktop.getState())).server).toBe('running');
  const state=await shell.evaluate(()=>desktop.getState()),base=state.localUrl;
  const api=async(name,data,token)=>{const r=await fetch(base+'api/'+name,{method:'POST',headers:{'Content-Type':'application/json',...(token?{Authorization:token}:{})},body:JSON.stringify(data)});expect(r.ok).toBe(true);return r.json();};
  const gm=await api('create',{name:'Мастер',title:'До копии'});
  await app.evaluate(({dialog},folder)=>{dialog.showOpenDialog=async()=>({canceled:false,filePaths:[folder]});},backups);
  await shell.evaluate(()=>desktop.backup());
  const folder=path.join(backups,(await readdir(backups))[0]);
  await api('action',{action:'campaignCodex',op:'save',version:0,entry:{kind:'note',title:'После копии',visibility:'gm'}},gm.token);
  await app.evaluate(({dialog})=>{dialog.showOpenDialog=()=>new Promise(resolve=>{globalThis.resolveRecoveryDialog=resolve;});});
  await shell.evaluate(()=>{window.restoreAttempt=desktop.restoreBackup().catch(e=>({error:e.message}));});
  await expect.poll(()=>app.evaluate(()=>Boolean(globalThis.resolveRecoveryDialog))).toBe(true);
  const duplicate=await shell.evaluate(async()=>{try{await desktop.restoreBackup();return '';}catch(e){return e.message;}});
  expect(duplicate).toContain('обслуживания');
  await app.evaluate(()=>{globalThis.resolveRecoveryDialog({canceled:true});delete globalThis.resolveRecoveryDialog;});
  expect(await shell.evaluate(()=>window.restoreAttempt)).toMatchObject({canceled:true});
  expect((await shell.evaluate(()=>desktop.getState())).maintenance).toBe(false);
  await app.evaluate(({dialog},folder)=>{dialog.showOpenDialog=async()=>({canceled:false,filePaths:[folder]});dialog.showMessageBox=async()=>({response:1});},folder);
  await shell.locator('#open-settings').click();await shell.locator('#tab-updates').click();await shell.locator('#restore-backup').click();await expect(shell.locator('#recovery-status')).toContainText('Данные восстановлены');
  const after=await shell.evaluate(()=>desktop.getState());expect(after.server).toBe('running');
  const resume=await fetch(after.localUrl+'api/resume',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:gm.code,resume:gm.resume})});expect(resume.ok).toBe(true);const credentials=await resume.json();
  const actual=await fetch(after.localUrl+'api/state',{headers:{Authorization:credentials.token}}).then(r=>r.json());expect(actual.title).toBe('До копии');expect(actual.codex.entries).toHaveLength(0);
  expect((await readdir(path.join(directory,'update-backups'))).length).toBe(1);expect(errors).toEqual([]);
 }finally{if(app){await app.evaluate(({dialog})=>{dialog.showMessageBoxSync=()=>1;});await app.close();}await rm(directory,{recursive:true,force:true,maxRetries:5,retryDelay:200});}
});
