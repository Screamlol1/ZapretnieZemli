"""Stronghold battle procedure: PHB175–178 and errata177 (+1 for all PCs)."""
import copy
import math
import secrets
from dice_events import publish,group

EVENTS=[
    'Падение героя с укрепления: высота D6+2 м, затем обычные правила падения.',
    'Герой отрезан D3+1 противниками; помощь подойдёт через два раунда личного боя.',
    'Один герой сталкивается с рядовым противником: проведите личный бой.',
    'Возможность сбросить лестницу или камни: успешная Сила сломит D3 нападающих.',
    'Герой вступает в поединок с вражеским командиром.',
    'Двое героев встречают сильного противника: командира или чудовище.']

def integer(v,maximum=10000):
    if type(v)!=int or not 0<=v<=maximum:raise ValueError('Некорректное количество.')
    return v

def flag(v):
    if type(v)!=bool:raise ValueError('Укажите условие явно.')
    return v

def die():return secrets.randbelow(6)+1
def ratings(v):
    d=v['defenders'];a=v['attackers'];sortie=v['sortie']
    defense=int(bool(v['heroes']))+min(5,math.ceil(d['guards']/(20 if sortie else 10)))-int(d['hungry'])
    if not sortie:defense+=d['ramparts']+int(d['portcullis'])+int(d['tower'])+int(d['moat'])
    attack=min(5,math.ceil(a['soldiers']/20))+int(a['commander'])+a['monsters']+int(a['flying'])
    if not sortie:attack+=int(a['ladders'])+int(a['ram'])
    return dict(defenders=max(0,defense),attackers=max(0,attack))

def record(room,v,text):
    v.setdefault('history',[]).append(text);v['history']=v['history'][-100:]
    room['log'].append(dict(name='Осада',text=text,private=False))

def hold(room,identifier):
    h=next((h for h in room.get('strongholds',[]) if h['id']==identifier),None)
    if not h:raise ValueError('Цитадель не найдена.')
    return h

def controls(v,s,side):
    return s['role']=='gm' or side=='defenders' and s['owner']==v['defenderOwner']

