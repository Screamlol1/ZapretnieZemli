import {readFile} from 'node:fs/promises';
import {blank} from '../public/tools/rules.js';
import {test,expect,openCampaign,refresh} from './fixtures.js';

test('Personal sight, floors, prepared scenes and portable adventure work for GM and player',async({clients,server},testInfo)=>{
 test.setTimeout(120000);
 const auth=await server.api('create',{name:'Мастер',title:'Башня'}),pa=await server.api('join',{name:'Игрок',code:auth.code,key:auth.playerKey});
 const hero=(await server.api('action',{action:'character',sheet:{...blank(),name:'Исследователь'}},pa)).characters.find(c=>c.name==='Исследователь');
 let map=(await server.api('action',{action:'locationMapGenerate',title:'Нижний двор',settings:{kind:'camp',seed:'advanced-browser',size:'small'}},auth)).locationMaps[0];
 const latest=async()=>{const s=await server.api('state',undefined,auth);map=s.locationMaps.find(m=>m.id===map.id);return s;};
 async function act(data){await latest();const s=await server.api('action',{action:'locationAdvanced',map:map.id,version:map.version,...data},auth);map=s.locationMaps.find(m=>m.id===map.id);return s;}
 map=(await server.api('action',{action:'locationMapEdit',id:map.id,version:map.version,op:'token',characterId:hero.id,point:[200,200],secret:false},auth)).locationMaps[0];
 await server.api('action',{action:'locationMapReveal',id:map.id,version:map.version,revealed:true},auth);await latest();
 const gm=await clients(),player=await clients({viewport:{width:390,height:844}});await openCampaign(gm,server,auth,{view:'locations'});await openCampaign(player,server,pa,{view:'locations'});
 for(const p of [gm,player])await p.locator('[data-location-library]').selectOption(map.id);
 await gm.locator('[data-advanced-open=floors]').click();let dialog=gm.locator('.location-advanced-dialog');
 await dialog.locator('[name=enabled]').check();await dialog.locator('[name=range]').fill('30');await dialog.locator('[data-advanced-form=vision] button').click();
 await expect.poll(async()=>(await latest()).locationMaps[0].vision?.enabled).toBe(true);
 await refresh(player);await expect(player.locator('[data-location-canvas] [id=location-vision]')).toHaveCount(1);
 await dialog.locator('[data-advanced-form=floorCreate] [name=title]').fill('Подвал');await dialog.locator('[data-advanced-form=floorCreate] button').click();await expect(dialog).toBeHidden();
 const basement=(await latest()).locationMaps.find(m=>m.title==='Подвал');expect(basement.revealed).toBe(false);
 await gm.locator('[data-location-library]').selectOption(map.id);await gm.locator('[data-advanced-open=floors]').click();
 const link=dialog.locator('[data-advanced-form=stairsLink]');await link.locator('[name=targetMap]').selectOption(basement.id);await link.locator('[name=x]').fill('200');await link.locator('[name=y]').fill('200');await link.locator('button').click();
 await expect.poll(async()=>(await latest()).locationMaps[0].stairs?.length).toBe(1);await dialog.locator('[data-advanced-close]').click();
 await latest();const target=(await server.api('state',undefined,auth)).locationMaps.find(m=>m.id===basement.id);await server.api('action',{action:'locationMapReveal',id:target.id,version:target.version,revealed:true},auth);
 await refresh(player);await player.locator('[data-advanced-open=floors]').click();await player.locator('.location-advanced-dialog [data-stairs-travel]').click();await expect(player.locator('[data-floor-select]')).toHaveValue(basement.id);
 expect((await server.api('state',undefined,pa)).characters.find(c=>c.id===hero.id).runtime).toEqual(hero.runtime);
 await refresh(gm);await expect(gm.locator('[data-location-canvas] [data-location-token]')).toHaveCount(0);
 await gm.locator('[data-advanced-open=presets]').click();await dialog.locator('[name=title]').fill('Тихий двор');await dialog.locator('[name=gmNote]').fill('PRIVATE-SCENE-TRAP');await dialog.locator('[data-advanced-form=presetSave] button').click();await expect(dialog.locator('[data-preset-apply]')).toHaveCount(1);
 gm.on('dialog',d=>d.accept());await dialog.locator('[data-preset-apply]').click();await expect.poll(async()=>(await latest()).scene?.title).toBe('Тихий двор');await dialog.locator('[data-advanced-close]').click();
 await gm.locator('[data-advanced-open=packs]').click();const download=gm.waitForEvent('download');await dialog.locator('[data-advanced-form=packExport] button').click();const file=testInfo.outputPath('tower-adventure.json');await(await download).saveAs(file);const pack=JSON.parse(await readFile(file,'utf8'));expect(pack.maps).toHaveLength(2);expect(pack.actors).toHaveLength(0);
 await dialog.locator('[data-adventure-file]').setInputFiles(file);await dialog.locator('[data-pack-preview]').click();await expect(dialog.locator('[data-pack-import]')).toBeVisible();await dialog.locator('[data-pack-import]').click();await expect.poll(async()=>(await latest()).locationMaps.length).toBe(4);
 const ps=await server.api('state',undefined,pa);expect(ps.locationMaps).toHaveLength(2);expect(JSON.stringify(ps)).not.toContain('PRIVATE-SCENE-TRAP');expect(ps.locationPackPreview).toBeUndefined();
 await player.locator('[data-advanced-open=floors]').click();expect(await player.locator('.location-advanced-dialog').evaluate(e=>e.scrollWidth<=e.clientWidth+1)).toBe(true);await player.screenshot({path:testInfo.outputPath('advanced-mobile.png')});
 await server.restart();const resumed=await server.api('resume',{code:auth.code,resume:auth.resume});expect((await server.api('state',undefined,resumed)).locationMaps).toHaveLength(4);
});
