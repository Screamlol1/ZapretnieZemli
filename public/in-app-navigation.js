// Same-window tools and a read-only dirty-state hook for browsers and desktop.
const checks=new Set();
let leaving=false,toolDialog=null,toolFrame=null;
function children(){return [...document.querySelectorAll('iframe')].flatMap(frame=>{try{return frame.contentWindow?.location.origin===location.origin?[frame.contentWindow]:[];}catch{return [];}});}
export function hasUnsavedChanges(){
 if(leaving)return false;
 for(const check of checks)try{if(check())return true;}catch{}
 return children().some(child=>{try{return child.zzHasUnsavedChanges?.()===true;}catch{return false;}});
}
window.zzHasUnsavedChanges=hasUnsavedChanges;
window.zzAcceptNavigation=()=>{leaving=true;for(const child of children())try{child.zzAcceptNavigation?.();}catch{}};
window.addEventListener('beforeunload',event=>{if(hasUnsavedChanges()){event.preventDefault();event.returnValue='';}});
export function trackUnsaved(check){checks.add(check);return ()=>checks.delete(check);}
export function allowFrameLeave(frame){try{frame?.contentWindow?.zzAcceptNavigation?.();}catch{}}
export function loadToolFrame(frame,source){
 const destination=new URL(source,location.href);destination.searchParams.set('_editor',crypto.randomUUID());const target=destination.href;
 frame.style.visibility='hidden';frame.setAttribute('aria-busy','true');
 frame.onload=()=>{try{if(frame.contentWindow.location.href!==target)return;}catch{return;}frame.style.visibility='';frame.removeAttribute('aria-busy');};
 frame.src=target;
}
export function confirmFrameClose(frame){
 let dirty=false;try{dirty=frame?.contentWindow?.zzHasUnsavedChanges?.()===true;}catch{}
 if(dirty&&!confirm('Закрыть редактор? Несохранённые изменения будут потеряны.'))return false;
 allowFrameLeave(frame);return true;
}
export function navigationStyles(){
 if(document.querySelector('link[data-in-app-navigation]'))return;
 const link=document.createElement('link');link.rel='stylesheet';link.href=new URL('./in-app-navigation.css',import.meta.url).href;link.dataset.inAppNavigation='';document.head.append(link);
}
export function openBattleTool(){
 navigationStyles();
 if(!toolDialog){
  toolDialog=document.createElement('dialog');toolDialog.className='in-app-tool';toolDialog.setAttribute('aria-label','Боевая песочница');
  toolDialog.innerHTML='<div class="in-app-tool-bar"><div><strong>Боевая песочница</strong><small>Отдельный тренировочный бой · состояние сохраняется, пока открыта эта страница</small></div><button type="button" data-close-tool>Вернуться</button></div><iframe title="Боевая песочница" src="/tools/battle.html?embedded=1"></iframe>';
  document.body.append(toolDialog);toolFrame=toolDialog.querySelector('iframe');
  toolDialog.querySelector('[data-close-tool]').onclick=()=>toolDialog.close();
  // Keep the iframe alive: returning to the sheet never discards a practice battle.
  window.addEventListener('message',event=>{if(event.origin===location.origin&&event.source===toolFrame.contentWindow&&event.data?.type==='zz-tool-close')toolDialog.close();});
 }
 toolDialog.showModal();
}
export function bindBattleLinks(){
 document.addEventListener('click',event=>{
  const link=event.target.closest?.('a[href]');if(!link||event.button||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;
  const url=new URL(link.href,location.href);if(url.origin!==location.origin||url.pathname!=='/tools/battle.html')return;
  event.preventDefault();openBattleTool();
 });
}