def apply(room,s,data):
    gm=s['role']=='gm';op=data.get('op');h=hold(room,data.get('hold'))
    if op=='create':
        if not gm:raise PermissionError('Оборону готовит Мастер.')
        if h.get('siege',{}).get('phase') not in (None,'finished'):raise ValueError('У цитадели уже есть незавершённая осада.')
        raw=data.get('setup',{});d=raw.get('defenders',{});a=raw.get('attackers',{})
        heroes=raw.get('heroes',[])
        if not isinstance(heroes,list) or len(set(heroes))!=len(heroes) or any(not any(c['id']==cid and c['kind']=='pc' and not c.get('hidden') and not c.get('runtime',{}).get('dead') for c in room['characters']) for cid in heroes):raise ValueError('Выберите участвующих героев.')
        owner=raw.get('defenderOwner','gm')
        if owner!='gm' and not any(c['kind']=='pc' and c['owner']==owner and c['id'] in heroes for c in room['characters']):raise ValueError('Защитой управляет владелец участвующего героя или Мастер.')
        v=dict(id=secrets.token_hex(12),version=1,phase='preparing',round=0,heroes=heroes,defenderOwner=owner,sortie=flag(raw.get('sortie',False)),
            defenders=dict(guards=integer(d.get('guards',0)),hungry=flag(d.get('hungry',False)),ramparts=integer(d.get('ramparts',0),2),**{k:flag(d.get(k,False)) for k in ('portcullis','tower','moat','well')}),
            attackers=dict(soldiers=integer(a.get('soldiers',0)),monsters=integer(a.get('monsters',0),20),**{k:flag(a.get(k,False)) for k in ('commander','ladders','ram','flying')}),
            occupants=integer(raw.get('occupants',d.get('guards',0))),waterStock=integer(raw.get('waterStock',0)),suppliedDay=room['journey']['day']-1,history=[])
        if v['occupants']<v['defenders']['guards']:raise ValueError('Число обитателей не может быть меньше гарнизона.')
        v['rating']=ratings(v);h['siege']=v;record(room,v,f'{h["name"]}: подготовка обороны; защита {v["rating"]["defenders"]}, нападение {v["rating"]["attackers"]}.');return
    v=h.get('siege')
    if not v or data.get('id')!=v['id'] or data.get('version')!=v['version']:raise ValueError('Осада обновилась. Откройте актуальные данные.')
    if v['phase']=='finished':raise ValueError('Это сражение уже завершено.')
    side=data.get('side')
    if op in ('roll','loss','decision') and (side not in ('defenders','attackers') or not controls(v,s,side)):raise PermissionError('Вы не управляете этой стороной.')
    if op=='supply':
        if not gm:raise PermissionError('Припасы подтверждает Мастер.')
        day=room['journey']['day'];days=day-v['suppliedDay']
        if days<1:raise ValueError('Припасы за этот день уже учтены.')
        need=math.ceil(v['occupants']/5)*days;stock=h.setdefault('stock',{})
        food=min(stock.get('food',0),need);water=need if v['defenders']['well'] else min(v['waterStock'],need)
        stock['food']=stock.get('food',0)-food
        if not v['defenders']['well']:v['waterStock']-=water
        hungry=food<need
        if v['phase']=='preparing':v['defenders']['hungry']=hungry;v['rating']=ratings(v)
        elif hungry!=v['defenders']['hungry']:v['rating']['defenders']=max(0,v['rating']['defenders']+(-1 if hungry else 1));v['defenders']['hungry']=hungry
        v['suppliedDay']=day;record(room,v,f'Снабжение за {days} дн.: еда {food}/{need}, вода {water}/{need}. Личные припасы героев учитываются отдельно.')
    elif op=='start':
        if not gm or v['phase']!='preparing':raise PermissionError('Сражение начинает Мастер после подготовки.')
        if not v['heroes'] and not v['defenders']['guards']:
            v.update(phase='finished',winner='attackers');record(room,v,'Цитадель без героев и стражи захвачена без сражения.')
        elif not v['rating']['attackers'] or not v['rating']['defenders']:
            v.update(phase='finished',winner='attackers' if not v['rating']['defenders'] else 'defenders')
        else:v.update(phase='rolling',round=1,rolls={},losses={},decisions={})
    elif op=='roll':
        if v['phase']!='rolling' or side in v['rolls']:raise ValueError('Эта сторона уже бросила кости.')
        dice=[die() for _ in range(v['rating'][side])];v['rolls'][side]=dict(dice=dice,hits=dice.count(6))
        publish(room,'Осада · '+('защита' if side=='defenders' else 'нападение'),f'Ход осады {v["round"]}',[group('base',dice)],f'Потери противника: {dice.count(6)}. Риск не применяется.',False)
        if len(v['rolls'])==2:
            v['losses']={side:min(v['rating'][side],v['rolls']['attackers' if side=='defenders' else 'defenders']['hits']) for side in ('defenders','attackers')};v['phase']='losses'
            advance(v)
    elif op=='loss':
        if v['phase']!='losses' or v['losses'].get(side,0)<1:raise ValueError('Потери этой стороны уже распределены.')
        kind=data.get('kind');party=v[side]
        if side=='defenders' and kind=='guards' and party['guards']>0:party['guards']=max(0,party['guards']-(20 if v['sortie'] else 10))
        elif side=='defenders' and not v['sortie'] and kind=='ramparts' and party['ramparts']>0:party['ramparts']-=1
        elif side=='defenders' and not v['sortie'] and kind=='portcullis' and party['portcullis']:party['portcullis']=False
        elif side=='attackers' and kind=='soldiers' and party['soldiers']>0:party['soldiers']=max(0,party['soldiers']-20)
        elif side=='attackers' and kind in ('commander','ram') and party[kind]:party[kind]=False
        elif side=='attackers' and kind=='monsters' and party['monsters']>0:party['monsters']-=1
        elif kind=='ruling' and gm and isinstance(data.get('note'),str) and data['note'].strip() and len(data['note'])<=600:
            record(room,v,'Нестандартное последствие Мастера: '+data['note'].strip())
        else:raise ValueError('Это последствие сейчас недоступно.')
        v['rating'][side]-=1;v['losses'][side]-=1
        record(room,v,('Защита' if side=='defenders' else 'Нападение')+f': −1 рейтинга, последствие «{kind}».');advance(v)
    elif op=='event':
        if not gm or v['phase']!='event' or v.get('event'):raise ValueError('Сейчас не требуется новое личное событие.')
        roll=die();v['event']=dict(roll=roll,text=EVENTS[roll-1]);publish(room,'Мастер','Личное событие осады',[group('table',[roll])],v['event']['text'],False)
    elif op=='resolveEvent':
        note=data.get('note')
        if not gm or v['phase']!='event' or not v.get('event') or not isinstance(note,str) or not note.strip() or len(note)>1000:raise ValueError('Запишите исход разыгранного личного события.')
        if room.get('combat',{}).get('phase')=='combat' or room.get('combat',{}).get('pendingRisk'):raise ValueError('Завершите личный бой перед следующим ходом осады.')
        record(room,v,'Личное событие: '+note.strip());v['phase']='decision'
    elif op=='decision':
        if v['phase']!='decision' or side in v['decisions'] or data.get('value') not in ('fight','surrender'):raise ValueError('Решение уже принято или ещё рано его принимать.')
        v['decisions'][side]=data['value']
        if data['value']=='surrender':v.update(phase='finished',winner='attackers' if side=='defenders' else 'defenders');record(room,v,('Защитники' if side=='defenders' else 'Нападающие')+' прекратили сражение.')
        elif len(v['decisions'])==2:v.update(phase='rolling',round=v['round']+1,rolls={},losses={},decisions={});v.pop('event',None)
    else:raise ValueError('Неизвестное действие осады.')
    v['version']+=1


def advance(v):
    if any(v['losses'].values()):return
    zero=[side for side,rating in v['rating'].items() if rating<=0]
    if zero:v.update(phase='finished',winner='draw' if len(zero)==2 else ('attackers' if zero[0]=='defenders' else 'defenders'))
    else:v['phase']='event' if v['heroes'] else 'decision'


def project(room,s):
    # No identities, tokens or GM notes are copied into this public procedure.
    room['sieges']=[dict(hold=h['id'],name=h['name'],food=h.get('stock',{}).get('food',0),**copy.deepcopy(h['siege'])) for h in room.get('strongholds',[]) if h.get('siege')]
