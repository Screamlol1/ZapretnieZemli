import {locationArt,artPreview} from './location-art.js';
import {esc} from './location-render.js';

// Tools operate in SVG world coordinates, independently of scroll and zoom.
export function locationEditor({root,viewport,canvas,current,getState,run,draw,error,canLeave}){
 const panel=document.createElement('div');panel.className='location-editor';panel.dataset.locationEditor='';
 root.querySelector('.location-layout').before(panel);
 panel.innerHTML=`<div class="toolbar" role="group" aria-label="Инструменты плана">${[['inspect','Осмотр / прокрутка'],['move','Переместить'],['add','Добавить объект'],['road','Дорога'],['wall','Стена'],['palisade','Частокол'],['passage','Проход'],['token','Персонаж / чудовище'],['remove','Удалить']].map(([id,label])=>`<button type="button" data-plan-tool="${id}" aria-pressed="${id==='inspect'}">${label}</button>`).join('')}</div><div data-plan-options class="location-fields"><label data-plan-add>Объект<select data-plan-art>${locationArt.map(([id,label])=>`<option value="${id}">${label}</option>`).join('')}</select></label><div data-plan-add data-plan-preview>${artPreview('thatch')}</div><label data-plan-add>Ширина, м<input data-plan-width type="number" value="10" min="0.5" max="100" step="0.5"></label><label data-plan-add>Длина, м<input data-plan-height type="number" value="8" min="0.5" max="100" step="0.5"></label><label data-plan-actor-label>Персонаж кампании<select data-plan-actor></select></label><label data-plan-snap-label><input data-plan-snap type="checkbox" checked> Привязка к сетке и концам линий</label><label data-plan-secret-label><input data-plan-secret type="checkbox"> Скрыть от игроков</label></div><div class="toolbar" data-plan-line><button type="button" data-plan-finish>Сохранить линию</button><button type="button" data-plan-back>Убрать последнюю точку</button><button type="button" data-plan-cancel>Отменить линию</button><span data-plan-count></span></div><p data-plan-help role="status"></p>`;
 const $=s=>panel.querySelector(s),isLine=()=>['road','wall','palisade','passage'].includes(mode);
 let mode='inspect',pts=[],version=0,mapId='',drag=null,pending=false,suppress=false;
 const enabled=()=>getState()?.me.role==='gm'&&!root.querySelector('[data-location-player-view]').checked&&!!current();
 const active=()=>enabled()&&mode!=='inspect';
 const hints={inspect:'Колесо — масштаб. На приближённом плане зажмите ЛКМ для прокрутки. Нажмите здание для описания.',move:'Перетащите здание или жетон. Правка сохраняется при отпускании. Пустое место не перемещает объект.',add:'Выберите иллюстрацию и размеры, затем нажмите место на плане. Добавление сохраняется сразу.',token:'Выберите персонажа или чудовище кампании, затем нажмите план. Для нового существа сначала создайте его в разделе «Персонажи».',remove:'Нажмите здание, линию или жетон, затем подтвердите удаление. Лист персонажа сохранится.'};
 function toolbar(){
  panel.hidden=!enabled();viewport.classList.toggle('location-editing',active());
  for(const b of panel.querySelectorAll('[data-plan-tool]'))b.setAttribute('aria-pressed',String(b.dataset.planTool===mode));
  for(const e of panel.querySelectorAll('[data-plan-add]'))e.hidden=mode!=='add';
  $('[data-plan-actor-label]').hidden=mode!=='token';$('[data-plan-line]').hidden=!isLine();
  $('[data-plan-snap-label]').hidden=['inspect','remove'].includes(mode);
  $('[data-plan-secret-label]').hidden=!['add','token','road','wall','palisade','passage'].includes(mode);
  $('[data-plan-help]').textContent=hints[mode]||'Нажимайте план, чтобы задать точки. Концы линий притягиваются друг к другу. Завершите кнопкой «Сохранить линию» или Enter; Escape отменяет черновик.';
  $('[data-plan-count]').textContent=`Точек: ${pts.length} / 100`;$('[data-plan-finish]').disabled=pts.length<2||pending;
 }
 function clear(){pts=[];version=0;canvas.querySelector('[data-plan-draft]')?.remove();toolbar();}
 function stopDrag(){if(drag){drag.node.removeAttribute('transform');if(viewport.hasPointerCapture(drag.pointer))viewport.releasePointerCapture(drag.pointer);drag=null;}}
 function reset(){stopDrag();mode='inspect';clear();suppress=false;}
 function world(e){const svg=canvas.querySelector(':scope > svg');if(!svg)return null;const p=new DOMPoint(e.clientX,e.clientY).matrixTransform(svg.getScreenCTM().inverse());return [p.x,p.y];}
 function snap(p){const m=current();if(!$('[data-plan-snap]').checked)return p;const grid=m.cellSize/2;let result=p.map(v=>Math.round(v/grid)*grid),distance=12;
  if(isLine())for(const path of m.paths){for(const end of [path.points[0],path.points.at(-1)]){const d=Math.hypot(end[0]-p[0],end[1]-p[1]);if(d<distance){distance=d;result=[...end];}}}
  return result;
 }
 function preview(){canvas.querySelector('[data-plan-draft]')?.remove();if(!pts.length)return;const g=document.createElementNS('http://www.w3.org/2000/svg','g');g.dataset.planDraft='';g.setAttribute('pointer-events','none');g.innerHTML=`<polyline points="${pts.map(p=>p.join(',')).join(' ')}" fill="none" stroke="#bb4328" stroke-width="4" stroke-dasharray="8 4"/>${pts.map(([x,y])=>`<circle cx="${x}" cy="${y}" r="5" fill="#f5da8c" stroke="#963d25"/>`).join('')}`;canvas.querySelector(':scope > svg')?.append(g);toolbar();}
 async function save(data,expected=current()?.version){if(pending)return false;const m=current();if(!m)return false;pending=true;try{return await run({action:'locationMapEdit',id:m.id,version:expected,...data});}finally{pending=false;draw();toolbar();}}
 async function finish(){if(pts.length<2)return;const points=pts.map(p=>[...p]),v=version;await save({op:'path',style:mode,points,secret:$('[data-plan-secret]').checked},v);clear();}
 function hit(e){const node=e.target.closest('[data-location-token],[data-location-feature],[data-location-path]');if(!node)return null;const d=node.dataset;return {node,kind:d.locationToken?'token':d.locationFeature?'feature':'path',target:d.locationToken||d.locationFeature||Number(d.locationPath)};}
 panel.addEventListener('click',async e=>{const b=e.target.closest('button');if(!b||pending)return;
  if(b.dataset.planTool){if(!canLeave())return;if(pts.length&&!confirm('Отменить незавершённую линию?'))return;stopDrag();mode=b.dataset.planTool;clear();error('');}
  if(b.hasAttribute('data-plan-finish'))await finish();
  if(b.hasAttribute('data-plan-back')){pts.pop();preview();toolbar();}
  if(b.hasAttribute('data-plan-cancel'))clear();
 });
 $('[data-plan-art]').addEventListener('change',()=>{const art=$('[data-plan-art]').value;$('[data-plan-preview]').innerHTML=artPreview(art);const dimensions={tent:[3,3],pavilion:[6,6],tower:[8,8],keep:[20,20],well:[2,2],fire:[2,2],supplies:[3,2],gate:[12,5],bridge:[12,4],oak:[8,8],pine:[6,6],rocks:[4,4],room:[10,10],cave:[10,10]};const [w,h]=dimensions[art]||[10,8];$('[data-plan-width]').value=w;$('[data-plan-height]').value=h;});
 viewport.addEventListener('pointerdown',e=>{if(!active()||e.button!==0)return;e.stopImmediatePropagation();if(pending)return;suppress=false;
  if(mode!=='move')return;const found=hit(e);if(!found||found.kind==='path')return;
  const m=current(),f=(found.kind==='feature'?m.features:m.tokens||[]).find(f=>f.id===found.target);if(!f)return;
  e.preventDefault();drag={...found,pointer:e.pointerId,start:world(e),x:f.x,y:f.y,w:f.w||0,h:f.h||0,version:m.version,moved:false};viewport.setPointerCapture(e.pointerId);
 },true);
 viewport.addEventListener('pointermove',e=>{if(!drag||e.pointerId!==drag.pointer)return;e.stopImmediatePropagation();const p=world(e),m=current();let next=snap([drag.x+p[0]-drag.start[0],drag.y+p[1]-drag.start[1]]);next=[Math.max(0,Math.min(m.width-drag.w,next[0])),Math.max(0,Math.min(m.height-drag.h,next[1]))];drag.next=next;drag.moved=drag.moved||Math.hypot(p[0]-drag.start[0],p[1]-drag.start[1])>3;if(drag.moved)drag.node.setAttribute('transform',`translate(${next[0]-drag.x} ${next[1]-drag.y})`);},true);
 viewport.addEventListener('pointerup',async e=>{if(!drag||e.pointerId!==drag.pointer)return;e.stopImmediatePropagation();const d=drag;suppress=d.moved;stopDrag();if(d.moved)await save({op:'move',kind:d.kind,target:d.target,point:d.next},d.version);},true);
 viewport.addEventListener('pointercancel',stopDrag);window.addEventListener('blur',stopDrag);
 viewport.addEventListener('click',async e=>{if(!active())return;e.stopImmediatePropagation();e.preventDefault();if(suppress){suppress=false;return;}if(pending)return;const p=world(e);if(!p)return;
  if(mode==='remove'){const found=hit(e);if(found&&confirm('Удалить выбранный объект с плана? Связанные проходы тоже будут удалены.'))await save({op:'remove',kind:found.kind,target:found.target});return;}
  if(mode==='add'){const art=$('[data-plan-art]').value;await save({op:'add',art,label:locationArt.find(([id])=>id===art)[1],widthMeters:Number($('[data-plan-width]').value),heightMeters:Number($('[data-plan-height]').value),point:snap(p),secret:$('[data-plan-secret]').checked});}
  if(mode==='token')await save({op:'token',characterId:$('[data-plan-actor]').value,point:snap(p),secret:$('[data-plan-secret]').checked});
  if(isLine()){if(pts.length>=100){error('Не более 100 точек. Сохраните линию и начните следующую.');return;}const next=snap(p);if(pts.length&&Math.hypot(next[0]-pts.at(-1)[0],next[1]-pts.at(-1)[1])<1)return;if(!pts.length)version=current().version;pts.push(next);preview();}
 },true);
 root.addEventListener('keydown',e=>{if(!active()||e.target.matches('input,textarea,select'))return;if(e.key==='Escape'){e.preventDefault();stopDrag();clear();}if(e.key==='Enter'&&isLine()&&e.target===viewport){e.preventDefault();finish();}});
 function render(){const m=current();if(mapId!==m?.id){mapId=m?.id;reset();}if(!enabled()&&mode!=='inspect')reset();if(!pending&&((pts.length&&version!==m?.version)||(drag&&drag.version!==m?.version))){stopDrag();clear();error('План изменён в другом окне. Незавершённая правка отменена; повторите её на актуальном плане.');}
  const select=$('[data-plan-actor]'),value=select.value,html='<option value="">Выберите персонажа</option>'+(getState()?.characters||[]).map(c=>`<option value="${esc(c.id)}">${esc(c.name)} · ${c.kind==='monster'?'чудовище':c.kind==='pc'?'игрок':'ПВ'}${c.hidden?' · скрыт':''}${m?.tokens?.some(t=>t.characterId===c.id)?' · уже на плане':''}</option>`).join('');if(select.innerHTML!==html){select.innerHTML=html;select.value=value;}toolbar();preview();
 }
 return {render,reset,active,isDragging:()=>!!drag,canLeave:()=>!pts.length||confirm('Отменить незавершённую линию?')};
}
