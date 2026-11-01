import {test,expect,openCampaign,refresh} from './fixtures.js';

test('Three players share identical dice; penalty dice stay separate and GM secrets stay private',async({clients,server})=>{
  const gmAuth=await server.api('create',{name:'Мастер',title:'Кости'}),pAuth=await server.api('join',{name:'Игрок',code:gmAuth.code,key:gmAuth.playerKey}),oAuth=await server.api('join',{name:'Наблюдатель',code:gmAuth.code,key:gmAuth.playerKey});
  const gm=await clients(),player=await clients(),observer=await clients({viewport:{width:390,height:844}}),pages=[gm,player,observer];
  for(const [page,auth] of [[gm,gmAuth],[player,pAuth],[observer,oAuth]])await openCampaign(page,server,auth,{view:'journal'});
  await expect(player.locator('#dice-visibility')).toBeHidden();await player.locator('#gear').fill('2');await player.locator('#modifier').fill('-4');
  for(const [die,count] of [[8,2],[10,1],[12,1]])await player.locator(`[name=artifact${die}]`).fill(String(count));await player.locator('#roll').click();
  for(const page of pages)await expect(page.locator('#dice-stage')).toHaveAttribute('data-phase','result');
  const id=await player.locator('#dice-stage').getAttribute('data-roll-id');
  const faces=page=>page.locator('#dice-stage .roll-die').evaluateAll(es=>es.map(e=>e.getAttribute('aria-label')));
  for(const page of pages){await expect(page.locator('#dice-stage')).toHaveAttribute('data-roll-id',id);expect(await faces(page)).toEqual(await faces(player));}
  await expect(player.locator('#dice-stage .die-skill')).toHaveCount(2);await expect(player.locator('#dice-stage .die-penalty')).toHaveCount(4);await expect(player.locator('#dice-stage .roll-die')).toHaveCount(15);
  expect(await observer.locator('#dice-stage').evaluate(e=>e.scrollWidth<=e.clientWidth)).toBe(true);
  for(const page of pages)await page.locator('#dice-stage [data-dismiss]').click();
  await gm.locator('.campaign-menu > summary').click();await gm.locator('#dice-visibility').selectOption('hidden');await gm.locator('.campaign-menu > summary').click();await gm.locator('#roll').click();await expect(gm.locator('#dice-stage')).toHaveAttribute('data-private','true');
  const hiddenId=await gm.locator('#dice-stage').getAttribute('data-roll-id');
  for(const [page,auth] of [[player,pAuth],[observer,oAuth]]){await refresh(page);await expect(page.locator('#dice-stage')).toBeHidden();const state=await server.api('state',undefined,auth);expect(JSON.stringify(state)).not.toContain(hiddenId);expect(state.diceRolls).toHaveLength(1);}
  await player.reload();await expect(player.locator('#table')).toBeVisible();await expect(player.locator('#dice-stage')).toBeHidden();await player.locator('#dice-last').click();await expect(player.locator('#dice-stage')).toHaveAttribute('data-roll-id',id);
});

test('GM audio panel sends one public cue, previews locally and respects player mute',async({clients,server})=>{
  const master=await server.api('create',{name:'Мастер',title:'Атмосфера'}),listener=await server.api('join',{name:'Игрок',code:master.code,key:master.playerKey}),quiet=await server.api('join',{name:'Тишина',code:master.code,key:master.playerKey});
  await server.api('action',{action:'audioDirector',op:'ambient',version:0,ambient:'cave'},master);await server.api('action',{action:'audioDirector',op:'cue',cue:'bell'},master);
  const gm=await clients(),player=await clients(),muted=await clients();
  for(const [page,auth,isMuted] of [[gm,master,false],[player,listener,false],[muted,quiet,true]]){
    await openCampaign(page,server,auth,{muted:isMuted});await page.locator('header h1').click();
    if(!isMuted)await expect.poll(()=>page.evaluate(()=>window.ZZAudio?.getState().ambient)).toBe('cave');
    expect(await page.evaluate(()=>window.testAudioCues)).toEqual([]);
  }
  await expect(player.locator('[data-audio-open]')).toBeHidden();await gm.locator('[data-audio-open]').click();await gm.locator('[name=audio-ambient][value=tavern]').check();await gm.locator('[data-audio-ambient-apply]').click();
  await expect(gm.locator('[data-audio-feedback]')).toContainText('сохранена');await refresh(player);await expect.poll(()=>player.evaluate(()=>window.ZZAudio.getState().ambient)).toBe('tavern');
  await gm.locator('[data-audio-tab=cues]').click();await gm.locator('[name=audio-cue]').selectOption('thunder');const before=(await server.api('state',undefined,master)).audioDirector;
  await gm.locator('[data-audio-cue-preview]').click();await expect.poll(()=>gm.evaluate(()=>window.testAudioCues.some(c=>c.preview&&c.type==='thunder'))).toBe(true);const afterPreview=(await server.api('state',undefined,master)).audioDirector;expect(afterPreview.version).toBe(before.version);expect(afterPreview.ambient).toBe(before.ambient);expect(afterPreview.cues.every(c=>before.cues.some(old=>old.id===c.id))).toBe(true);expect(await player.evaluate(()=>window.testAudioCues)).toEqual([]);
  const sent=gm.waitForRequest(r=>r.url().endsWith('/api/action')&&r.postDataJSON()?.action==='audioDirector'&&r.postDataJSON()?.op==='cue');await gm.locator('[data-audio-cue-send]').click();const command=(await sent).postDataJSON();await expect(gm.locator('[data-audio-feedback]')).toContainText('отправлен');
  const state=await server.api('state',undefined,master),id='director:'+state.audioDirector.cues.at(-1).id;
  for(const page of [gm,player]){await refresh(page);await expect.poll(()=>page.evaluate(id=>window.testAudioCues.filter(c=>c.id===id).length,id)).toBe(1);}
  await refresh(muted);await server.api('action',command,master);await Promise.all([gm,player,muted].map(refresh));
  for(const page of [gm,player])expect(await page.evaluate(id=>window.testAudioCues.filter(c=>c.id===id).length,id)).toBe(1);expect(await muted.evaluate(()=>window.testAudioCues)).toEqual([]);
  await server.api('action',{action:'audioDirector',op:'cue',cue:'wolf'},listener,403);
  await player.reload();await expect(player.locator('#table')).toBeVisible();await player.locator('header h1').click();expect(await player.evaluate(()=>window.testAudioCues)).toEqual([]);
});

test('Isolated server restart preserves campaign and ambience; resume keeps the same owner',async({clients,server})=>{
  const master=await server.api('create',{name:'Мастер',title:'Сохранённая экспедиция'});
  const before=await server.api('action',{action:'audioDirector',op:'ambient',version:0,ambient:'rain'},master);
  await server.restart();const auth=await server.api('resume',{code:master.code,resume:master.resume});const after=await server.api('state',undefined,auth);
  expect(after.me.owner).toBe(before.me.owner);expect(after.id).toBe(before.id);expect(after.audioDirector.ambient).toBe('rain');
  const page=await clients();await openCampaign(page,server,auth);await expect(page.locator('#campaign')).toHaveText('Сохранённая экспедиция');
});
