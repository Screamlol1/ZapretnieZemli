"""PHB pp. 50, 52: Crafting restores one point per success; failure is permanent.

Time, facilities and advanced-item talents are confirmed by the GM, never inferred
from a free-text item. Only the final accepted/pushed result changes the target.
"""
import copy
import json
import secrets
import time
from dice_pools import artifact_sides, skill_counts, result_text
from dice_events import visibility, publish, pools
from equipment_rules import bonus, artifact, clear_slots, owned
from risk_rules import push, score, can_push


def die(sides=6):
    return secrets.randbelow(sides)+1


def pending(room, cid):
    return next((i for i in room.get('items', []) if i.get('repair', {}).get('status') == 'rolled'
                 and i['repair'].get('character') == cid), None)


def signature(c, tool):
    return json.dumps([c['sheet'], c['runtime']['current'], c['runtime'].get('wp', 0),
                       tool.get('version') if tool else None], sort_keys=True)


def repair_stat(item):
    if item.get('quantity') != 1:
        raise ValueError('Для ремонта отделите один предмет от стопки.')
    if item.get('bonus', 0) and item.get('armor', 0):
        raise ValueError('Предмет с бонусом и защитой одновременно требует ручного решения Мастера.')
    stat = 'armor' if item.get('armor', 0) else 'bonus'
    if item.get(stat, 0) <= 0 or item.get('wear', 0) <= 0:
        raise ValueError('У этого предмета нет повреждённого бонуса или защиты для ремонта.')
    return stat


def public_repair(value):
    if value.get('status') == 'rolled' and value.get('private'):
        return dict(status='rolled', character=value.get('character'), waiting=True)
    return {k: copy.deepcopy(v) for k, v in value.items() if k not in ('signature', 'requestedBy')}


def approved(room, c, target, data):
    from inventory_rules import text
    if data.get('conditionsConfirmed') is not True:
        raise ValueError('Мастер должен подтвердить время, условия и необходимые достоинства для ремонта.')
    note = text(data.get('note', ''), 500)
    if not note:
        raise ValueError('Укажите условия ремонта: время, мастерская, инструменты и нужные достоинства.')
    modifier = data.get('modifier', 0)
    if type(modifier) != int or not -10 <= modifier <= 10:
        raise ValueError('Модификатор ремонта должен быть целым числом от −10 до 10.')
    iid = data.get('tool', '')
    tool = next((i for i in owned(room, c['id']) if i['id'] == iid), None)
    if iid and (not tool or tool.get('quantity') != 1 or tool['id'] == target['id']):
        raise ValueError('Выберите отдельный одиночный инструмент этого персонажа.')
    if tool and tool.get('bonus', 0) > 0 and not bonus(tool):
        raise ValueError('Сломанный инструмент нельзя использовать для ремонта.')
    extras = artifact_sides(data)
    if len(extras)+bool(artifact(tool) if tool else 0) > 10:
        raise ValueError('Не более 10 артефактных костей вместе с инструментом.')
    return dict(status='approved', character=c['id'], note=note, tool=iid, modifier=modifier,
                artifacts=extras, toolVersion=tool['version'] if tool else None,
                approvedVersion=target['version']+1)


def finish(room, c, item, r, stat):
    old_max = item[stat]
    current = max(0, old_max-item.get('wear', 0))
    restored = min(item.get('wear', 0), r['hits']) if r['hits'] else 0
    destroyed = not r['hits'] and current == 0
    if r['hits']:
        item['wear'] = max(0, item.get('wear', 0)-restored)
        result = f'Восстановлено {restored}. Теперь {item[stat]-item["wear"]}/{item[stat]}.'
    elif destroyed:
        result = 'Неудача: предмет окончательно уничтожен.'
    else:
        item[stat] = current
        item['wear'] = 0
        result = f'Неудача: постоянный предел снижен с {old_max} до {current}.'
    summary = dict(item=item['id'], name=item['name'], stat=stat, oldMaximum=old_max,
                   maximum=0 if destroyed else item[stat], restored=restored, destroyed=destroyed,
                   hits=r['hits'], pushed=r['pushed'], private=r['private'], time=time.time(), result=result)
    if destroyed:
        clear_slots(room, item['id'])
        room['items'].remove(item)
    else:
        item.pop('repair', None)
        item['version'] += 1
        item['lastRepair'] = summary
    # Private results remain in the private dice journal, never in player runtime.
    if not r['private']:
        c['runtime']['lastRepair'] = summary
    return result


