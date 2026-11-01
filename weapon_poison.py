"""Weapon coatings, PHB p114. Doses are actual inventory stacks."""
import secrets
import injuries
from afflictions import POISONS
from equipment_rules import owned, prepare, bonus

ELIGIBLE={'sword','greatsword','axe','dagger','spear','halberd','bow','longbow','crossbow','throwingknife','throwingspear'}


def reconcile(room):
    now=injuries.now(room)
    room['weaponCoatings']=[p for p in room.get('weaponCoatings',[]) if p['expiresAt']>now and any(i['id']==p['weapon'] for i in room.get('items',[]))]
    ids={i['id'] for i in room.get('items',[])}
    room['poisonSupplies']={k:v for k,v in room.get('poisonSupplies',{}).items() if k in ids}


def apply(room,s,data):
    reconcile(room);op=data.get('op');gm=s['role']=='gm'
    if room.get('combat',{}).get('pendingRisk') or room.get('combat',{}).get('cardExchange') or room.get('afflictionCheck'):
        raise ValueError('Сначала завершите текущую проверку или комбинацию.')
    c=injuries.character(room,data.get('character'))
    if not injuries.controls(c,s):raise PermissionError('Можно использовать только предметы своего персонажа.')
    items=owned(room,c['id']);item=next((i for i in items if i['id']==data.get('item')),None)
    if not item or item['version']!=data.get('version'):raise ValueError('Предмет изменился. Откройте актуальную карточку.')
    if op=='configure':
        if not gm:raise PermissionError('Состав и силу яда задаёт Мастер.')
        typ=data.get('type');potency=data.get('potency')
        if typ not in POISONS or type(potency)!=int or not 1<=potency<=30:raise ValueError('Выберите яд и силу от 1 до 30.')
        if item['kind']!='gear':raise ValueError('Дозы должны быть отдельной переносимой стопкой снаряжения.')
        room.setdefault('poisonSupplies',{})[item['id']]=dict(type=typ,potency=potency)
        item['version']+=1
        return
    if op!='coat':raise ValueError('Неизвестное действие с ядом.')
    injuries.check_allowed(c)
    supply=room.get('poisonSupplies',{}).get(item['id'])
    if not supply:raise ValueError('Мастер должен сначала указать содержимое стопки яда.')
    prepare(room,c)
    weapon=next((i for i in items if i['id']==data.get('weapon')),None)
    if not weapon or weapon.get('quantity')!=1 or weapon.get('combatProfile') not in ELIGIBLE or bonus(weapon)<=0:
        raise ValueError('Нужно исправное колющее или режущее оружие, либо отдельный готовый боеприпас.')
    if weapon['version']!=data.get('weaponVersion'):raise ValueError('Оружие изменилось.')
    if any(p['weapon']==weapon['id'] for p in room.get('weaponCoatings',[])):raise ValueError('На оружии уже есть действующий яд.')
    b=room.get('combat',{})
    if b.get('phase')=='combat':
        u=next((u for u in b['units'] if u['id']==c['id']),None)
        if not u or b['order'][b['turn']]!=c['id'] or not u['slow'] or u['str']<=0:raise ValueError('Нанесение яда требует медленного действия ходящего бойца.')
        if u.get('equipmentIds',{}).get('weapon')!=weapon['id']:raise ValueError('В бою яд наносится на выбранное оружие.')
        u['slow']-=1;b['roundStarted']=True;b['activationStarted']=True;room['combatRevision']+=1
    elif room.get('journey',{}).get('phase')=='resolving' and c['id'] in room['journey'].get('party',[]):
        raise ValueError('Сначала завершите текущее занятие путешествия.')
    item['quantity']-=1;item['version']+=1
    if not item['quantity']:room['items'].remove(item);room['poisonSupplies'].pop(item['id'],None)
    weapon['version']+=1
    room.setdefault('weaponCoatings',[]).append(dict(id=secrets.token_hex(12),weapon=weapon['id'],character=c['id'],**supply,expiresAt=injuries.now(room)+360))
    room['log'].append(dict(name='Яд на оружии',text=f'{c["name"]}: подготовлено оружие «{weapon["name"]}», израсходована одна доза.',private=bool(c.get('hidden'))))


def after_combat(room,impacts):
    reconcile(room)
    for hit in impacts:
        if hit.get('action') not in ('slash','stab','shoot') or not hit.get('weapon'):continue
        coating=next((p for p in room.get('weaponCoatings',[]) if p['weapon']==hit['weapon']),None)
        if not coating:continue
        room['weaponCoatings'].remove(coating)
        target=next((c for c in room['characters'] if c['id']==hit['target']),None)
        if not target:continue
        text='Покрытие израсходовано попаданием; броня остановила повреждение, яд не проник.'
        if hit.get('damage',0)>0:
            if target['kind']=='monster':
                text='Покрытие израсходовано. Мастер определяет восприимчивость чудовища к яду по его описанию.'
            else:
                target.setdefault('runtime',{}).setdefault('afflictions',[]).append(dict(id=secrets.token_hex(12),kind='poison',type=coating['type'],name=POISONS[coating['type']][0],potency=coating['potency'],note='Яд проник через повреждение от оружия.',phase='exposed',nextAt=injuries.now(room),created=injuries.now(room)))
                text=f'Требуется сопротивление: {POISONS[coating["type"]][0]}, сила {coating["potency"]}.'
        room['log'].append(dict(name='Яд на оружии',text=f'{target["name"]}: {text}',private=bool(target.get('hidden'))))


def project(room,s):
    reconcile(room)
    if s['role']=='gm':return
    ids={c['id'] for c in room['characters'] if c['kind']=='pc' and c['owner']==s['owner'] and not c.get('hidden')}
    items={i['id'] for i in room.get('items',[]) if i['location'].get('kind')=='character' and i['location'].get('id') in ids}
    room['poisonSupplies']={k:v for k,v in room.get('poisonSupplies',{}).items() if k in items}
    room['weaponCoatings']=[p for p in room.get('weaponCoatings',[]) if p['weapon'] in items]
