"""PH p49: opposed skills; only the initiating side may push."""
import secrets
from skill_checks import apply as skill_check,ATTRS
from inventory_rules import character,editable,ensure
from dice_events import visibility

def apply(room,s,data):
    checks=room.setdefault('opposedChecks',[])
    gm=s['role']=='gm';action=data['action']
    if action=='opposedCreate':
        if sum(not p.get('done') for p in checks)>=10:raise ValueError('Сначала завершите открытые встречные проверки (не более 10).')
        sides=[]
        for key in ('attacker','defender'):
            raw=data.get(key,{})
            if not isinstance(raw,dict):raise ValueError('Укажите обе стороны проверки.')
            c=character(room,raw.get('character'));ensure(room,c['id'])
            if key=='attacker':editable(room,dict(kind='character',id=c['id']),s)
            elif not gm and c.get('hidden'):raise PermissionError('Этот персонаж недоступен.')
            skill=raw.get('skill');mod=raw.get('modifier',0)
            if skill not in ATTRS or type(mod)!=int or not -10<=mod<=10:raise ValueError('Проверьте навыки и модификаторы.')
            if not gm and key=='defender':mod=0
            sides.append(dict(character=c['id'],name=c['name'],skill=skill,modifier=mod,item=raw.get('item','') if gm or key=='attacker' else '',rolled=False))
        if any(not p.get('done') and any(p[k]['character'] in [x['character'] for x in sides] for k in ('attacker','defender')) for p in checks):raise ValueError('Участник уже выполняет встречную проверку. Сначала завершите или отмените её.')
        if sides[0]['character']==sides[1]['character']:raise ValueError('Нужны два разных персонажа.')
        private=visibility(s,data) or any(character(room,x['character']).get('hidden') for x in sides)
        checks.append(dict(id=secrets.token_hex(12),attacker=sides[0],defender=sides[1],private=private,done=False,note=str(data.get('note',''))[:300]))
        room['opposedChecks']=checks[-40:];return
    p=next((p for p in checks if p['id']==data.get('id')),None)
    if not p or p['done']:raise ValueError('Встречная проверка уже завершена.')
    if p['private'] and not gm:raise PermissionError('Скрытую проверку проводит Мастер.')
    key=data.get('side','attacker')
    if key not in ('attacker','defender'):raise ValueError('Укажите сторону проверки.')
    side=p[key];c=character(room,side['character']);editable(room,dict(kind='character',id=c['id']),s)
    if action=='opposedCancel':
        p['done']=True;p['cancelled']=True;p['result']='Проверка отменена.';return
    if action=='opposedRoll':
        if side['rolled']:raise ValueError('Эта сторона уже бросила кости.')
        item=next((i for i in room.get('items',[]) if i['id']==side['item']),None)
        skill_check(room,s,dict(action='characterRoll',character=c['id'],skill=side['skill'],modifier=side['modifier'],item=side['item'],itemVersion=item['version'] if item else None,revision=room['revision'],visibility='hidden' if p['private'] else 'public',note=p['note']),opposed=True)
        r=room['gmChecks'][c['id']] if p['private'] else c['runtime']['lastCheck']
        r['opposed']=p['id'];side.update(rolled=True,roll=r['id'],hits=r['hits'])
        event=room['diceRolls'][-1];event['label']='Встречная · '+('инициатор' if key=='attacker' else 'защитник')
        if key=='defender':event.pop('risk',None)
        else:event['risk']=dict(action='opposed',character=c['id'],roll=r['id'],opposed=p['id'],attribute=r['attribute'])
    elif action in ('opposedPush','opposedAccept'):
        if key!='attacker' or not all(p[k]['rolled'] for k in ('attacker','defender')):raise ValueError('Риск доступен только инициатору после бросков обеих сторон.')
        skill_check(room,s,dict(action='characterPush' if action=='opposedPush' else 'characterAccept',character=c['id'],roll=side['roll']),opposed=True)
        r=room['gmChecks'][c['id']] if p['private'] else c['runtime']['lastCheck'];side['hits']=r['hits'];p['done']=True
    else:raise ValueError('Неизвестное действие встречной проверки.')
    if all(p[k]['rolled'] for k in ('attacker','defender')):
        a=p['attacker']['hits'];d=p['defender']['hits'];net=max(0,a-d);p['net']=net
        p['result']=f'Инициатор {a} − защитник {d} = {net}. '+('Инициатор добился успеха.' if net else 'Инициатор не добился успеха; ничья в пользу защиты.')
        if p['done']:
            room['log'].append(dict(name='Встречная проверка',kind='check',text=p['result'],private=p['private']))
            if action=='opposedPush':room['diceRolls'][-1]['result']+=' '+p['result']