def apply(room, s, data):
    from inventory_rules import character, editable, ensure, text
    gm = s['role'] == 'gm'
    item = next((i for i in room.get('items', []) if i['id'] == data.get('id')), None)
    if not item or item.get('location', {}).get('kind') != 'character':
        raise ValueError('Выберите предмет в инвентаре персонажа.')
    editable(room, item['location'], s, repair=True)
    if data.get('version') != item['version']:
        raise ValueError('Предмет уже изменён. Обновите инвентарь и повторите действие.')
    c = character(room, item['location']['id'])
    ensure(room, c['id'])
    op = data.get('op')
    p = item.get('repair', {})
    if op in ('approve',) and not gm:
        raise PermissionError('Условия ремонта подтверждает Мастер.')
    if op == 'cancel':
        if p.get('status') not in ('requested', 'approved'):
            raise ValueError('После броска нужно принять результат или пойти на риск; отмена недоступна.')
        item.pop('repair', None)
        item['version'] += 1
        return
    stat = repair_stat(item)
    if op in ('request', 'approve', 'roll'):
        if pending(room, c['id']):
            raise ValueError('Сначала завершите предыдущий бросок ремонта этого персонажа.')
        if any(not pair.get('done') and any(pair[k]['character'] == c['id'] for k in ('attacker', 'defender')) for pair in room.get('opposedChecks', [])):
            raise ValueError('Сначала завершите встречную проверку этого персонажа.')
        if op == 'request':
            if p:
                raise ValueError('Заявка на ремонт уже существует.')
            item['repair'] = dict(status='requested', character=c['id'], requestedBy=s['owner'], note=text(data.get('note', ''), 500))
            item['version'] += 1
            return
        if op == 'approve' or gm and p.get('status') != 'approved':
            p = approved(room, c, item, data)
            item['repair'] = p
            item['version'] += 1
            if op == 'approve':
                return
        if p.get('status') != 'approved':
            raise ValueError('Сначала Мастер должен подтвердить условия ремонта.')
        if item['version'] != p.get('approvedVersion'):
            raise ValueError('Предмет изменился. Мастер должен заново подтвердить условия ремонта.')
        tool = next((i for i in owned(room, c['id']) if i['id'] == p['tool']), None)
        if p['tool'] and (not tool or tool['version'] != p.get('toolVersion')):
            raise ValueError('Инструмент изменился. Мастер должен заново подтвердить условия ремонта.')
        base = c['runtime']['current']['str']
        if base <= 0:
            raise ValueError('Персонаж сломлен по Телосложению и не может ремонтировать.')
        skill = c['sheet']['skills'].get('craft', 0)
        skill_count, penalties = skill_counts(skill, p['modifier'])
        gear = bonus(tool) if tool else 0
        sides = ([artifact(tool)] if tool and artifact(tool) else []) + p['artifacts']
        r = dict(id=secrets.token_hex(8), base=[die() for _ in range(base)], skillDice=[die() for _ in range(skill_count)],
                 gear=[die() for _ in range(gear)], penalty=[die() for _ in range(penalties)],
                 artifacts=[dict(sides=n, value=die(n)) for n in sides], pushed=False,
                 private=visibility(s, data) or bool(c.get('hidden')), skill='craft', attribute='str',
                 formula=dict(base=base, skill=skill, modifier=p['modifier'], gear=gear))
        score(r)
        item['version'] += 1
        p.update(status='rolled', private=r['private'], roll=r, stat=stat, signature=signature(c, tool))
        result = result_text(*score(r)) + ' Примите результат или пойдите на риск; ремонт ещё не применён.'
        r['diceEvent'] = publish(room, c['name'], 'Ремесло · ремонт: '+item['name'], pools(r), result,
                                 r['private'], risk=dict(action='repair', character=c['id'], item=item['id'], roll=r['id']))
    elif op in ('push', 'accept'):
        if p.get('status') != 'rolled' or p.get('roll', {}).get('id') != data.get('roll'):
            raise ValueError('Этот бросок ремонта уже завершён или устарел.')
        r = p['roll']
        if r['private'] and not gm:
            raise PermissionError('Скрытый бросок завершает Мастер.')
        tool = next((i for i in owned(room, c['id']) if i['id'] == p['tool']), None)
        if op == 'push':
            if r.get('pushed') or not can_push(r):
                raise ValueError('Нет костей для повторного броска. Примите результат ремонта.')
            if signature(c, tool) != p['signature'] or p['tool'] and not tool:
                raise ValueError('Персонаж или инструмент изменился. Примите исходный результат ремонта.')
            damage, wear = push(r, die)
            c['runtime']['current']['str'] = max(0, c['runtime']['current']['str']-damage)
            if c['kind'] == 'pc':
                c['runtime']['wp'] = min(10, c['runtime'].get('wp', 0)+damage)
            if tool and wear:
                tool['wear'] = tool.get('wear', 0)+wear
                tool['version'] += 1
            score(r)
        result = result_text(*score(r)) + ' ' + finish(room, c, item, r, p['stat'])
        if op == 'push':
            result += f' Риск: Телосложение −{r["damage"]}, износ инструмента +{r["wear"]}.'
        publish(room, c['name'], 'Ремонт · '+('риск' if op == 'push' else 'результат'),
                pools(r) if op == 'push' else [], result, r['private'])
    else:
        raise ValueError('Неизвестное действие ремонта.')
    room['journey']['gmReady'] = False
