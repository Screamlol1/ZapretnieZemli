import {trackUnsaved,navigationStyles} from '../in-app-navigation.js';
const KEY='zz-character-draft-v1';
export function sheetDraft({get,restore,validate,embedded}){
 let baseline=JSON.stringify(get()),pending=null,timer,notice,status;
 const dirty=()=>JSON.stringify(get())!==baseline;
 trackUnsaved(dirty);
 if(!embedded){
  navigationStyles();
  status=document.createElement('small');status.className='sheet-draft-status';status.setAttribute('role','status');document.querySelector('header').after(status);
  try{const raw=localStorage.getItem(KEY);if(raw&&raw.length<150000){const saved=JSON.parse(raw);if(saved.version===1&&Number.isFinite(saved.updated)){pending={...saved,sheet:validate(saved.sheet)};}}}catch{}
  if(pending){
   notice=document.createElement('section');notice.className='sheet-draft-recovery';notice.setAttribute('aria-label','Восстановление черновика');notice.innerHTML='<p><strong>Есть локальный черновик</strong><small></small></p><button type="button" data-restore-draft>Восстановить</button><button type="button" data-remove-draft>Удалить черновик</button>';
   notice.querySelector('small').textContent=(pending.sheet.name||'Без имени')+' · '+new Date(pending.updated).toLocaleString('ru-RU');status.before(notice);
   notice.querySelector('[data-restore-draft]').onclick=()=>{if(dirty()&&!confirm('Восстановить черновик вместо текущего листа?'))return;const sheet=pending.sheet;pending=null;notice.remove();restore(sheet);changed();};
   notice.querySelector('[data-remove-draft]').onclick=()=>{if(!confirm('Удалить сохранённый на этом устройстве черновик?'))return;pending=null;notice.remove();try{localStorage.removeItem(KEY);}catch{}changed();};
  }
 }
 function write(){
  if(embedded||pending||!dirty())return;
  try{const value=JSON.stringify({version:1,updated:Date.now(),sheet:get()});if(value.length>150000)throw Error('large');localStorage.setItem(KEY,value);status.textContent='Черновик сохранён на этом устройстве. Для переноса скачайте файл.';status.dataset.error='false';}
  catch{status.textContent='Не удалось сохранить черновик на устройстве. Скачайте лист в файл.';status.dataset.error='true';}
 }
 function changed(){if(embedded)return;clearTimeout(timer);timer=setTimeout(write,350);}
 function loaded(){baseline=JSON.stringify(get());}
 function saved(){if(embedded){loaded();return;}clearTimeout(timer);write();loaded();status.textContent='Лист отправлен на скачивание. Локальный черновик сохранён на случай отмены загрузки.';}
 document.addEventListener('input',changed);document.addEventListener('change',changed);window.addEventListener('pagehide',write);
 return {changed,loaded,saved,dirty};
}
