export function recoveryUI({check,retry}){
 const panel=document.createElement('section');panel.id='action-recovery';panel.hidden=true;panel.setAttribute('aria-label','Восстановление действия');
 panel.innerHTML='<strong>Проверяем сохранение действия</strong><p role="status" aria-live="polite"></p><div class="toolbar"><button data-recovery-check>Проверить результат</button><button data-recovery-retry hidden>Повторить безопасно</button></div>';
 document.getElementById('autosave-note').after(panel);
 panel.querySelector('[data-recovery-check]').onclick=check;panel.querySelector('[data-recovery-retry]').onclick=retry;
 return (pending,{busy=false,missing=false,message=''}={})=>{
  panel.hidden=!pending;if(!pending)return;
  panel.querySelector('p').textContent=message||(busy?'Проверяем, сохранил ли сервер действие…':missing?'Сервер пока не подтвердил действие. Можно повторить ту же команду: второй бросок или повторное списание не произойдут.':'Ответ не получен. Новые действия временно приостановлены, пока не выяснится результат. Проверка продолжится при восстановлении связи.');
  panel.querySelectorAll('button').forEach(b=>b.disabled=busy);
  panel.querySelector('[data-recovery-retry]').hidden=!missing;
 };
}
