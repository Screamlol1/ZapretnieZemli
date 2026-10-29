"""Shared map attention, suggested routes and explicit control of absent players."""
import copy
import secrets
import time
from campaign_rules import coordinate, adjacent, apply as journey_action
from terrain_map import cell_at


def state(room):
    return room.setdefault('tableTools', dict(pings=[], proposals={}, control={}))


def point(room, raw):
    p = coordinate(raw, room)
    if cell_at(room, f'{p["x"]},{p["y"]}').get('hidden'):
        raise ValueError('Для общего указателя и маршрута сначала откройте гекс игрокам.')
    return p


def focus_target(room, raw):
    if not isinstance(raw, dict): raise ValueError('Выберите место на карте.')
    if raw.get('kind') == 'world': return dict(kind='world', **point(room, raw))
    if raw.get('kind') == 'location':
        from location_maps import redact
        view = copy.deepcopy(room); redact(view)
        visible = view.get('locationMaps', [])
        if not any(m['id'] == raw.get('id') for m in visible):
            raise ValueError('Откройте карту локации игрокам перед приглашением.')
        return dict(kind='location', id=raw['id'])
    raise ValueError('Неизвестная карта.')


def returned(room, owner, name):
    tools = state(room)
    if tools['control'].pop(owner, None):
        room['log'].append(dict(name='Стол', text=name + ' вернулся: временное управление Мастера завершено.'))
        return True
    return False


def apply(room, s, data, online):
    tools = state(room); op = data.get('op'); gm = s['role'] == 'gm'; now = time.time()
    if op in ('claim', 'release', 'completeFor'):
        if not gm: raise PermissionError('Временное управление принимает Мастер.')
        owner = data.get('owner')
        if not isinstance(owner, str): raise ValueError('Выберите участника.')
        if op == 'claim':
            if owner in online: raise ValueError('Игрок подключён. Временное управление доступно после отключения.')
            if not any(c['kind'] == 'pc' and c['owner'] == owner and not c.get('hidden') for c in room['characters']):
                raise ValueError('У участника нет открытых героев.')
            if any(i['owner'] == owner and i['role'] == 'gm' for i in room.get('identities', {}).values()):
                raise ValueError('Мастер уже управляет своими персонажами.')
            if owner in tools['control']: raise ValueError('Управление уже принято.')
            tools['control'][owner] = dict(id=secrets.token_hex(8), by=s['owner'], time=now)
            name = next((i['name'] for i in room['identities'].values() if i['owner'] == owner), 'Игрок')
            room['log'].append(dict(name=s['name'], text='Принято временное управление героями: ' + name + '. Подтверждения выполняются отдельно.'))
        elif op == 'release':
            if not tools['control'].pop(owner, None): raise ValueError('Временное управление уже завершено.')
            room['log'].append(dict(name=s['name'], text='Временное управление возвращено владельцу.'))
        else:
            if owner not in tools['control'] or owner in online: raise ValueError('Нет временного управления этим отсутствующим игроком.')
            if room.get('journeyRisk'): raise ValueError('Сначала завершите проверку путешествия.')
            proxy = dict(s, role='player', owner=owner)
            journey_action(room, proxy, {**data, 'action':'travelComplete'})
            room['log'].append(dict(name=s['name'], text='Мастер проверил и подтвердил результаты отсутствующего игрока.'))
        return
    if op == 'ping':
        target = point(room, data)
        recent = [p for p in tools['pings'] if now-p['time'] < 90]
        if any(p['owner'] == s['owner'] and now-p['time'] < 2 for p in recent):
            raise ValueError('Подождите две секунды перед следующим указателем.')
        tools['pings'] = (recent + [dict(id=secrets.token_hex(8), owner=s['owner'], name=s['name'], time=now, **target)])[-12:]
    elif op == 'focus':
        if not gm: raise PermissionError('Предложить всей группе место просмотра может Мастер.')
        tools['focus'] = dict(id=secrets.token_hex(8), target=focus_target(room, data.get('target')), time=now, name=s['name'])
    elif op in ('propose', 'withdraw'):
        t = room['journey']
        if t['phase'] != 'planning' or not t['party']: raise ValueError('Маршрут предлагают на этапе заявок собранного отряда.')
        if data.get('cycle') != t['cycleId']: raise ValueError('Началась другая четверть. Составьте маршрут заново.')
        old = tools['proposals'].get(s['owner'], {})
        if old.get('cycle') != t['cycleId']: old={}
        if data.get('version', 0) != old.get('version', 0): raise ValueError('Предложение изменилось в другом окне.')
        path = data.get('path', []) if op == 'propose' else []
        if not isinstance(path, list) or len(path) > 3: raise ValueError('Предложите до трёх соседних гексов.')
        previous = t['position']; checked=[]
        for raw in path:
            p = point(room, raw)
            if not adjacent(previous, p, room) or p in checked or p==t['position']: raise ValueError('Маршрут должен идти по соседним гексам без повторов и возврата в стартовый гекс.')
            checked.append(p); previous=p
        tools['proposals'][s['owner']] = dict(owner=s['owner'], name=s['name'], path=checked, cycle=t['cycleId'], start=t['position'].copy(), version=old.get('version', 0)+1)
    elif op == 'acceptRoute':
        if not gm: raise PermissionError('Общий маршрут выбирает Мастер.')
        proposal = tools['proposals'].get(data.get('owner'), {})
        t = room['journey']
        if not proposal.get('path') or proposal.get('version') != data.get('version') or proposal.get('cycle') != t['cycleId'] or proposal.get('start') != t['position']:
            raise ValueError('Предложение маршрута устарело.')
        for p in proposal['path']: point(room, p)
        journey_action(room, s, dict(action='travelRoute', path=proposal['path'], revision=data.get('revision'), cycle=data.get('cycle'), phase=data.get('phase'), routeVersion=data.get('routeVersion')))
        proposal['accepted'] = True
    else: raise ValueError('Неизвестный инструмент совместной игры.')


def project(room, s):
    tools = state(room); now=time.time()
    def public_point(p):
        try: point(room, p); return True
        except (ValueError, TypeError, KeyError): return False
    tools['pings'] = [p for p in tools['pings'] if now-p['time'] < 90 and public_point(p)]
    tools['proposals'] = {k:p for k,p in tools['proposals'].items() if p.get('cycle') == room['journey']['cycleId'] and all(public_point(x) for x in p['path'])}
    if tools.get('focus'):
        try:
            if now-tools['focus']['time'] > 300: raise ValueError()
            focus_target(room, tools['focus']['target'])
        except (ValueError, TypeError, KeyError): tools.pop('focus', None)
