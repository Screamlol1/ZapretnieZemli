"""Versioned floor travel, personal sight, scene presets and adventure transfer."""
import copy
import math
import secrets
from location_editor import point
from location_maps import find,generate,settings,text
import adventure_packs
import location_vision
from injuries import now


def current(room,d):
    m=find(room,d.get('map'))
    if d.get('version')!=m['version']:raise ValueError('Карта уже изменилась. Обновите план и повторите действие.')
    return m


def owns(room,s,cid):
    c=next((c for c in room['characters'] if c['id']==cid),None)
    if not c or s['role']!='gm' and (c.get('owner')!=s['owner'] or c.get('hidden') or c['kind']!='pc'):raise PermissionError('Выберите своего персонажа.')
    return c


def exposed(room,m):
    if not m.get('revealed') or m['source']['kind']=='workshop':return False
    if m['source']['kind']=='hex':
        cell=room['maps']['world'].get(f"{m['source']['x']},{m['source']['y']}",{})
        return not cell.get('hidden') and not cell.get('siteHidden') and cell.get('locationMapId')==m['id']
    return True


def block_active(room):
    if room.get('combat',{}).get('phase') in ('setup','combat'):raise ValueError('Сначала завершите текущий бой.')


def apply(room,s,d):
    op=d.get('op');gm=s['role']=='gm'
    if op not in ('observer','move','stairsTravel') and not gm:raise PermissionError('Эта подготовка доступна Мастеру.')
    if op=='packPreview':
        checked,digest=adventure_packs.validate(d.get('pack'))
        room['locationPackPreview']=dict(id=secrets.token_hex(12),digest=digest,title=checked['title'],maps=len(checked['maps']),actors=len(checked['actors']),workshop=len(checked['workshop']),residents=sum(len(m.get('population',{}).get('residents',[])) for m in checked['maps']))
        return
    if op=='packImport':
        block_active(room)
        preview=room.get('locationPackPreview',{});checked,digest=adventure_packs.validate(d.get('pack'))
        if d.get('confirmed') is not True or d.get('preview')!=preview.get('id') or digest!=preview.get('digest'):raise ValueError('Сначала проверьте этот набор и подтвердите импорт.')
        room['locationPackImported']=adventure_packs.import_pack(room,checked);room.pop('locationPackPreview',None);return
    if op=='presetDelete':
        presets=room.get('scenePresets',[]);preset=next((p for p in presets if p['id']==d.get('preset')),None)
        if not preset or preset['version']!=d.get('presetVersion'):raise ValueError('Заготовка сцены уже изменилась.')
        if d.get('confirmed') is not True:raise ValueError('Подтвердите удаление заготовки.')
        presets.remove(preset);return
    m=current(room,d)
    if not gm and not exposed(room,m):raise PermissionError('Карта недоступна.')
    if op=='observer':
        c=owns(room,s,d.get('character'))
        if not any(t['characterId']==c['id'] and not t.get('secret') for t in m.get('tokens',[])):raise ValueError('Сначала разместите видимый жетон героя на этом этаже.')
        room.setdefault('locationObservers',{})[s['owner']]=c['id'];return
    if op=='vision':
        if type(d.get('enabled')) is not bool:raise ValueError('Укажите режим видимости.')
        if d['enabled'] and not location_vision.within_budget(m):raise ValueError('Слишком сложный план для личного обзора. Разделите его на этажи или сократите линии.')
        m['vision']=dict(enabled=d['enabled'],range=adventure_packs.number(d.get('range',30),1,100),personalLight=adventure_packs.number(d.get('personalLight',0),0,100))
    elif op=='move':
        block_active(room);c=owns(room,s,d.get('character'));t=next((t for t in m.get('tokens',[]) if t['characterId']==c['id'] and (gm or not t.get('secret'))),None)
        if not t:raise ValueError('Жетон не найден.')
        p=point(m,d.get('point'));distance=math.dist([t['x'],t['y']],p)*m['metersPerCell']/m['cellSize']
        if not gm:
            if distance>10:raise ValueError('Перемещайтесь шагами не более 10 метров. Дальние переходы задаёт Мастер.')
            if not location_vision.clear_line([t['x'],t['y']],p,location_vision.blockers(m)):raise ValueError('Путь пересекает стену или закрытую дверь.')
        t.update(x=p[0],y=p[1])
    elif op=='floorCreate':
        block_active(room)
        if len(room.get('locationMaps',[]))>=40:raise ValueError('В кампании уже 40 карт.')
        group=m.get('level',{}).get('group',m['id'])
        if sum(x.get('level',{}).get('group',x['id'])==group for x in room.get('locationMaps',[]))>=12:raise ValueError('В одной локации не более 12 этажей.')
        title=text(d.get('title',''),80)
        if not title:raise ValueError('Назовите новый этаж.')
        cfg=settings(dict(kind=d.get('kind','dungeon'),size=m.get('settings',{}).get('size','medium'),seed=d.get('seed',''),culture=m.get('culture','neutral')))
        floor=dict(id=secrets.token_hex(12),version=1,title=title,kind=cfg['kind'],source=dict(kind='library'),revealed=False,**generate(cfg),level=dict(group=group,name=title),stairs=[])
        m.setdefault('level',dict(group=group,name=m['title']));room['locationMaps'].append(floor)
    elif op=='stairsLink':
        target=find(room,d.get('targetMap'))
        if target['id']==m['id'] or target['version']!=d.get('targetVersion'):raise ValueError('Выберите актуальный другой этаж.')
        if len(m.get('stairs',[]))>=30 or len(target.get('stairs',[]))>=30:raise ValueError('Предел: 30 переходов на этаже.')
        if type(d.get('revealed')) is not bool:raise ValueError('Выберите видимость перехода.')
        group=m.get('level',{}).get('group',m['id']);targetgroup=target.get('level',{}).get('group')
        if targetgroup and targetgroup!=group:raise ValueError('Этаж уже связан с другой локацией.')
        a=point(m,d.get('point'));b=point(target,d.get('targetPoint'));aid,bid=secrets.token_hex(8),secrets.token_hex(8);name=text(d.get('name','Лестница'),80)
        m.setdefault('level',dict(group=group,name=m['title']));target.setdefault('level',dict(group=group,name=target['title']))
        m.setdefault('stairs',[]).append(dict(id=aid,name=name,targetMap=target['id'],targetStair=bid,x=a[0],y=a[1],revealed=d['revealed']))
        target.setdefault('stairs',[]).append(dict(id=bid,name=name,targetMap=m['id'],targetStair=aid,x=b[0],y=b[1],revealed=d['revealed']));target['version']+=1
    elif op=='stairsDelete':
        stair=next((x for x in m.get('stairs',[]) if x['id']==d.get('stair')),None)
        if not stair:raise ValueError('Переход уже удалён.')
        target=find(room,stair['targetMap'])
        if target['version']!=d.get('targetVersion'):raise ValueError('Другой этаж изменился.')
        m['stairs'].remove(stair);target['stairs']=[x for x in target.get('stairs',[]) if x['id']!=stair['targetStair']];target['version']+=1
    elif op=='stairsTravel':
        block_active(room);c=owns(room,s,d.get('character'));stair=next((x for x in m.get('stairs',[]) if x['id']==d.get('stair') and (gm or x.get('revealed'))),None)
        if not stair:raise PermissionError('Переход недоступен.')
        target=find(room,stair['targetMap']);other=next((x for x in target.get('stairs',[]) if x['id']==stair['targetStair']),None)
        if not other or target['version']!=d.get('targetVersion'):raise ValueError('Переход или другой этаж изменился.')
        if not gm and (not exposed(room,target) or not other.get('revealed')):raise PermissionError('Другой этаж ещё не открыт.')
        token=next((t for t in m.get('tokens',[]) if t['characterId']==c['id'] and (gm or not t.get('secret'))),None)
        if not token:raise ValueError('Герой уже покинул этот этаж.')
        if math.dist([token['x'],token['y']],[stair['x'],stair['y']])*m['metersPerCell']/m['cellSize']>2:raise ValueError('Подведите жетон к лестнице на расстояние до 2 метров.')
        if any(t['characterId']==c['id'] for t in target.get('tokens',[])):raise ValueError('Герой уже размещён на другом этаже. Уберите дубликат жетона.')
        if len(target.get('tokens',[]))>=100:raise ValueError('На другом этаже слишком много жетонов.')
        m['tokens'].remove(token);token.update(x=other['x'],y=other['y']);target.setdefault('tokens',[]).append(token);target['version']+=1
        room.setdefault('locationObservers',{})[s['owner']]=c['id'];room['locationLastTransition']=dict(owner=s['owner'],character=c['id'],map=target['id'])
    elif op=='presetSave':
        presets=room.setdefault('scenePresets',[])
        if len(presets)>=40:raise ValueError('В библиотеке уже 40 сцен.')
        title=text(d.get('title',''),120)
        if not title:raise ValueError('Назовите подготовленную сцену.')
        e=copy.deepcopy(m.get('exploration',dict(enabled=False,dark=False,discovered=[],doors={},lights=[])))
        for light in e.get('lights',[]):light['remainingMinutes']=max(0,light['expiresAt']-now(room)) if light.get('expiresAt') is not None else None;light.pop('expiresAt',None);light.pop('expired',None)
        presets.append(dict(id=secrets.token_hex(12),version=1,title=title,map=m['id'],tokens=copy.deepcopy(m.get('tokens',[])),exploration=e,vision=copy.deepcopy(m.get('vision',{})),description=text(d.get('description',''),1200),gmNote=text(d.get('gmNote',''),2400),ambient=room.get('audioDirector',{}).get('ambient','auto')))
    elif op=='presetApply':
        block_active(room);preset=next((p for p in room.get('scenePresets',[]) if p['id']==d.get('preset') and p['map']==m['id']),None)
        if not preset or preset['version']!=d.get('presetVersion'):raise ValueError('Заготовка сцены изменилась.')
        if d.get('confirmed') is not True:raise ValueError('Подтвердите замену расстановки, света и исследования.')
        ids={c['id'] for c in room['characters']};fids={f['id'] for f in m['features']};pids={p['id'] for p in m['paths']}
        if any(t['characterId'] not in ids for t in preset['tokens']) or any(v not in fids for v in preset['exploration'].get('discovered',[])) or any(v not in pids for v in preset['exploration'].get('doors',{})):raise ValueError('Карта или участники изменились. Сохраните новую заготовку сцены.')
        preset_ids={t['characterId'] for t in preset['tokens']}
        group=m.get('level',{}).get('group')
        if group and any(t['characterId'] in preset_ids for other in room.get('locationMaps',[]) if other['id']!=m['id'] and other.get('level',{}).get('group')==group for t in other.get('tokens',[])):raise ValueError('Участник сцены уже на другом этаже. Верните его переходом или уберите жетон перед запуском расстановки.')
        for token in preset['tokens']:point(m,[token['x'],token['y']])
        room['scenePresetUndo']=dict(map=m['id'],tokens=copy.deepcopy(m.get('tokens',[])),exploration=copy.deepcopy(m.get('exploration',{})),vision=copy.deepcopy(m.get('vision',{})),scene=copy.deepcopy(room.get('scene',{})),ambient=room.get('audioDirector',{}).get('ambient','auto'),expectedVersion=m['version']+1)
        m['tokens']=copy.deepcopy(preset['tokens']);m['exploration']=copy.deepcopy(preset['exploration']);m['vision']=copy.deepcopy(preset['vision'])
        for l in m['exploration'].get('lights',[]):
            remaining=l.pop('remainingMinutes',None);l['expiresAt']=None if remaining is None else now(room)+remaining
        room['scene']=dict(version=room.get('scene',{}).get('version',0)+1,map=m['id'],title=preset['title'],description=preset['description'])
        import audio_director
        audio_director.apply(room,s,dict(op='ambient',version=audio_director.state(room)['version'],ambient=preset['ambient']))
    elif op=='presetUndo':
        block_active(room);old=room.get('scenePresetUndo')
        if not old or old['map']!=m['id'] or old['expectedVersion']!=m['version']:raise ValueError('После запуска сцены карта уже менялась; адресная отмена недоступна.')
        for k in ('tokens','exploration','vision'):m[k]=copy.deepcopy(old[k])
        restored=copy.deepcopy(old['scene']);restored['version']=room.get('scene',{}).get('version',0)+1;room['scene']=restored
        import audio_director
        audio_director.apply(room,s,dict(op='ambient',version=audio_director.state(room)['version'],ambient=old['ambient']));room.pop('scenePresetUndo')
    elif op=='packExport':
        selected=d.get('workshop',[])
        if not isinstance(selected,list) or len(selected)>30 or any(not isinstance(v,str) for v in selected):raise ValueError('Выберите до 30 заготовок мастерской.')
        room['locationPackExport']=adventure_packs.export(room,m['id'],selected,d.get('includeFloors',True) is True);return
    else:raise ValueError('Неизвестное действие расширенного атласа.')
    m['version']+=1


