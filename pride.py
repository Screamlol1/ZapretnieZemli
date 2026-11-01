"""PHB 34, 50–51: Pride for ordinary character checks, with GM relevance review."""
import secrets
from dice_events import publish, pools
from inventory_rules import character, editable, text
from equipment_rules import owned


def die():return secrets.randbelow(12)+1


def check(room,c,roll,gm):
    from skill_checks import signature
    r=c['runtime'].get('lastCheck')
    hidden=room.get('gmChecks',{}).get(c['id']) if gm else None
    if hidden and hidden['id']==roll:r=hidden
    if not r or r['id']!=roll or r.get('accepted') or r.get('opposed') or r.get('pride'):
        raise ValueError('Нужна незавершённая обычная проверка без уже использованной гордости.')
    item=next((i for i in owned(room,c['id']) if i['id']==r.get('item')),None)
    if r.get('signature')!=signature(c,item) or r.get('item') and not item:
        raise ValueError('Герой или предмет изменились после броска. Эта проверка устарела.')
    if r['hits']>0:raise ValueError('Гордость используется после провала проверки.')
    return r,item


def available(c,session):
    state=c.get('runtime',{}).get('pride',{})
    return c.get('kind')=='pc' and bool(c.get('sheet',{}).get('pride','').strip()) and not state.get('lost') and state.get('usedSession')!=session


def apply(room,s,data):
    from skill_checks import signature,count,successes
    import check_abilities
    from injuries import controls
    c=character(room,data.get('character'))
    if not controls(c,s):raise PermissionError('Гордость использует владелец героя или Мастер.')
    if c['kind']!='pc':raise ValueError('Гордость доступна игровому персонажу.')
    rt=c['runtime'];session=room['journey']['session'];op=data.get('op');gm=s['role']=='gm'
    if op=='replace':
        editable(room,dict(kind='character',id=c['id']),s)
        state=rt.get('pride',{})
        if not state.get('lost') or session<state['lostSession']+2:raise ValueError('После потери гордости нужна одна полная следующая игровая встреча без неё.')
        if data.get('lostSession')!=state['lostSession']:raise ValueError('Состояние гордости изменилось.')
        value=text(data.get('text',''),500)
        if not value:raise ValueError('Опишите новую гордость.')
        c['sheet']['pride']=value;state['lost']=False;state['replacedSession']=session
        room['log'].append(dict(name=c['name'],text='Выбрана новая гордость.'))
        return
    request=rt.get('prideRequest')
    if op in ('cancel','reject'):
        if op=='reject' and not gm:raise PermissionError('Применимость гордости решает Мастер.')
        if not request or request['id']!=data.get('request'):raise ValueError('Запрос уже изменён или завершён.')
        rt.pop('prideRequest');return
    if not available(c,session):raise ValueError('Гордость уже использована в этой встрече, потеряна или не указана в листе.')
    ctx=check_abilities.context(room,c,data.get('roll'),gm);r=ctx['r'];item=ctx['item']
    if r.get('pride') or not ctx['failed']:raise ValueError('Гордость используется после провала проверки и только один раз.')
    if op=='request':
        if request:raise ValueError('Сначала завершите или отмените текущий запрос гордости.')
        note=text(data.get('note',''),500)
        if not note:raise ValueError('Объясните, почему гордость помогает в этой проверке.')
        rt['prideRequest']=dict(id=secrets.token_hex(12),roll=data['roll'],event=ctx['event'],session=session,note=note,status='requested',private=ctx['private'])
        return
    if not request or request['id']!=data.get('request') or request['roll']!=data['roll'] or request['event']!=ctx['event'] or request['session']!=session:
        raise ValueError('Запрос или результат проверки уже изменился.')
    if op=='approve':
        if not gm:raise PermissionError('Применимость гордости подтверждает Мастер.')
        if request['status']!='requested':raise ValueError('Запрос уже рассмотрен.')
        request['status']='approved';return
    if op!='roll' or request['status']!='approved':raise ValueError('Сначала Мастер должен подтвердить применимость гордости.')
    value=die()
    failed=check_abilities.after_pride(room,c,ctx,value,successes(value))
    state=rt.setdefault('pride',{});state.update(usedSession=session,lost=failed)
    if state['lost']:
        state.update(lostSession=session,lostText=c['sheet']['pride']);c['sheet']['pride']=''
    rt.pop('prideRequest')
    outcome=f"Гордость D12 [{value}]: +{successes(value)} успехов. Итог: {r['hits']}. "
    outcome+='Гордость потеряна; следующую полную встречу герой играет без неё.' if state['lost'] else 'Гордость использована в этой встрече.'
    check_abilities.refresh(room,c,ctx,outcome)
    room['journey']['gmReady']=False


def guard_edit(old,sheet):
    if old and old.get('runtime',{}).get('pride',{}).get('lost') and sheet.get('pride')!=old['sheet'].get('pride'):
        raise ValueError('Гордость потеряна. Выберите новую через панель гордости после полной встречи без неё.')
