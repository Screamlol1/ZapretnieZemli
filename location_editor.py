"""Validated, versioned manual edits to a location plan (GM only)."""
import math
import secrets


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
    elif op in ('move', 'remove'):
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
        if op == 'remove':
            collection.remove(target)
            if kind == 'feature':
                m['paths'] = [p for p in m['paths'] if target['id'] not in p.get('refs', [])]
        elif kind == 'path':
            raise ValueError('Линию можно удалить и проложить заново.')
        else:
            x, y = point(m, data.get('point'))
            if kind == 'feature':
                point(m, [x+target['w'], y+target['h']])
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
