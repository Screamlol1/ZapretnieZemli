import {test,expect,register,editorReady,openCampaign} from './fixtures.js';

test('Account registration, password visibility and saved character editing',async({page,server})=>{
  await page.goto(server.url);await page.getByRole('button',{name:'Регистрация',exact:true}).click();
  const password=page.getByLabel('Пароль',{exact:true});await password.fill('e2e isolated account password 42');
  await page.getByRole('button',{name:'Показать пароль',exact:true}).click();await expect(password).toHaveAttribute('type','text');
  await page.getByRole('button',{name:'Скрыть пароль',exact:true}).click();await expect(password).toHaveAttribute('type','password');
  await page.getByLabel('Логин',{exact:true}).fill('account.e2e');await page.getByLabel('Имя за столом',{exact:true}).fill('Игрок');
  await page.getByRole('button',{name:'Создать аккаунт',exact:true}).click();await page.getByRole('button',{name:'Код сохранён · продолжить',exact:true}).click();
  await page.getByRole('button',{name:/Мои персонажи/}).click();await page.locator('#new-account-character').click();
  let editor=await editorReady(page,'#account-editor iframe');await editor.locator('#name').fill('Астрид Вересковая');await editor.locator('#notes').fill('Запись после первой встречи.');
  await expect.poll(()=>page.evaluate(()=>window.zzHasUnsavedChanges())).toBe(true);
  page.once('dialog',dialog=>dialog.dismiss());await page.locator('#close-account-editor').click();await expect(page.locator('#account-editor')).toBeVisible();
  await editor.locator('.campaign-save').click();await expect(page.locator('#account-editor')).toBeHidden();await expect(page.locator('#hero-list')).toContainText('Астрид Вересковая');
  await expect.poll(()=>page.evaluate(()=>window.zzHasUnsavedChanges())).toBe(false);
  await page.reload();await page.getByRole('button',{name:/Мои персонажи/}).click();await page.getByRole('button',{name:'Открыть лист',exact:true}).click();
  await expect(page.locator('#account-dialog')).toContainText('Запись после первой встречи.');await page.getByRole('button',{name:'Открыть полный лист и редактировать',exact:true}).click();
  editor=await editorReady(page,'#account-editor iframe');await expect(editor.locator('#name')).toHaveValue('Астрид Вересковая');await expect(editor.locator('#notes')).toHaveValue('Запись после первой встречи.');
  await page.locator('#close-account-editor').click();expect(page.context().pages()).toHaveLength(1);
});

test('Campaign creator saves through its iframe and a player keeps ownership',async({clients,server})=>{
  const master=await server.api('create',{name:'Мастер',title:'Приключение'});
  const player=await server.api('join',{name:'Игрок',code:master.code,key:master.playerKey});
  const gm=await clients(),pc=await clients();await openCampaign(gm,server,master);await openCampaign(pc,server,player);
  await pc.locator('[data-create-character]').first().click();let editor=await editorReady(pc,'.character-creator iframe');await editor.locator('#name').fill('Герой отряда');await editor.locator('.campaign-save').click();
  await expect(pc.locator('.character-creator')).toBeHidden();await expect(pc.locator('#characters')).toContainText('Герой отряда');
  await gm.locator('[data-view=crew]').click();await expect(gm.locator('#characters')).toContainText('Герой отряда');
  const state=await server.api('state',undefined,player);expect(state.characters[0].owner).toBe(state.me.owner);
  await pc.locator('#characters [data-edit]').click();editor=await editorReady(pc,'.character-creator iframe');await editor.locator('#notes').fill('Не сохранять');pc.once('dialog',dialog=>dialog.accept());await pc.locator('[data-close-creator]').click();
  await pc.locator('#characters [data-edit]').click();editor=await editorReady(pc,'.character-creator iframe');await expect(editor.locator('#notes')).toHaveValue('');await pc.locator('[data-close-creator]').click();
  expect(pc.context().pages()).toHaveLength(1);expect(gm.context().pages()).toHaveLength(1);
});

test('Standalone character draft restores explicitly and battle stays in one page',async({page,server})=>{
  await page.goto(server.url+'tools/index.html');await expect(page.locator('body:not([inert])')).toBeVisible();await page.locator('#name').fill('Дорожный черновик');
  await page.locator('.battle-link').click();const battle=page.frameLocator('.in-app-tool iframe');await battle.locator('#start').click();await expect(battle.locator('#setup-panel')).toBeHidden();
  await page.locator('.in-app-tool [data-close-tool]').click();await expect(page.locator('#name')).toHaveValue('Дорожный черновик');await page.locator('.battle-link').click();await expect(battle.locator('#setup-panel')).toBeHidden();await battle.locator('header a').click();
  expect(page.context().pages()).toHaveLength(1);await expect.poll(()=>page.evaluate(()=>localStorage.getItem('zz-character-draft-v1'))).toContain('Дорожный черновик');
  page.once('dialog',dialog=>dialog.accept());await page.reload();await expect(page.locator('[data-restore-draft]')).toBeVisible();await expect(page.locator('#name')).toHaveValue('');await page.locator('[data-restore-draft]').click();await expect(page.locator('#name')).toHaveValue('Дорожный черновик');
});

test('390px account, settings and character editor stay inside the viewport',async({page,server},testInfo)=>{
  await page.setViewportSize({width:390,height:844});await register(page,server,'mobile.e2e','Астрид');
  const noOverflow=()=>expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth+1)).toBe(true);
  await noOverflow();await page.locator('[data-interface-settings]').click();const settings=page.locator('#interface-settings-dialog');await expect(settings).toBeVisible();
  expect(await settings.evaluate(e=>e.scrollWidth<=e.clientWidth)).toBe(true);const box=await settings.boundingBox();expect(box.x).toBeGreaterThanOrEqual(0);expect(box.x+box.width).toBeLessThanOrEqual(391);
  await page.screenshot({path:testInfo.outputPath('mobile-settings.png')});await page.keyboard.press('Escape');
  await page.getByRole('button',{name:/Мои персонажи/}).click();await page.locator('#new-account-character').click();const editor=await editorReady(page,'#account-editor iframe');
  await editor.locator('#name').fill('Мобильный герой');await editor.locator('.campaign-save').click();await expect(page.locator('#account-editor')).toBeHidden();await noOverflow();
  await page.screenshot({path:testInfo.outputPath('mobile-characters.png')});
});
