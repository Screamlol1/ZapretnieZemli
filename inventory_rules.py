"""Campaign property is separate from the immutable creation equipment budget."""
import json
import math
import secrets
import subprocess
from pathlib import Path

def text(value,maximum=2000):
    if not isinstance(value,str) or len(value)>maximum:raise ValueError('Слишком длинное или некорректное текстовое поле.')
    return value.strip()

def number(value,maximum=1000,integer=False):
    if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=maximum or integer and type(value)!=int:raise ValueError('Некорректное количество или параметр предмета.')
    return value

def character(room,cid):
    c=next((c for c in room['characters'] if c['id']==cid),None)
    if not c or c['kind']=='monster':raise ValueError('Выберите героя или персонажа ведущего.')
    return c

def destination(room,raw,s):
    if not isinstance(raw,dict):raise ValueError('Укажите получателя предмета.')
    kind=raw.get('kind');identifier=raw.get('id','')
    if kind=='character':
        c=character(room,identifier)
        if s['role']!='gm' and (c.get('hidden') or c['kind']!='pc'):raise PermissionError('Этот получатель недоступен.')
    elif kind=='hold':
        if not any(h['id']==identifier for h in room.get('strongholds',[])):raise ValueError('Цитадель не найдена.')
    elif kind=='treasury':
        if s['role']!='gm':raise PermissionError('Хранилище Мастера недоступно.')
        identifier=''
    else:raise ValueError('Неизвестное место хранения.')
    return dict(kind=kind,id=identifier)

def owns(room,location,s):
    return location['kind']=='character' and any(c['id']==location['id'] and c['kind']=='pc' and c['owner']==s['owner'] and not c.get('hidden') for c in room['characters'])

def editable(room,location,s):
    if s['role']!='gm' and not owns(room,location,s):raise PermissionError('Можно управлять только своим инвентарём.')
    if location['kind']=='character':
        cid=location['id']
        if room.get('combat',{}).get('phase')=='combat' and cid in room.get('combatOwners',{}):raise ValueError('Завершите бой перед изменением инвентаря участника.')
        t=room.get('journey',{})
        if t.get('phase')=='resolving' and cid in t.get('party',[]):raise ValueError('Завершите действия текущей четверти перед изменением инвентаря.')

def validate(raw):
    if not isinstance(raw,dict):raise ValueError('Нужны параметры предмета.')
    name=text(raw.get('name',''),100)
    if not name:raise ValueError('Укажите название предмета.')
    kind=raw.get('kind','gear')
    if kind not in ('gear','weapon','armor','shield','artifact'):raise ValueError('Неизвестный тип предмета.')
    quantity=number(raw.get('quantity',1),999,True)
    if not quantity:raise ValueError('Количество должно быть не меньше одного.')
    return dict(name=name,kind=kind,quantity=quantity,weight=number(raw.get('weight',0)),
        description=text(raw.get('description','')),effect=text(raw.get('effect','')),gmNote=text(raw.get('gmNote','')),
        bonus=number(raw.get('bonus',0),20,True),damage=number(raw.get('damage',0),20,True),armor=number(raw.get('armor',0),30,True),
        grip=text(raw.get('grip',''),40),range=text(raw.get('range',''),60),artifactDie=text(raw.get('artifactDie',''),40))

def ensure(room,cid):
    c=character(room,cid)
    if c.get('inventoryInitialized'):return
    try:
        result=subprocess.run(['node',str(Path(__file__).with_name('inventory-data.mjs'))],input=json.dumps(c),text=True,capture_output=True,encoding='utf-8',timeout=8)
        if result.returncode:raise ValueError('Не удалось перенести стартовое снаряжение в инвентарь.')
        initial=json.loads(result.stdout)
    except (OSError,subprocess.TimeoutExpired):raise ValueError('Для переноса стартового снаряжения необходим Node.js.')
    items=room.setdefault('items',[])
    if len(items)+len(initial)>1000:raise ValueError('Предел предметов кампании: 1000.')
    for source in initial:
        raw=dict(name=source['name'],weight=source['weight'],kind='weapon' if source.get('weapon') else 'armor' if source.get('armor') else 'shield' if source.get('shield') else 'gear',bonus=source.get('bonus',source.get('shield',0)),damage=source.get('damage',0),armor=source.get('armor',0),grip=source.get('grip',''),range=source.get('range',''))
        items.append(dict(**validate(raw),id=secrets.token_hex(8),version=1,location=dict(kind='character',id=cid),catalogId=source['id']))
    c['inventoryInitialized']=True

def public_items(room,s):
    result=[]
    for item in room.get('items',[]):
        if s['role']=='gm':result.append(item)
        elif owns(room,item['location'],s) or item['location']['kind']=='hold':result.append({k:v for k,v in item.items() if k!='gmNote'})
    return result

def apply(room,s,data):
    action=data['action'];gm=s['role']=='gm'
    if action=='inventoryOpen':
        location=destination(room,dict(kind='character',id=data.get('character')),s);editable(room,location,s);ensure(room,location['id']);return
    if action=='itemCreate':
        location=destination(room,data.get('location'),s);editable(room,location,s)
        raw=validate(data.get('item'))
        if not gm and (raw['kind']!='gear' or any(raw[k] for k in ('bonus','damage','armor','effect','artifactDie','gmNote'))):raise PermissionError('Боевые свойства и артефакты задаёт Мастер.')
        if location['kind']=='character':ensure(room,location['id'])
        if len(room.setdefault('items',[]))>=1000:raise ValueError('Предел предметов кампании: 1000.')
        room['items'].append(dict(**raw,id=secrets.token_hex(8),version=1,location=location))
        return
    item=next((i for i in room.get('items',[]) if i['id']==data.get('id')),None)
    if not item:raise ValueError('Предмет не найден.')
    editable(room,item['location'],s)
    if data.get('version')!=item['version']:raise ValueError('Предмет уже изменён. Обновите инвентарь и повторите действие.')
    if action=='itemEdit':
        if not gm:raise PermissionError('Свойства предмета редактирует Мастер.')
        item.update(validate(data.get('item')));item.pop('catalogId',None)
    elif action=='itemTransfer':
        target=destination(room,data.get('location'),s)
        # Recipients may receive property without exposing their private sheet.
        editable(room,target,{**s,'role':'gm'})
        if target==item['location']:raise ValueError('Предмет уже находится у этого получателя.')
        quantity=number(data.get('quantity'),item['quantity'],True)
        if not quantity:raise ValueError('Укажите количество для передачи.')
        if target['kind']=='character':ensure(room,target['id'])
        if quantity<item['quantity']:
            if len(room['items'])>=1000:raise ValueError('Предел предметов кампании: 1000.')
            room['items'].append({**item,'id':secrets.token_hex(8),'version':1,'quantity':quantity,'location':target})
            item['quantity']-=quantity
        else:item['location']=target
        room['log'].append(dict(name=s['name'],text="Предмет передан; инвентари участников обновлены."))
    else:raise ValueError('Неизвестное действие инвентаря.')
    item['version']+=1
