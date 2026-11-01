import {paintSprites,spriteURL} from './appearance.js';
const timers=new WeakMap();
export function appearanceEvents(before,after){
 const events={},oldTokens=new Map((before.locationMaps||[]).flatMap(m=>(m.tokens||[]).map(t=>[t.characterId,{...t,map:m.id}])));
 for(const m of after.locationMaps||[])for(const t of m.tokens||[]){const old=oldTokens.get(t.characterId);if(old&&(old.map!==m.id||old.x!==t.x||old.y!==t.y))events[t.characterId]={pose:'walk',direction:t.x<old.x?'left':'right'};}
 for(const c of after.characters||[]){const old=before.characters?.find(o=>o.id===c.id);if(old?.runtime?.current?.str>0&&c.runtime?.current?.str===0)events[c.id]={pose:'fall'};}
 for(const cast of after.magicCastings||[]){const old=before.magicCastings?.find(c=>c.id===cast.id);if(cast.power!==undefined&&old?.power===undefined&&cast.status!=='cancelled')events[cast.character]={pose:'cast'};}
 return events;
}
export function playAppearanceChanges(before,after){
 if(!before||before.revision===after.revision)return;
 const events=appearanceEvents(before,after);
 for(const id of Object.keys(events)){
  const images=[...document.querySelectorAll(`[data-sprite="${CSS.escape(id)}"]`)].filter(e=>!e.closest('#online-combat'));
  for(const img of images){clearTimeout(timers.get(img));paintSprites({querySelectorAll:()=>[img]},after.characters,events,after.items);timers.set(img,setTimeout(()=>{if(img.isConnected)paintSprites({querySelectorAll:()=>[img]},after.characters,events[id].pose==='fall'?{[id]:{pose:'fall',animate:false}}:{},after.items);timers.delete(img);},1400));}
  const actor=after.characters.find(c=>c.id===id);if(!actor)continue;
  for(const map of after.locationMaps||[])for(const token of (map.tokens||[]).filter(t=>t.characterId===id))for(const img of document.querySelectorAll(`[data-location-token="${CSS.escape(token.id)}"] image`)){
   clearTimeout(timers.get(img));const revision=String(after.revision);img.dataset.poseRevision=revision;
   spriteURL(actor,events[id],after.items).then(url=>{if(img.isConnected&&img.dataset.poseRevision===revision)img.setAttribute('href',url);}).catch(()=>{});
   timers.set(img,setTimeout(async()=>{if(img.isConnected&&img.dataset.poseRevision===revision)try{img.setAttribute('href',await spriteURL(actor,events[id].pose==='fall'?{pose:'fall',animate:false}:'idle',after.items));}catch{}timers.delete(img);},1400));
  }
 }
}
