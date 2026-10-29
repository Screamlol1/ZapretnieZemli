"""Bounded GM audit with entity-specific inverses; rolls are never replayed."""
import copy
import json
import secrets
import time
import hashlib

COLLECTIONS=('characters','items','tokens','strongholds','locationMaps','workshop')
SAFE={'paint','mapLocation','token','deleteToken','visual','runtime','assignCharacter',
      'character','actor','deleteCharacter','itemCreate','itemEdit','itemTransfer','itemWear',
      'itemAppearance','itemSplit','itemMerge','inventoryCoins','equipment'}
LABELS={'paint':'Местность','mapLocation':'Место на карте','token':'Жетон','deleteToken':'Удаление жетона',
        'visual':'Внешность','runtime':'Состояние героя','assignCharacter':'Владелец героя',
        'character':'Лист героя','actor':'Персонаж Мастера','deleteCharacter':'Удаление персонажа',
        'itemCreate':'Создание предмета','itemEdit':'Изменение предмета','itemTransfer':'Передача предмета',
        'itemWear':'Износ предмета','itemAppearance':'Изображение предмета','itemSplit':'Разделение стопки',
        'itemMerge':'Объединение стопок','inventoryCoins':'Монеты','equipment':'Экипировка',
        'combatAction':'Боевое действие','characterRoll':'Проверка героя','characterPush':'Риск героя',
        'inventoryRepair':'Ремонт','tableTool':'Совместная игра','sessionRecap':'Итоги встречи',
        'injury':'Травма или лечение','changeUndo':'Исправление действия',
        'characterProgression':'Развитие героя','characterAbility':'Способность народа',
        'characterAccept':'Принятие результата проверки','freeAccept':'Принятие свободного броска',
        'roll':'Свободный бросок','freePush':'Риск свободного броска',
        'travelSetup':'Сбор отряда','travelParty':'Состав и условия путешествия',
        'travelRelocate':'Перенос отряда','travelPlan':'Заявка на четверть',
        'travelRoute':'Маршрут отряда','travelReady':'Начало проверок четверти',
        'travelComplete':'Подтверждение результатов четверти','travelResolve':'Решение события',
        'travelConditions':'Состояния путешественника','travelSupplies':'Припасы',
        'travelConsume':'Расход припасов','travelRecover':'Восстановление',
        'travelFinds':'Добыча путешествия','travelEvent':'Событие путешествия',
        'travelRisk':'Риск путешествия','travelSession':'Новая игровая встреча',
        'travelAdvance':'Переход к следующей четверти','inventoryResource':'Запас припасов',
        'itemConsume':'Расход предмета','combatCreate':'Подготовка боя','combatClose':'Завершение боя',
        'combatManual':'Решение Мастера в бою','worldLayout':'Сетка общей карты','mapArtwork':'Фон общей карты'}


def action_name(action):
    if action in LABELS:return LABELS[action]
    for prefix,name in (('locationMap','Карта локации'),('workshop','Мастерская'),('hold','Цитадель'),('opposed','Встречная проверка'),('travel','Путешествие'),('combat','Бой')):
        if action.startswith(prefix):return name
    return 'Изменение кампании'


def object_name(room,key,value):
    if value and (value.get('name') or value.get('title')):return value.get('name') or value['title']
    parts=key.split(':',2)
    if parts[0]=='maps':
        from campaign_rules import hex_label
        x,y=map(int,parts[2].split(','))
        return 'Гекс '+hex_label(dict(x=x,y=y),room) if parts[1]=='world' else f'Клетка поля боя {x+1}:{y+1}'
    return {'characters':'Персонаж','items':'Предмет','tokens':'Жетон','strongholds':'Цитадель','locationMaps':'Карта локации','workshop':'Заготовка Мастера'}.get(parts[0],'Объект кампании')


def snapshot(room):
    result={}
    for collection in COLLECTIONS:
        for entity in room.get(collection,[]): result[collection+':'+entity['id']]=copy.deepcopy(entity)
    for kind,cells in room.get('maps',{}).items():
        for key,value in cells.items(): result['maps:'+kind+':'+key]=copy.deepcopy(value)
    return result


def context(room):
    t=room.get('journey',{})
    return [t.get('cycleId'),room.get('combatRevision',0),t.get('phase')]


