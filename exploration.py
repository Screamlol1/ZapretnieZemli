"""GM-controlled discovery and light on location plans; no hidden geometry in views."""
import copy
import math
import secrets
from injuries import now
from inventory_rules import text,number


def ensure_paths(m):
    for i,p in enumerate(m.get('paths',[])):p.setdefault('id','path-'+str(i+1))


def state(m):
    ensure_paths(m)
    return m.setdefault('exploration',dict(enabled=False,discovered=[],dark=False,doors={},lights=[]))


def visible_ids(m):
    e=m.get('exploration',{})
    return {f['id'] for f in m['features'] if not f.get('secret') and (not e.get('enabled') or f['id'] in e.get('discovered',[]))}


def contains(f,x,y):
    # Inverse rotation keeps discovery tied to the object when the GM moves it.
    cx,cy=f['x']+f['w']/2,f['y']+f['h']/2;a=-math.radians(f.get('rotation',0));dx,dy=x-cx,y-cy
    px,py=cx+dx*math.cos(a)-dy*math.sin(a),cy+dx*math.sin(a)+dy*math.cos(a)
    return f['x']<=px<=f['x']+f['w'] and f['y']<=py<=f['y']+f['h']


def visible_point(m,x,y):
    e=m.get('exploration',{})
    if not e.get('enabled'):return True
    ids=visible_ids(m)
    return any(f['id'] in ids and contains(f,x,y) for f in m['features'])


def public_state(m):
    ensure_paths(m)
    e=copy.deepcopy(m.get('exploration',{}));ids=visible_ids(m)
    paths={p['id'] for p in m['paths'] if not p.get('secret') and all(i in ids for i in p.get('refs',[])) and (not e.get('enabled') or p.get('refs') or all(visible_point(m,x,y) for x,y in p['points']))}
    e['discovered']=[i for i in e.get('discovered',[]) if i in ids]
    e['doors']={i:v for i,v in e.get('doors',{}).items() if i in paths}
    e['lights']=[l for l in e.get('lights',[]) if not l.get('secret') and visible_point(m,l['x'],l['y'])]
    return e


def apply(room,s,d):
    if s['role']!='gm':raise PermissionError('Комнаты, двери, свет и текущую сцену раскрывает Мастер.')
    if d.get('op')=='scene':
        old=room.get('scene',{})
        if d.get('version',0)!=old.get('version',0):raise ValueError('Сцена уже изменилась.')
        mid=d.get('map','');m=next((x for x in room.get('locationMaps',[]) if x['id']==mid),None)
        if mid and not m:raise ValueError('Локация не найдена.')
        room['scene']=dict(version=old.get('version',0)+1,map=mid,title=text(d.get('title',''),120),description=text(d.get('description',''),1200))
        return
    m=next((x for x in room.get('locationMaps',[]) if x['id']==d.get('map')),None)
    if not m or d.get('version')!=m['version']:raise ValueError('План уже изменился. Обновите панель исследования.')
    e=state(m);op=d.get('op')
    if op=='settings':
        if any(type(d.get(k)) is not bool for k in ('enabled','dark')):raise ValueError('Выберите режим открытия и освещения.')
        e.update(enabled=d['enabled'],dark=d['dark'])
    elif op=='discover':
        f=next((f for f in m['features'] if f['id']==d.get('feature')),None)
        if not f or type(d.get('revealed')) is not bool:raise ValueError('Выберите помещение или здание.')
        ids=set(e['discovered'])
        if d['revealed']:ids.add(f['id'])
        else:ids.discard(f['id'])
        e['discovered']=sorted(ids)
    elif op=='door':
        p=next((p for p in m['paths'] if p['id']==d.get('path') and p['style'] in ('passage','wall','palisade')),None)
        if not p or d.get('state') not in ('open','closed','locked','none'):raise ValueError('Выберите проход и состояние двери или ворот.')
        if d['state']=='none':e['doors'].pop(p['id'],None)
        else:e['doors'][p['id']]=d['state']
    elif op=='light':
        x,y=number(d.get('x'),m['width']),number(d.get('y'),m['height'])
        radius=number(d.get('radius'),100)
        if radius<=0:raise ValueError('Радиус света должен быть больше нуля.')
        duration=number(d.get('minutes',0),525600,True)
        if len(e['lights'])>=50:raise ValueError('Предел: 50 источников света на плане.')
        e['lights'].append(dict(id=secrets.token_hex(6),name=text(d.get('name','Свет'),80),x=x,y=y,radius=radius,expiresAt=now(room)+duration if duration else None,secret=d.get('secret') is True))
    elif op=='removeLight':
        e['lights']=[l for l in e['lights'] if l['id']!=d.get('light')]
    else:raise ValueError('Неизвестное действие исследования.')
    m['version']+=1


def project(room,s):
    for m in room.get('locationMaps',[]):
        ensure_paths(m)
        for light in m.get('exploration',{}).get('lights',[]):light['expired']=light.get('expiresAt') is not None and now(room)>=light['expiresAt']
    if s['role']=='gm':return
    # Scene titles/descriptions may describe an unrevealed map; reveal it first.
    from location_maps import redact
    probe=dict(locationMaps=copy.deepcopy(room.get('locationMaps',[])),characters=room['characters'],maps=dict(world=copy.deepcopy(room['maps']['world'])));redact(probe)
    visible={m['id'] for m in probe.get('locationMaps',[])}
    if room.get('scene',{}).get('map') and room['scene']['map'] not in visible:room.pop('scene',None)
