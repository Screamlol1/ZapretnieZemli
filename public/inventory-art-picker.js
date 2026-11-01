import {itemArt,itemPicture,escapeItem as esc} from './inventory-art.js';

// Build the atlas gallery only when opened, keeping ordinary item dialogs light.
export function bindArtPicker(dialog,previewSelector,{open=false}={}){
 const select=dialog.querySelector('[name=art]'),preview=dialog.querySelector(previewSelector);if(!select||!preview)return;
 const details=document.createElement('details');details.className='inventory-art-picker';details.innerHTML='<summary>Выбрать по картинке</summary>';preview.after(details);
 const render=()=>{if(details.querySelector('[data-art-search]'))return;details.insertAdjacentHTML('beforeend',`<label>Найти изображение<input data-art-search type="search" placeholder="Например, молот, фонарь, палатка"></label><div class="inventory-art-gallery">${itemArt.map(([id,name])=>`<button type="button" data-pick-art="${id}" data-art-name="${esc(name.toLowerCase().replaceAll('ё','е'))}" aria-label="Выбрать: ${esc(name)}" aria-pressed="${select.value===id}">${itemPicture(id)}<span>${esc(name)}</span></button>`).join('')}</div><p data-art-empty hidden>Нет подходящих картинок. Попробуйте другое название.</p>`);};
 details.addEventListener('toggle',()=>{if(details.open)render();});
 details.addEventListener('input',e=>{if(!e.target.hasAttribute('data-art-search'))return;const q=e.target.value.trim().toLowerCase().replaceAll('ё','е');let count=0;details.querySelectorAll('[data-pick-art]').forEach(b=>{b.hidden=!b.dataset.artName.includes(q);if(!b.hidden)count++;});details.querySelector('[data-art-empty]').hidden=!!count;});
 details.addEventListener('click',e=>{const b=e.target.closest('[data-pick-art]');if(!b)return;select.value=b.dataset.pickArt;select.dispatchEvent(new Event('change',{bubbles:true}));});
 select.addEventListener('change',()=>details.querySelectorAll('[data-pick-art]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.pickArt===select.value))));
 if(open){details.open=true;render();}
}
