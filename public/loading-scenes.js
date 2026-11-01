/** Original lightweight loading landscapes. Explicit transitions only, never polling. */
export const loadingThemes=Object.freeze({
 journey:{name:'Дороги Запретных Земель',detail:'Лесные тропы, дальние перевалы и ещё не открытые места.'},
 settlement:{name:'Огни поселения',detail:'За стенами ждут жители, ремесленные мастерские и новые истории.'},
 ruins:{name:'Следы забытых времён',detail:'Старые стены хранят то, о чём давно перестали говорить.'},
 battle:{name:'Перед схваткой',detail:'Отряд собирается у костра. Скоро каждый сделает свой ход.'},
 magic:{name:'На границе незримого',detail:'Древние знаки проступают в тишине между мирами.'},
 characters:{name:'Привал у дороги',detail:'Каждое приключение начинается с тех, кто идёт рядом.'}
});
export function themeFor(context={}){
 if(context&&typeof context==='object'&&Object.hasOwn(loadingThemes,context.theme))return context.theme;
 const input=typeof context==='string'?context:context&&typeof context==='object'?[context.theme,context.section,context.url].filter(Boolean).join(' '):'';
 const text=String(input).toLowerCase();
 if(/magic|arcane|spell|маг/.test(text))return 'magic';
 if(/ruin|dungeon|explor|руин|подзем|исслед/.test(text))return 'ruins';
 if(/battle|combat|бой|схват/.test(text))return 'battle';
 if(/settlement|town|stronghold|citadel|location|поселен|город|цитад|локац/.test(text))return 'settlement';
 if(/journey|world|map|index\.html(?:[?#]|$)|путеше|карт/.test(text)&&!/\/tools\/index\.html/.test(text))return 'journey';
 if(/character|account|camp|\/tools\/|персона|кабинет/.test(text))return 'characters';
 return 'characters';
}

let installed=null;
export function installLoadingScenes(){
 if(installed)return installed;
 const style=document.createElement('link');style.rel='stylesheet';style.href=new URL('./loading-scenes.css',import.meta.url).href;document.head.append(style);
 const element=document.createElement('section');element.id='zz-loading-scene';element.className='zz-loading-scene';element.hidden=true;element.tabIndex=-1;element.setAttribute('role','region');element.setAttribute('aria-label','Загрузка игрового стола');
 element.innerHTML='<img class="zz-loading-art" alt="" decoding="async"><div class="zz-loading-shade"></div><div class="zz-loading-content"><span class="zz-loading-eyebrow">ЗАПРЕТНЫЕ ЗЕМЛИ</span><p class="zz-loading-place"></p><h2 class="zz-loading-title"></h2><p class="zz-loading-detail"></p><div class="zz-loading-progress" role="status" aria-live="polite"><span class="zz-loading-spinner" aria-hidden="true"></span><span class="zz-loading-status">Загружаем…</span></div><div class="zz-loading-actions" hidden><button type="button" data-load-retry>Повторить</button><button type="button" data-load-home>В личный кабинет</button><button type="button" data-load-dismiss>Скрыть сообщение</button></div><p class="zz-loading-footnote">Один стол. Общая история.</p></div>';
 document.body.append(element);
 const select=selector=>element.querySelector(selector),art=select('.zz-loading-art'),title=select('.zz-loading-title'),detail=select('.zz-loading-detail'),actions=select('.zz-loading-actions');
 let serial=0,current=0,displayTimer=null,timeoutTimer=null,restoreFocus=null,displayReady=false,styleReady=false;
 function showElement(){if(!current||!displayReady||!styleReady)return;element.hidden=false;if(!document.querySelector('dialog[open]')){if(!element.contains(document.activeElement))restoreFocus=document.activeElement;element.focus({preventScroll:true});}}
 style.addEventListener('load',()=>{styleReady=true;showElement();},{once:true});
 style.addEventListener('error',()=>{styleReady=false;hide();},{once:true});
 function clearTimers(){clearTimeout(displayTimer);clearTimeout(timeoutTimer);displayTimer=timeoutTimer=null;}
 function show(context={}){
  const options=typeof context==='string'?{section:context}:context&&typeof context==='object'?context:{};const theme=themeFor(options),copy=loadingThemes[theme];
  clearTimers();current=++serial;displayReady=false;element.dataset.theme=theme;element.dataset.failed='false';element.setAttribute('aria-busy','true');
  art.src=new URL(`./assets/loading/${theme}.svg`,import.meta.url).href;select('.zz-loading-place').textContent=copy.name;title.textContent=typeof options.title==='string'?options.title.slice(0,160):'Открываем игровой стол';detail.textContent=copy.detail;select('.zz-loading-status').textContent='Загружаем…';actions.hidden=true;
  const token=current;displayTimer=setTimeout(()=>{displayReady=true;showElement();},150);timeoutTimer=setTimeout(()=>{if(current===token)fail('Сервер отвечает дольше обычного. Проверьте соединение, повторите загрузку или вернитесь в кабинет.');},20000);return token;
 }
 function hide(token){if(token!==undefined&&token!==current)return;const hadFocus=element.contains(document.activeElement);clearTimers();current=0;displayReady=false;element.hidden=true;element.setAttribute('aria-busy','false');if(hadFocus&&restoreFocus?.isConnected)restoreFocus.focus({preventScroll:true});restoreFocus=null;}
 function fail(message){
  if(!current)show({url:location.href});clearTimers();displayReady=true;element.dataset.failed='true';element.setAttribute('aria-busy','false');title.textContent='Не удалось закончить загрузку';detail.textContent=typeof message==='string'?message.slice(0,500):'Проверьте соединение и попробуйте ещё раз.';select('.zz-loading-status').textContent='Загрузка не завершена';actions.hidden=false;showElement();
 }
 select('[data-load-retry]').onclick=()=>location.reload();select('[data-load-home]').onclick=()=>location.assign(new URL('/',location.href).href);select('[data-load-dismiss]').onclick=()=>hide();
 element.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();hide();return;}if(event.key!=='Tab')return;const focusable=[...actions.querySelectorAll('button')].filter(button=>!actions.hidden&&!button.disabled);if(!focusable.length){event.preventDefault();element.focus();return;}const first=focusable[0],last=focusable.at(-1);if(event.shiftKey&&(document.activeElement===first||document.activeElement===element)){event.preventDefault();last.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}});
 window.addEventListener('pageshow',event=>{if(event.persisted)hide();});
 installed=Object.freeze({show,hide,fail,themeFor});window.ZZLoading=installed;
 if(window.top===window&&document.readyState!=='complete'){const token=show({url:location.href});window.addEventListener('load',()=>hide(token),{once:true});}
 return installed;
}
