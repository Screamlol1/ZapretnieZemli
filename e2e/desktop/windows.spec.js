import {test,expect,_electron} from '@playwright/test';
import {mkdtemp,rm,access} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {editorReady,register,openCampaign} from '../fixtures.js';

const desktopRoot=path.resolve(fileURLToPath(new URL('../../desktop/',import.meta.url)));
// This runner targets the real Windows runtime, independent of any live install.
test('Windows settings, seamless editor and browser crossplay in one native window',async({browser},testInfo)=>{
  test.skip(process.platform!=='win32','Windows Electron and embedded-runtime test.');
  const executable=process.env.ZZ_TEST_EXE||path.join(desktopRoot,'node_modules/electron/dist/electron.exe');
  for(const required of [executable,path.join(desktopRoot,'.runtime/python/python.exe'),path.join(desktopRoot,'.runtime/node/node.exe')]){
    try{await access(required);}catch{throw Error('Desktop prerequisites missing. Run npm --prefix desktop ci && npm --prefix desktop run prepare:runtime. Missing: '+required);}
  }
  const directory=await mkdtemp(path.join(tmpdir(),'zz-electron-e2e-'));let app,shell,home,game;
  const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;
  const errors=[];
  async function findPage(match){await expect.poll(()=>app.context().pages().some(page=>match(page.url()))).toBe(true);return app.context().pages().find(page=>match(page.url()));}
  async function oneWindow(){expect(await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows().length)).toBe(1);}
  async function launch(){
    app=await _electron.launch({executablePath:executable,args:[...(!process.env.ZZ_TEST_EXE?[desktopRoot]:[]),'--zz-data-dir='+directory],env,timeout:60000});
    await app.context().tracing.start({screenshots:true,snapshots:true,sources:true});
    app.context().on('page',page=>page.on('pageerror',error=>errors.push(error.message)));
    shell=await findPage(url=>url.endsWith('/shell.html'));home=await findPage(url=>url.endsWith('/ui/index.html'));await expect(home.locator('#start-local')).toBeVisible();
  }
  async function closeApplication(failed=false){
    if(!app)return;
    if(failed&&shell&&!shell.isClosed())await testInfo.attach('native-shell.png',{body:await shell.screenshot(),contentType:'image/png'});
    const tracePath=testInfo.outputPath('electron-trace.zip');await app.context().tracing.stop(failed?{path:tracePath}:{});if(failed)await testInfo.attach('electron-trace',{path:tracePath,contentType:'application/zip'});
    await app.evaluate(({dialog})=>{dialog.showMessageBoxSync=()=>1;});await app.close();app=null;
  }
  try{
    await launch();await shell.locator('#open-settings').click();await expect(shell.locator('#settings-dialog')).toBeVisible();
    await shell.locator('#resolution').selectOption('1280x720');await shell.locator('#apply-settings').click();await expect(shell.locator('#display-confirm')).toBeVisible();await shell.locator('#confirm-display').click();
    expect(await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].getSize())).toEqual([1280,720]);
    await shell.locator('label.mode-option:has(input[value=borderless])').click();await shell.locator('#apply-settings').click();await expect(shell.locator('#display-confirm')).toBeVisible();await shell.locator('#revert-display').click();expect((await shell.evaluate(()=>desktop.getState())).preferences.mode).toBe('windowed');
    await shell.locator('#close-settings').click();await home.locator('#start-local').click();game=await findPage(url=>/^http:\/\/127\.0\.0\.1/.test(url));const url=new URL(game.url()).origin+'/';
    await oneWindow();expect(await game.evaluate(()=>[typeof desktop,typeof require,typeof process])).toEqual(['undefined','undefined','undefined']);
    await register(game,{url},'native.master','Мастер');await game.getByRole('button',{name:/Мои персонажи/}).click();await game.locator('#new-account-character').click();const editor=await editorReady(game,'#account-editor iframe');await editor.locator('#name').fill('Черновик единого окна');
    await shell.locator('#go-home').click();await expect(home.locator('#start-local')).toBeVisible();await shell.locator('#resume-game').click();await expect(editor.locator('#name')).toHaveValue('Черновик единого окна');await oneWindow();await editor.locator('.campaign-save').click();await expect(game.locator('#account-editor')).toBeHidden();
    await game.getByRole('button',{name:'Кампании',exact:true}).click();await game.getByLabel('Название кампании',{exact:true}).fill('Общий стол Windows');await game.getByRole('button',{name:'Создать кампанию',exact:true}).click();await expect(game.locator('#table')).toBeVisible();
    const invite=await game.evaluate(()=>JSON.parse(sessionStorage.campaign));const response=await fetch(url+'api/join',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'Браузер',code:invite.code,key:invite.playerKey})});expect(response.ok).toBeTruthy();const joined=await response.json();
    const context=await browser.newContext();const player=await context.newPage();await openCampaign(player,{url},joined,{view:'journal'});await game.locator('[data-view=journal]').click();await player.locator('#roll').click();
    for(const page of [player,game])await expect(page.locator('#dice-stage')).toHaveAttribute('data-phase','result');expect(await player.locator('#dice-stage').getAttribute('data-roll-id')).toBe(await game.locator('#dice-stage').getAttribute('data-roll-id'));await context.close();
    await shell.locator('#open-settings').click();await shell.locator('label.mode-option:has(input[value=borderless])').click();await shell.locator('#apply-settings').click();await shell.locator('#confirm-display').click();await shell.locator('#close-settings').click();await oneWindow();
    await closeApplication();await launch();expect((await shell.evaluate(()=>desktop.getState())).preferences.mode).toBe('borderless');await home.locator('#start-local').click();game=await findPage(url=>/^http:\/\/127\.0\.0\.1/.test(url));await expect(game.getByRole('button',{name:'Продолжить как Мастер',exact:true})).toBeVisible();await oneWindow();expect(errors).toEqual([]);
  }finally{await closeApplication(testInfo.status!==testInfo.expectedStatus);await rm(directory,{recursive:true,force:true,maxRetries:5,retryDelay:200});}
});
