"""GM-controlled public ambience and short-lived presentation cues."""
import math
import secrets
import time

AMBIENTS=frozenset(('auto','silent','battle','wind','forest','cave','river','marsh','fire','city','tavern','rain','night'))
CUES=frozenset(('metal','footstep','monster','wolf','break','thunder','bell','blacksmith','snow-step','dice','magic'))
CUE_TTL=8
CUE_COOLDOWN=.8


def number(value):
    return type(value) in (int,float) and math.isfinite(value)


def state(room):
    raw=room.get('audioDirector',{})
    if not isinstance(raw,dict):raw={}
    version=raw.get('version',0)
    ambient=raw.get('ambient','auto')
    cues=raw.get('cues',[])
    return dict(version=version if type(version) is int and version>=0 else 0,
                ambient=ambient if isinstance(ambient,str) and ambient in AMBIENTS else 'auto',
                cues=[dict(id=c['id'],type=c['type'],at=c['at']) for c in cues
                      if isinstance(c,dict) and isinstance(c.get('id'),str) and 0<len(c['id'])<=80
                      and isinstance(c.get('type'),str) and c['type'] in CUES and number(c.get('at'))][-12:] if isinstance(cues,list) else [],
                lastCueAt=raw.get('lastCueAt',0) if number(raw.get('lastCueAt',0)) else 0)


def project(room):
    current=state(room);now=time.time()
    room['audioDirector']=dict(version=current['version'],ambient=current['ambient'],
                               cues=[c for c in current['cues'] if 0<=now-c['at']<=CUE_TTL])


def checkpoint(room):
    current=state(room)
    return dict(version=current['version'],ambient=current['ambient'],cues=[])


def restored(room,previous):
    current=checkpoint(room)
    current['version']=max(current['version'],state(previous)['version'])+1
    room['audioDirector']=current


def apply(room,session,data):
    if session['role']!='gm':raise PermissionError('Общим звуком управляет только Мастер.')
    current=state(room);operation=data.get('op')
    if operation=='ambient':
        version=data.get('version');ambient=data.get('ambient')
        if type(version) is not int or version!=current['version']:
            raise ValueError('Звуковая сцена уже изменилась. Обновите состояние и повторите выбор.')
        if not isinstance(ambient,str) or ambient not in AMBIENTS:
            raise ValueError('Выберите звуковую сцену из списка.')
        current['ambient']=ambient
    elif operation=='cue':
        cue=data.get('cue')
        if not isinstance(cue,str) or cue not in CUES:raise ValueError('Выберите звук из списка.')
        now=time.time()
        if current['lastCueAt'] and now-current['lastCueAt']<CUE_COOLDOWN:
            raise ValueError('Подождите немного перед следующим общим звуком.')
        current['cues']=(current['cues']+[dict(id=secrets.token_hex(12),type=cue,at=now)])[-12:]
        current['lastCueAt']=now
    else:raise ValueError('Неизвестное действие звукового пульта.')
    current['version']+=1
    room['audioDirector']=current
