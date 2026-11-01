import {readFile} from 'node:fs/promises';
import {test,expect,openCampaign} from './fixtures.js';

test('Location editor rotates, moves and undoes; published map and SVG reach the player',async({clients,server},testInfo)=>{
  const master=await server.api('create',{name:'Мастер',title:'Вороний брод'}),auth=await server.api('join',{name:'Игрок',code:master.code,key:master.playerKey});
  let map=(await server.api('action',{action:'locationMapGenerate',title:'Вороний брод',settings:{kind:'settlement',seed:'portable-map-e2e',size:'small'}},master)).locationMaps[0];
  const gm=await clients(),player=await clients({viewport:{width:390,height:844}});await openCampaign(gm,server,master,{view:'locations'});await openCampaign(player,server,auth,{view:'locations'});
  await gm.locator('[data-location-library]').selectOption(map.id);await expect(gm.locator('[data-location-canvas] > svg')).toBeVisible();
  const latest=async()=>(await server.api('state',undefined,master)).locationMaps[0];
  async function saved(){const old=map.version;await expect.poll(async()=>(await latest()).version).toBeGreaterThan(old);map=await latest();}
  const viewport=gm.locator('.location-viewport');
  const point=(x,y)=>gm.locator('[data-location-canvas] > svg').evaluate((svg,[x,y])=>{const p=new DOMPoint(x,y).matrixTransform(svg.getScreenCTM());return {x:p.x,y:p.y};},[x,y]);
  async function click(x,y){await viewport.scrollIntoViewIfNeeded();const p=await point(x,y);await gm.mouse.click(p.x,p.y);}
  await gm.locator('[data-plan-tool=add]').click();await gm.locator('[data-plan-art]').selectOption('bridge');await click(300,300);await saved();const feature=map.features.at(-1),original=structuredClone(feature);
  await gm.locator('[data-plan-tool=rotate]').click();await click(300,300);await gm.locator('[data-plan-angle]').fill('90');await gm.locator('[data-plan-apply]').click();await saved();expect(map.features.at(-1).rotation).toBe(90);
  await expect(gm.locator(`[data-location-feature="${feature.id}"] [transform="rotate(90 300 300)"]`)).toHaveCount(1);
  await gm.locator('[data-plan-tool=move]').click();await viewport.scrollIntoViewIfNeeded();const a=await point(300,300),b=await point(360,360);await gm.mouse.move(a.x,a.y);await gm.mouse.down();await gm.mouse.move(b.x,b.y,{steps:6});await gm.mouse.up();await saved();expect(map.features.at(-1).x).toBeGreaterThan(original.x);expect(map.features.at(-1).rotation).toBe(90);
  await gm.locator('[data-plan-undo]').click();await saved();expect(map.features.at(-1).x).toBe(original.x);
  await gm.locator('[data-plan-tool=road]').click();await click(100,420);await click(300,420);await click(300,480);await viewport.focus();await gm.keyboard.press('Control+z');await expect(gm.locator('[data-plan-count]')).toHaveText('Точек: 2 / 100');await gm.locator('[data-plan-finish]').click();await saved();expect(map.paths.at(-1).points).toEqual([[100,420],[300,420]]);
  await gm.locator('[data-plan-tool=inspect]').click();await gm.locator('[data-location-reveal]').click();await saved();await expect(player.locator(`[data-location-library] option[value="${map.id}"]`)).toBeAttached();await player.locator('[data-location-library]').selectOption(map.id);
  await expect(player.locator(`[data-location-feature="${feature.id}"] [transform="rotate(90 300 300)"]`)).toHaveCount(1);
  const publicState=await server.api('state',undefined,auth);expect(publicState.locationHistory).toBeUndefined();expect(publicState.locationMaps[0].undoCount).toBeUndefined();
  const download=gm.waitForEvent('download');await gm.locator('[data-location-svg]').click();const file=testInfo.outputPath('location.svg');await (await download).saveAs(file);expect(await readFile(file,'utf8')).toContain('rotate(90 300 300)');
  expect(await player.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1)).toBe(true);await player.screenshot({path:testInfo.outputPath('location-mobile.png')});
});
