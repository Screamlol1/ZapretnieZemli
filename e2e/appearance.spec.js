import {blank} from '../public/tools/rules.js';
import {test,expect,openCampaign,refresh} from './fixtures.js';

test('Layered appearance saves for its owner, animates, respects mobile and survives reconnect',async({clients,server},testInfo)=>{
 const gm=await server.api('create',{name:'Мастер',title:'Облик'}),player=await server.api('join',{name:'Игрок',code:gm.code,key:gm.playerKey});
 const hero=(await server.api('action',{action:'character',sheet:{...blank(),name:'Искатель'}},player)).characters[0];
 const page=await clients();await openCampaign(page,server,player,{view:'crew'});await page.locator(`[data-visual="${hero.id}"]`).click();const dialog=page.locator('.visual-dialog');
 await dialog.locator('[name=style]').selectOption('miniature');await dialog.locator('[name=hairStyle]').selectOption('braid');await dialog.locator('[name=beard]').selectOption('short');await dialog.locator('[name=outfit]').selectOption('mail');await dialog.locator('[name=mainHand]').selectOption('axe');await dialog.locator('[name=offHand]').selectOption('shield');
 await expect.poll(()=>dialog.locator('.appearance-preview').evaluate(e=>e.complete&&e.naturalWidth>0)).toBe(true);
 await dialog.screenshot({path:testInfo.outputPath('appearance-desktop.png')});
 await dialog.locator('[data-preview-pose]').selectOption('walk');
 const img=dialog.locator('.appearance-preview');await expect(img).toHaveAttribute('src',/data-pose%3D%22walk/);
 const first=await img.screenshot();await page.waitForTimeout(230);const second=await img.screenshot();expect(first.equals(second)).toBe(false);
 await dialog.locator('[name=direction]').selectOption('left');await dialog.locator('[data-preview-pose]').selectOption('block');await dialog.locator('[data-save]').click();await expect(dialog).toBeHidden();
 const state=await server.api('state',undefined,player),saved=state.characters.find(c=>c.id===hero.id);expect(saved.visual).toMatchObject({hairStyle:'braid',beard:'short',outfit:'mail',mainHand:'axe',offHand:'shield',direction:'left'});expect(saved.runtime).toEqual(hero.runtime);
 await page.setViewportSize({width:390,height:844});await page.locator(`[data-visual="${hero.id}"]`).click();expect(await dialog.evaluate(e=>e.scrollWidth<=e.clientWidth+1)).toBe(true);await dialog.screenshot({path:testInfo.outputPath('appearance-mobile.png')});await dialog.locator('[data-close]').click();
 await server.restart();const resumed=await server.api('resume',{code:player.code,resume:player.resume});expect((await server.api('state',undefined,resumed)).characters.find(c=>c.id===hero.id).visual).toEqual(saved.visual);
});

test('Eight peoples keep their proportions and all poses decode with reduced motion',async({clients,server},testInfo)=>{
 const page=await clients();await page.goto(server.url);
 await page.evaluate(async()=>{const {spriteURL,visualDefaults}=await import('/appearance.js');const root=document.createElement('section');root.id='appearance-gallery';root.style='display:grid;grid-template-columns:repeat(4,1fr);gap:16px;background:#17271e;padding:20px;position:relative;z-index:1000';document.body.replaceChildren(root);
  for(const kin of ['human','elf','halfelf','dwarf','halfling','wolfkin','orc','goblin']){const actor={kind:'pc',sheet:{kin},visual:{...visualDefaults({sheet:{kin}}),style:'painted',mainHand:'sword',offHand:'shield'}};const figure=document.createElement('figure');figure.style='margin:0;text-align:center;color:#ddd3b4';figure.innerHTML='<img width="220" height="220" alt=""><figcaption></figcaption>';figure.querySelector('figcaption').textContent=kin;figure.querySelector('img').src=await spriteURL(actor);root.append(figure);}
 });
 await page.locator('#appearance-gallery img').evaluateAll(imgs=>Promise.all(imgs.map(img=>img.decode())));await page.locator('#appearance-gallery').screenshot({path:testInfo.outputPath('appearance-peoples.png')});
 const results=await page.evaluate(async()=>{const {spriteURL,visualDefaults}=await import('/appearance.js');document.documentElement.dataset.reducedMotion='true';const results=[];for(const pose of ['walk','strike','shoot','block','dodge','cast','fall']){const url=await spriteURL({sheet:{kin:'human'},visual:{...visualDefaults({}),style:'miniature',mainHand:'bow'}},pose),img=new Image();img.src=url;await img.decode();results.push({pose,animated:decodeURIComponent(url).includes('animateTransform')});}return results;});expect(results.every(r=>!r.animated)).toBe(true);
 await page.evaluate(async()=>{const {spriteURL,visualDefaults}=await import('/appearance.js');const root=document.getElementById('appearance-gallery');root.replaceChildren();for(const [i,pose] of ['idle','walk','strike','shoot','block','dodge','cast','fall'].entries()){const kin=['human','elf','dwarf','halfling','wolfkin','orc','goblin','halfelf'][i],actor={kind:'pc',sheet:{kin},visual:{...visualDefaults({sheet:{kin}}),style:'miniature',mainHand:pose==='shoot'?'bow':pose==='cast'?'staff':'axe',offHand:pose==='block'?'shield':'none'}};const figure=document.createElement('figure');figure.style='margin:0;text-align:center;color:#ddd3b4';figure.innerHTML='<img width="220" height="220" alt=""><figcaption></figcaption>';figure.querySelector('figcaption').textContent=kin+' · '+pose;figure.querySelector('img').src=await spriteURL(actor,{pose,animate:false});root.append(figure);}});
 await page.locator('#appearance-gallery img').evaluateAll(imgs=>Promise.all(imgs.map(img=>img.decode())));await page.locator('#appearance-gallery').screenshot({path:testInfo.outputPath('appearance-poses.png')});
});