def busy(room):
    return (room.get('combat',{}).get('phase') in ('setup','combat') or
            room.get('journey',{}).get('phase')=='resolving' or room.get('journeyRisk') or
            room.get('treatment') or any(i.get('repair',{}).get('status')=='rolled' for i in room.get('items',[])) or
            pending_check(room) or
            any(not p.get('done') for p in room.get('opposedChecks',[])))


def pending_check(room):
    from skill_checks import signature
    for c in room.get('characters',[]):
        for r in (c.get('runtime',{}).get('lastCheck'),room.get('gmChecks',{}).get(c['id'])):
            if not r or r.get('accepted') or r.get('pushed'):continue
            item=next((i for i in room.get('items',[]) if i['id']==r.get('item') and i.get('location')==dict(kind='character',id=c['id'])),None)
            if r.get('item') and not item:continue
            if r.get('signature')==signature(c,item):return True
    return False


def dependencies(room,key):
    """Changes to an object's consumers invalidate its inverse, too.

    Only references to this entity are fingerprinted: a change to another hero,
    map cell or item remains independent. Digests keep the bounded audit small.
    """
    kind,identifier,*_=key.split(':',2)
    refs=[]
    if kind=='characters':
        refs.extend([('token',t) for t in room.get('tokens',[]) if t.get('characterId')==identifier])
        refs.extend([('item',i) for i in room.get('items',[]) if i.get('location')==dict(kind='character',id=identifier)])
        for m in room.get('locationMaps',[]):
            refs.extend([('location',m['id'],t) for t in m.get('tokens',[]) if t.get('characterId')==identifier])
        t=room.get('journey',{})
        if identifier in t.get('party',[]):refs.append(('party',t.get('plans',{}).get(identifier)))
        refs.extend([('battle',u) for u in room.get('combat',{}).get('units',[]) if u.get('id')==identifier])
        if identifier in room.get('gmChecks',{}):refs.append(('privateCheck',room['gmChecks'][identifier]))
        for p in room.get('opposedChecks',[]):
            if any(p.get(side,{}).get('character')==identifier for side in ('attacker','defender')):refs.append(('opposed',p))
        recap=room.get('sessionRecap')
        if recap and recap.get('status')=='draft' and any(c['id']==identifier for c in recap['characters']):refs.append(('recap',recap['id']))
    elif kind=='items':
        for c in room.get('characters',[]):
            slots={k:v for k,v in c.get('equipment',{}).items() if v==identifier}
            if slots:refs.append(('equipment',c['id'],slots))
            for check in (c.get('runtime',{}).get('lastCheck'),room.get('gmChecks',{}).get(c['id'])):
                if check and check.get('item')==identifier:refs.append(('check',c['id'],check))
        refs.extend([('repair',i['id'],i['repair']) for i in room.get('items',[]) if i.get('repair',{}).get('tool')==identifier])
        refs.extend([('plan',cid,p) for cid,p in room.get('journey',{}).get('plans',{}).items() if p.get('gearItem')==identifier])
    else:return ''
    treatment=room.get('treatment')
    if treatment and identifier in (treatment.get('character'),treatment.get('target'),treatment.get('healer'),treatment.get('item'),treatment.get('tool')):refs.append(('treatment',treatment))
    return hashlib.sha256(json.dumps(refs,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def record(room, before, s, data, before_context):
    action=data.get('action')
    if action in ('chat','inventoryOpen'): return
    after=snapshot(room);keys=sorted(k for k in before.keys()|after.keys() if before.get(k)!=after.get(k))
    versions=room.setdefault('changeVersions',{})
    for key in keys: versions[key]=versions.get(key,0)+1
    if action=='tableTool' and data.get('op') in ('ping','propose','withdraw','focus'):return
    patches=[dict(key=k,before=before.get(k),after=after.get(k),version=versions[k]) for k in keys]
    permitted=action in SAFE and keys and before_context==context(room) and not busy(room)
    if len(json.dumps(patches,ensure_ascii=False))>100000:permitted=False
    entries=room.setdefault('changeHistory',[])
    entries.append(dict(id=secrets.token_hex(8),time=time.time(),actor=s['name'],owner=s['owner'],
                        label=action_name(action),action=action,context=context(room),
                        summary=', '.join(dict.fromkeys(object_name(room,k,after.get(k) or before.get(k)) for k in keys))[:240],
                        patches=patches if permitted else [],dependencies={k:dependencies(room,k) for k in keys} if permitted else {},reason='' if permitted else 'Игровое разрешение или связанные изменения; используйте контрольное сохранение.'))
    entries[:]=entries[-40:]
    while len(json.dumps(entries,ensure_ascii=False))>400000 and len(entries)>1:entries.pop(0)
    needed={p['key'] for e in entries for p in e.get('patches',[])}
    room['changeVersions']={k:v for k,v in versions.items() if k in needed}


def inspect_history(room):
    return dict(current=snapshot(room),busy=bool(busy(room)),context=context(room),dependencies={})


def reason(room, entry, inspection=None):
    if entry.get('undone'):return 'Уже отменено.'
    if not entry.get('patches'):return entry.get('reason','Для этого действия нет безопасной отмены.')
    inspection=inspection if inspection is not None else inspect_history(room)
    if inspection['busy']:return 'Завершите бой и незавершённые проверки перед исправлением.'
    if entry.get('context')!=inspection['context']:return 'После действия изменился игровой этап или бой.'
    current=inspection['current'];references=inspection['dependencies']
    for p in entry['patches']:
        if room.get('changeVersions',{}).get(p['key'])!=p['version'] or current.get(p['key'])!=p['after']:
            return 'Этот объект уже использован или изменён позднее. Последующие действия будут затронуты.'
        if p['key'] not in references:references[p['key']]=dependencies(room,p['key'])
        if entry.get('dependencies',{}).get(p['key'],'')!=references[p['key']]:
            return 'После действия появились или изменились связанные жетоны, предметы, проверки или участники. Исправление затронет их.'
    return ''


def undo(room,s,data):
    if s['role']!='gm':raise PermissionError('Исправлять действия через историю может Мастер.')
    if data.get('revision')!=room['revision']:raise ValueError('История изменилась. Обновите её и проверьте действие.')
    entry=next((e for e in room.get('changeHistory',[]) if e['id']==data.get('id')),None)
    if not entry:raise ValueError('Действие больше не хранится в краткой истории.')
    problem=reason(room,entry)
    if problem:raise ValueError(problem)
    note=data.get('note')
    if not isinstance(note,str) or not 3<=len(note.strip())<=300:raise ValueError('Укажите причину исправления (3–300 символов).')
    for p in entry['patches']:
        parts=p['key'].split(':',2);value=copy.deepcopy(p['before'])
        if parts[0]=='maps':
            cells=room['maps'][parts[1]]
            if value is None:cells.pop(parts[2],None)
            else:cells[parts[2]]=value
        else:
            coll=room.setdefault(parts[0],[]);coll[:]=[x for x in coll if x['id']!=parts[1]]
            if value is not None:
                if parts[0]=='items':value['version']=max(value.get('version',0),(p['after'] or {}).get('version',0))+1
                if parts[0]=='characters':
                    value['equipmentVersion']=max(value.get('equipmentVersion',0),(p['after'] or {}).get('equipmentVersion',0))+1
                    progression=value.get('sheet',{}).get('progression')
                    if progression:progression['revision']=max(progression['revision'],(p['after'] or {}).get('sheet',{}).get('progression',{}).get('revision',0))+1
                coll.append(value)
    entry['undone']=dict(by=s['name'],time=time.time(),note=note.strip())
    room['journey']['gmReady']=False
    room['log'].append(dict(name=s['name'],text='Исправлено действие «'+entry['label']+'»: '+note.strip()))


def project(room,s):
    entries=room.pop('changeHistory',[])
    if s['role']=='gm':
        inspection=inspect_history(room) if any(e.get('patches') and not e.get('undone') for e in entries) else None
        projected=[]
        for e in entries:
            unavailable=reason(room,e,inspection)
            projected.append({**{k:v for k,v in e.items() if k not in ('patches','context','owner','reason','dependencies')},
                                'changes':[dict(object=object_name(room,p['key'],p.get('after') or p.get('before')),
                                                fields=[dict(field=k,before=json.dumps((p['before'] or {}).get(k),ensure_ascii=False)[:250],after=json.dumps((p['after'] or {}).get(k),ensure_ascii=False)[:250])
                                                        for k in ((p['before'] or {}).keys()|(p['after'] or {}).keys()) if (p['before'] or {}).get(k)!=(p['after'] or {}).get(k)][:8]) for p in e.get('patches',[])][:10],
                                'canUndo':not unavailable,'unavailable':unavailable})
        room['changeHistory']=projected
    room.pop('changeVersions',None)
