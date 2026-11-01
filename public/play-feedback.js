import {esc} from './location-render.js';
import {itemPicture} from './inventory-art.js';
import {paintSprites} from './appearance.js';
import {playAppearanceChanges} from './appearance-feedback.js';
export function resultChanges(before,after){
 const result=[];for(const c of after.characters||[]){const old=before.characters?.find(x=>x.id===c.id);if(!old?.runtime||!c.runtime)continue;for(const [key,name]of Object.entries({str:'Телосложение',agi:'Ловкость',wit:'Разум',emp:'Эмпатия'})){const a=old.runtime.current?.[key],b=c.runtime.current?.[key];if(Number.isFinite(a)&&Number.isFinite(b)&&a!==b)result.push({kind:b<a?'damage':'heal',character:c.id,title:c.name,text:`${name}: ${a} → ${b} (${b-a>0?'+':''}${b-a})`});}if(old.runtime.wp!==c.runtime.wp&&Number.isFinite(c.runtime.wp))result.push({kind:'will',character:c.id,title:c.name,text:`Сила воли: ${old.runtime.wp} → ${c.runtime.wp}`});for(const [key,name]of Object.entries({food:'Еда',water:'Вода',arrows:'Стрелы',torches:'Факелы'})){const a=old.runtime.resources?.[key],b=c.runtime.resources?.[key];if(a!==undefined&&b!==undefined&&a!==b)result.push({kind:'resource',character:c.id,title:c.name,text:`${name}: ${a} → ${b}`,art:key==='arrows'?'arrows':key==='torches'?'torch':key==='water'?'waterskin':'food'});}}
 for(const i of after.items||[]){const old=before.items?.find(x=>x.id===i.id);if(old&&old.wear!==i.wear&&Number.isFinite(i.wear))result.push({kind:i.wear>(old.wear||0)?'gear':'repair',title:i.name,text:`Износ: ${old.wear||0} → ${i.wear}`,item:i,character:i.location.kind==='character'?i.location.id:null});}
 return result;
}
export function playFeedbackUI(getState){
 let previous=null,history=[],campaign='';
 const preference=localStorage.getItem('zz-reduced-motion');document.documentElement.dataset.reducedMotion=preference??String(matchMedia('(prefers-reduced-motion: reduce)').matches);
 function render(){const s=getState();if(!s)return;if(campaign!==s.id){campaign=s.id;previous=null;history=[];}
  if(previous&&previous.revision!==s.revision){const changes=resultChanges(previous,s),known=new Set(previous.diceRolls?.map(r=>r.id));for(const e of (s.diceRolls||[]).filter(e=>!known.has(e.id)).slice(-4))changes.push({kind:'dice',title:e.name+' · '+e.label,text:e.result,art:/маг|заклин/i.test(e.label)?'gem':/охот|стрел/i.test(e.label)?'bow':/леч/i.test(e.label)?'herbs':'scroll'});history=[...changes,...history].slice(0,12);for(const change of changes){if(!change.character)continue;for(const el of document.querySelectorAll(`[data-character-card="${CSS.escape(change.character)}"],[data-scene-hero="${CSS.escape(change.character)}"]`)){el.dataset.resultKind=change.kind;el.classList.remove('result-flash');requestAnimationFrame(()=>el.classList.add('result-flash'));}for(const m of s.locationMaps||[])for(const t of (m.tokens||[]).filter(t=>t.characterId===change.character)){const el=document.querySelector(`[data-location-token="${CSS.escape(t.id)}"]`);if(el){el.dataset.resultKind=change.kind;el.classList.add('result-flash');}}}}
  if(!previous)history=(s.diceRolls||[]).slice(-3).reverse().map(e=>({kind:'dice',title:e.name+' · '+e.label,text:e.result,art:'scroll'}));
  playAppearanceChanges(previous,s);
  previous=structuredClone({id:s.id,revision:s.revision,characters:s.characters,items:s.items,diceRolls:s.diceRolls,locationMaps:s.locationMaps,magicCastings:s.magicCastings});
  const feed=document.getElementById('scene-feedback-feed');if(!feed)return;feed.innerHTML=history.map(e=>`<article class="result-card" data-kind="${e.kind}"><div class="result-art">${e.character?`<img data-sprite="${esc(e.character)}" alt="">`:itemPicture(e.item||e.art||'pack')}</div><div><small>${({damage:'Повреждение',heal:'Восстановление',will:'Сила воли',resource:'Припасы',gear:'Повреждение предмета',repair:'Ремонт',dice:'Бросок'})[e.kind]}</small><strong>${esc(e.title)}</strong><p>${esc(e.text)}</p></div></article>`).join('')||'<p class="muted">Здесь появятся броски, изменения характеристик, припасов и снаряжения. Полная история остаётся в журнале.</p>';paintSprites(feed,s.characters);
 }
 return {render};
}
