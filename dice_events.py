"""Server-owned dice events. Private events never enter a player's response."""
import copy
import secrets
import time

LABELS = dict(penalty='Штраф',base='Характеристика', skill='Навык', gear='Снаряжение', artifact='Артефакт',
              armor='Броня', cover='Укрытие', magic='Магия', table='Таблица', monster='Чудовище')

def visibility(session, data):
    value = data.get('visibility', 'public')
    if value not in ('public', 'hidden'):
        raise ValueError('Выберите открытый или скрытый бросок.')
    if value == 'hidden' and session['role'] != 'gm':
        raise PermissionError('Игроки бросают кости открыто.')
    return value == 'hidden'

def group(kind, values, sides=6, negative=False):
    return dict(kind=kind, label=LABELS[kind], values=list(values), sides=sides, negative=negative)

def pools(r):
    groups = [group('base', r.get('base', [])),
              group('skill', r.get('skillDice', r.get('skill', [])), negative=r.get('negative', False)),
              group('gear', r.get('gear', []))]
    for g,key in zip(groups,('base','skillDice','gear')):
        g['held']=r.get('held',{}).get(key,[])
    groups.append({**group('penalty',r.get('penalty',[]),negative=True),'held':r.get('held',{}).get('penalty',[])})
    for a in r.get('artifacts', []):
        groups.append({**group('artifact', [a['value']], a['sides']), 'held':[a.get('held',False)]})
    if r.get('sides'):
        groups.append({**group('artifact', r.get('artifact', []), r['sides']), 'held':r.get('held',{}).get('artifact',[])})
    if r.get('pride'):
        groups.append(dict(kind='artifact',label='Гордость',values=[r['pride']['value']],sides=12,negative=False))
    return groups

def publish(room, name, label, groups, result, private=False, message=None, risk=None, sources=None):
    event = dict(id=secrets.token_hex(12), time=time.time(), name=name, label=label,
                 groups=copy.deepcopy([g for g in groups if g['values']]), result=str(result), private=bool(private))
    if risk:event['risk']=copy.deepcopy(risk)
    if sources:event['sources']=copy.deepcopy(sources)
    pending={room.get('combat',{}).get('pendingRisk',{}).get('id'),room.get('journeyRisk',{}).get('id')} - {None}
    events=room.get('diceRolls', []) + [event]
    check_ids={r.get('diceEvent') for c in room.get('characters',[]) for r in
               (c.get('runtime',{}).get('lastCheck'),room.get('gmChecks',{}).get(c['id'])) if r and not r.get('accepted')}
    treatment=room.get('treatment',{}).get('roll',{})
    if treatment.get('id'):pending.add(treatment['id'])
    cold=room.get('coldCheck',{})
    if cold.get('id'):pending.add(cold['id'])
    water=room.get('waterCheck',{})
    if water.get('id'):pending.add(water['id'])
    for key in ('afflictionCheck','expeditionCheck'):
        if room.get(key,{}).get('id'):pending.add(room[key]['id'])
    for key in ('afflictionCheck','expeditionCheck'):
        p=room.get(key,{})
        if p.get('id'):pending.add(p['id'])
    for item in room.get('items',[]):
        repair=item.get('repair',{})
        if repair.get('status')=='rolled':pending.add(repair['roll']['id'])
    pinned=[e for e in events[:-1] if e['id'] in check_ids or e.get('risk',{}).get('roll') in pending][-199:]
    keep={e['id'] for e in pinned}|{event['id']}
    for old in reversed(events):
        if len(keep)>=200:break
        keep.add(old['id'])
    room['diceRolls']=[e for e in events if e['id'] in keep]
    if message is None:
        values = '; '.join(f"{g['label']}{' (−)' if g.get('negative') else ''} D{g['sides']} [{', '.join(map(str, g['values']))}]" for g in event['groups'])
        message = f'{label}: {values or "без костей"}. {result}'
    room['log'].append(dict(name=name, kind='check', text=message, private=bool(private), diceEvent=event['id']))
    return event['id']

def redact(room):
    room['diceRolls'] = [e for e in room.get('diceRolls', []) if not e.get('private')]
    room['log'] = [e for e in room['log'] if not e.get('private')]
    room.pop('gmChecks', None)
    battle = room.get('combat')
    if battle and 'publicLog' in battle:
        battle['log'] = battle.pop('publicLog')
    if battle and battle.get('pendingMishap'):
        # Manual adjudication belongs to the GM; do not expose a hidden D66.
        battle['pendingMishap'] = {'pending': True}
