import {cultures,cultureAssets} from './location-culture-data.js';
import {locationArt,artPreview} from './location-art.js';
export {cultures,cultureAssets};
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const options=(list,value)=>list.map(([id,label])=>`<option value="${id}" ${value===id?'selected':''}>${esc(label)}</option>`).join('');
export function cultureOptions(value='',filter='all'){
 const general=locationArt.filter(([id])=>!cultureAssets.some(a=>a.id===id));
 return ((filter==='all'||filter==='neutral')?`<optgroup label="Общие объекты">${options(general,value)}</optgroup>`:'')+cultures.filter(c=>filter==='all'||filter===c.id).map(c=>`<optgroup label="${esc(c.label)}">${options(c.assets.map(a=>[a.id,a.label]),value)}</optgroup>`).join('');
}
export function styleFields(){return `<div class="location-fields location-style-fields"><label>Народ / архитектура<select name="culture">${options([['neutral','Общий набор'],['mixed','Смешанное поселение'],...cultures.map(c=>[c.id,c.label])])}</select></label><label>Покрытие земли<select name="ground">${options([['auto','По выбранному набору'],['grass','Луг'],['forest','Лесная почва'],['highland','Камни и скалы'],['marsh','Заболоченная земля'],['ash','Пепелище'],['sand','Песок']])}</select></label><label>Дороги<select name="roadSurface">${options([['auto','По выбранному набору'],['earth','Грунт'],['stone','Каменная кладка'],['planks','Деревянные настилы']])}</select></label></div>`;}
export function stylePreview(id){
 const c=cultures.find(c=>c.id===id);
 if(!c)return `<p class="muted">${id==='mixed'?'Типовые здания получают разные культурные мотивы. Конкретный состав жителей определяет Мастер.':'Общие средневековые постройки. Культурные объекты можно добавлять вручную.'}</p>`;
 return `<div class="location-culture-preview">${c.assets.map(a=>`<figure>${artPreview(a.id)}<figcaption>${esc(a.label)}<small>${a.width} × ${a.height} м при ручном добавлении</small></figcaption></figure>`).join('')}</div><p class="muted">${esc(c.description)} <small>${esc(c.source)} · Авторская визуальная интерпретация; не ограничения для народа.</small></p>`;
}
export function terrainPalette(map){
 const palettes={grass:['#c9c29c','#aaa77b','#dcd3ac'],forest:['#a1ad88','#7d8965','#c3c4a0'],highland:['#b8b4a2','#929687','#d4cbb5'],marsh:['#a3ad91','#7e9586','#c0c4a1'],ash:['#aaa293','#817e70','#c9bc9e'],sand:['#d7c39a','#bca77d','#ebd9b3']};
 return palettes[map.ground]||['#d8cba8','#baa880','#eadfc0'];
}