def project(room,s):
    prefs=room.pop('locationObservers',{});room['locationObservers']={s['owner']:prefs[s['owner']]} if s['owner'] in prefs else {}
    gm=s['role']=='gm'
    room['locationViews']={}
    if not gm:
        for k in ('scenePresets','scenePresetUndo','locationPackExport','locationPackPreview','locationPackImported'):room.pop(k,None)
        last=room.get('locationLastTransition')
        if last and last['owner']!=s['owner']:room.pop('locationLastTransition',None)
    for m in room.get('locationMaps',[]):
        if not gm and not exposed(room,m):continue
        token,options=location_vision.observer(room,m,s)
        view=dict(observerOptions=options,observerId=token['characterId'] if token else '')
        room['locationViews'][m['id']]=view
        if gm:
            # Use the same server projection and redaction as a player, not a CSS mask.
            from location_maps import redact
            preview=copy.deepcopy(m);preview['revealed']=True;preview['source']=dict(kind='library')
            probe=dict(locationMaps=[preview],characters=room['characters'],maps=dict(world={}),locationObservers=room.get('locationObservers',{}),_previewVisibleMaps=[x['id'] for x in room.get('locationMaps',[]) if exposed(room,x)])
            redact(probe,s,preview=True)
            view['visionPreview']=probe['locationMaps'][0] if probe['locationMaps'] else None
    if gm:room['locationAdvancedAvailable']=True
    if gm:room.pop('locationObservers',None)


def restored(restored,current):
    """Invalidate previews and commands prepared on the discarded timeline."""
    for key in ('scenePresetUndo','locationHistory','locationViews','locationPackExport','locationPackPreview','locationPackImported','locationLastTransition','locationObservers'):
        restored.pop(key,None)
    versions={p['id']:p.get('version',0) for p in current.get('scenePresets',[])}
    for preset in restored.get('scenePresets',[]):preset['version']=max(preset.get('version',0),versions.get(preset['id'],0))+1
