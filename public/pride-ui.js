import {escapeIdentity as esc} from './player-identity.js';
const drafts=new Map();
export function pridePanel(c,s,r){
 if(c?.kind!=='pc')return '';
 const status=c.runtime.pride||{},request=c.runtime.prideRequest,gm=s.me.role==='gm',session=s.journey.session;
 let body=`<p>${esc(c.sheet.pride||'Гордость ещё не указана в листе.')}</p><small>Один D12 после провала обычной проверки, в том числе после риска. Мастер подтверждает связь с гордостью. Если итог снова неудачен, гордость теряется.</small>`;
 if(status.lost){const remaining=Math.max(0,status.lostSession+2-session);body=`<p>Гордость потеряна: ${esc(status.lostText)}</p>${remaining?`<p>Следующую полную встречу нужно сыграть без гордости. Новую можно выбрать со встречи ${status.lostSession+2}; сейчас ${session}.</p>`:`<form data-pride-replace><label>Новая гордость<input name="text" maxlength="500" required value="${esc(drafts.get(c.id+':replace')||'')}"></label><button>Сохранить новую гордость</button></form>`}`;}
 else if(request)body+=`<p>${esc(request.note)}</p><p>${!request.current?'Проверка или герой изменились. Отмените устаревший запрос.':request.status==='approved'?'Мастер подтвердил. Можно бросить D12; это завершит проверку.':'Ожидается решение Мастера.'}</p><div class="toolbar">${request.current&&request.status==='requested'&&gm?'<button data-pride-op="approve">Подтвердить применимость</button><button data-pride-op="reject">Отклонить</button>':''}${request.current&&request.status==='approved'?'<button class="primary-action" data-pride-op="roll">Использовать гордость · D12</button>':''}<button data-pride-op="cancel">Отменить запрос</button></div>`;
 else if(status.usedSession===session)body+='<p>Уже использована в этой встрече.</p>';
 else if(r?.prideAvailable)body+=`<form data-pride-request><label>Почему гордость помогает<input name="note" maxlength="500" required value="${esc(drafts.get(c.id+':request')||'')}"></label><button>Запросить применение гордости</button></form>`;
 else body+='<p class="muted">Запрос появится после незавершённой неудачной обычной проверки. Боевые, дорожные и встречные проверки пока разрешаются отдельно Мастером.</p>';
 return `<details class="pride-controls" ${request||status.lost?'open':''}><summary>Гордость${request?' · ожидается решение':status.lost?' · потеряна':status.usedSession===session?' · использована':''}</summary>${body}<p data-pride-error class="editor-error" role="alert"></p></details>`;
}
export function bindPride(root,getState,send,selected){
 const character=()=>getState().characters.find(c=>c.id===selected());
 const run=async data=>{const c=character(),request=c?.runtime.prideRequest;const ok=await send({action:'characterPride',character:c.id,roll:request?.roll,request:request?.id,...data});if(!ok){const box=root.querySelector('[data-pride-error]');if(box)box.textContent=document.getElementById('error')?.textContent||'Не удалось сохранить.';}return ok;};
 root.addEventListener('input',e=>{const f=e.target.closest('[data-pride-request],[data-pride-replace]');if(f)drafts.set(selected()+':'+(f.hasAttribute('data-pride-request')?'request':'replace'),e.target.value);});
 root.addEventListener('submit',async e=>{if(!e.target.matches('[data-pride-request],[data-pride-replace]'))return;e.preventDefault();const f=e.target,c=character(),s=getState(),r=s.me.role==='gm'&&s.gmChecks?.[c.id]&&(!c.runtime.lastCheck||s.gmChecks[c.id].time>(c.runtime.lastCheck.time||0))?s.gmChecks[c.id]:c.runtime.lastCheck;const data=Object.fromEntries(new FormData(f));const op=f.hasAttribute('data-pride-request')?'request':'replace';if(await run({op,...data,roll:r?.id,lostSession:c.runtime.pride?.lostSession}))drafts.delete(c.id+':'+op);});
 root.addEventListener('click',e=>{const b=e.target.closest('[data-pride-op]');if(b)run({op:b.dataset.prideOp});});
}
