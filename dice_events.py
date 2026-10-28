"""Server-owned dice events. Private events never enter a player's response."""
import copy
import secrets
import time

LABELS = dict(base='Характеристика', skill='Навык', gear='Снаряжение', artifact='Артефакт',
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
    for a in r.get('artifacts', []):
        groups.append(group('artifact', [a['value']], a['sides']))
    if r.get('sides'):
        groups.append({**group('artifact', r.get('artifact', []), r['sides']), 'held':r.get('held',{}).get('artifact',[])})
    return groups

def publish(room, name, label, groups, result, private=False, message=None):
    event = dict(id=secrets.token_hex(12), time=time.time(), name=name, label=label,
                 groups=copy.deepcopy([g for g in groups if g['values']]), result=str(result), private=bool(private))
    room['diceRolls'] = (room.get('diceRolls', []) + [event])[-200:]
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
