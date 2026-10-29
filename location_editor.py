"""Validated, versioned manual edits to a location plan (GM only)."""
import math
import secrets
import copy
import json
from location_geometry import transform_line


def snapshot(m):
    return {k:copy.deepcopy(m.get(k, {} if k=='settings' else 'neutral' if k=='culture' else 'grass' if k=='ground' else 'earth' if k=='roadSurface' else [])) for k in ('features','paths','tokens','culture','ground','roadSurface','settings')}


def remember(room, m, before):
    after=snapshot(m)
    changes={k:v for k,v in before.items() if v!=after[k]}
    if not changes:return
    history=room.setdefault('locationHistory',{}).setdefault(m['id'],[])
    history.append(changes)
    del history[:-20]
    while len(history)>1 and len(json.dumps(history,ensure_ascii=False).encode('utf-8'))>2_000_000:
        history.pop(0)
    m['undoCount']=len(history)


def undo(room, m):
    history=room.get('locationHistory',{}).get(m['id'],[])
    if not history:raise ValueError('Нет действий для отмены на этой карте.')
    m.update(history.pop())
    m['undoCount']=len(history)


def rotate_point(p, center, angle):
    a=math.radians(angle);x,y=p[0]-center[0],p[1]-center[1]
    return [center[0]+x*math.cos(a)-y*math.sin(a),center[1]+x*math.sin(a)+y*math.cos(a)]


def feature_bounds(m, f):
    x,y,w,h=f['x'],f['y'],f['w'],f['h']
    center=[x+w/2,y+h/2]
    for p in ([x,y],[x+w,y],[x+w,y+h],[x,y+h]):
        px,py=rotate_point(p,center,f.get('rotation',0))
        if px < -1e-6 or py < -1e-6 or px > m['width']+1e-6 or py > m['height']+1e-6:
            raise ValueError('После поворота объект выходит за границы плана. Переместите его ближе к центру.')


def point(m, raw):
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise ValueError('Нужны координаты на плане.')
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in raw):
        raise ValueError('Некорректные координаты.')
    x, y = raw
    if not 0 <= x <= m['width'] or not 0 <= y <= m['height']:
        raise ValueError('Объект выходит за границы плана.')
    return [round(x, 3), round(y, 3)]


def edit(room, m, data, art_ids):
    op = data.get('op')
    if op == 'add':
        if len(m['features']) >= 300:
            raise ValueError('На плане уже 300 объектов.')
        art = data.get('art')
        if art not in art_ids:
            raise ValueError('Выберите иллюстрацию объекта.')
        sizes = [data.get('widthMeters'), data.get('heightMeters')]
        if any(type(v) not in (int, float) or not math.isfinite(v) or not .5 <= v <= 100 for v in sizes):
            raise ValueError('Размеры объекта: от 0,5 до 100 метров.')
        w, h = [v * m['cellSize'] / m['metersPerCell'] for v in sizes]
        cx, cy = point(m, data.get('point'))
        x, y = point(m, [cx-w/2, cy-h/2]); point(m, [x+w, y+h])
        label = data.get('label', '')
        if not isinstance(label, str) or len(label) > 80:
            raise ValueError('Название: до 80 символов.')
        m['features'].append(dict(id=secrets.token_hex(12), style=art, art=art, shape='rect',
                                 x=x, y=y, w=w, h=h, label=label.strip(), note='', gmNote='', secret=data.get('secret') is True))
    elif op in ('move', 'remove', 'rotate'):
        kind = data.get('kind')
        if kind not in ('feature', 'path', 'token'):
            raise ValueError('Выберите объект, линию или жетон.')
        collection = m.setdefault({'feature':'features', 'path':'paths', 'token':'tokens'}[kind], [])
        if kind == 'path':
            index = data.get('target')
            target = collection[index] if type(index) is int and 0 <= index < len(collection) else None
        else:
            target = next((f for f in collection if f['id'] == data.get('target')), None)
        if target is None:
            raise ValueError('Объект уже удалён. Обновите план.')
        if op == 'rotate':
            angle=data.get('angle')
            if type(angle) not in (int,float) or not math.isfinite(angle) or not -360<=angle<=360:
                raise ValueError('Угол поворота: от −360 до 360 градусов.')
            angle=angle%360
            if kind=='path':
                pts=target['points'];center=target.get('rotationCenter') or [(min(p[i] for p in pts)+max(p[i] for p in pts))/2 for i in (0,1)]
                if target.get('refs'):raise ValueError('Связанный проход следует за комнатой. Для отдельного поворота нарисуйте новый проход.')
                transform_line(m,target,lambda p:rotate_point(p,center,angle-target.get('rotation',0)),point)
                target['rotationCenter']=center
            elif kind=='feature':
                feature_bounds(m,{**target,'rotation':angle})
            target['rotation']=angle
        elif op == 'remove':
            collection.remove(target)
            if kind == 'feature':
                m['paths'] = [p for p in m['paths'] if target['id'] not in p.get('refs', [])]
        elif kind == 'path':
            if target.get('refs'):raise ValueError('Связанный проход перемещается вместе с комнатой.')
            x,y=point(m,data.get('point'));pts=target['points']
            center=[(min(p[i] for p in pts)+max(p[i] for p in pts))/2 for i in (0,1)]
            dx,dy=x-center[0],y-center[1]
            transform_line(m,target,lambda p:[p[0]+dx,p[1]+dy],point)
            if 'rotationCenter' in target:target['rotationCenter']=[target['rotationCenter'][0]+dx,target['rotationCenter'][1]+dy]
        else:
            x, y = point(m, data.get('point'))
            if kind == 'feature':
                point(m, [x+target['w'], y+target['h']])
                feature_bounds(m,{**target,'x':x,'y':y})
                dx, dy = x-target['x'], y-target['y']
                for p in target.get('points', []):
                    p[0] += dx; p[1] += dy
                # Generated corridors stay attached to the moved room.
                for path in m['paths']:
                    refs = path.get('refs', [])
                    if target['id'] in refs:
                        i = 0 if len(refs) > 1 and refs[0] == target['id'] else -1
                        path['points'][i][0] += dx; path['points'][i][1] += dy
            target.update(x=x, y=y)
    elif op == 'path':
        if len(m['paths']) >= 300:
            raise ValueError('На плане уже 300 линий.')
        style = data.get('style')
        raw = data.get('points')
        if style not in ('road', 'wall', 'palisade', 'passage') or not isinstance(raw, list) or not 2 <= len(raw) <= 100:
            raise ValueError('Линия должна содержать от 2 до 100 точек.')
        pts = [point(m, p) for p in raw]
        if any(math.dist(a, b) < 1 for a, b in zip(pts, pts[1:])):
            raise ValueError('Соседние точки линии должны различаться.')
        m['paths'].append(dict(points=pts, style=style, refs=[], secret=data.get('secret') is True))
    elif op == 'token':
        character = next((c for c in room['characters'] if c['id'] == data.get('characterId')), None)
        if not character:
            raise ValueError('Выберите персонажа кампании. Сначала создайте его в разделе персонажей.')
        tokens = m.setdefault('tokens', [])
        if len(tokens) >= 100:
            raise ValueError('На плане уже 100 жетонов.')
        if any(t['characterId'] == character['id'] for t in tokens):
            raise ValueError('Этот персонаж уже на плане. Переместите его жетон.')
        x, y = point(m, data.get('point'))
        tokens.append(dict(id=secrets.token_hex(12), characterId=character['id'], x=x, y=y, secret=data.get('secret') is True))
    else:
        raise ValueError('Неизвестный инструмент редактора.')
