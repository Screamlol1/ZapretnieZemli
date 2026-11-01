"""PHB 113: swimming, holding breath and drowning, measured in game time."""
import copy
import secrets
from dice_events import publish, pools, group
from dice_pools import skill_counts, result_text
from equipment_rules import owned, bonus, artifact
from risk_rules import push, score, can_push
import injuries


def die(sides=6):return secrets.randbelow(sides)+1
def exposure(c):return c.get('runtime',{}).get('waterExposure')
def alive(c):return c['kind']!='monster' and not c.get('runtime',{}).get('dead')
def active(room):return any(alive(c) and exposure(c) for c in room.get('characters',[]))
def due(room,c):return bool(alive(c) and exposure(c) and injuries.now(room)>=exposure(c)['nextAt'])
def fatal_due(room,c):return due(room,c) and exposure(c)['phase']=='broken'
def overdue(room):return any(due(room,c) for c in room.get('characters',[]) if c['kind']!='monster')
def round_minutes(room):return room.get('medicalRoundSeconds',10)/60
def interval(room,e):return 15 if e['phase']=='afloat' and not e['metalArmor'] else round_minutes(room)
def note(data):
    value=data.get('note','')
    if not isinstance(value,str) or not value.strip() or len(value)>500:raise ValueError('Опишите обстоятельства или помощь (до 500 символов).')
    return value.strip()
def log(room,c,message):room['log'].append(dict(name='Вода',text=f'{c["name"]}: {message}',private=bool(c.get('hidden'))))
def schedule(room,e,minutes=None):
    e['roundMinutes']=round_minutes(room)
    e['nextAt']=round(e['nextAt']+(interval(room,e) if minutes is None else minutes),4)
def pending_other(room):
    return bool(room.get('coldCheck') or room.get('treatment') or room.get('journeyRisk') or room.get('combat',{}).get('pendingRisk') or
                any(i.get('repair',{}).get('status')=='rolled' for i in room.get('items',[])))


def mark_broken(room,c,e,at):
    duration=die();e.update(phase='broken',brokenAt=at,deathMinutes=duration,deathAt=round(at+duration,4),nextAt=round(at+duration,4))
    result=f'Телосложение сломлено при утоплении. Срок спасения: {duration} игровых минут. Гибель подтверждает Мастер.'
    e['deathEvent']=publish(room,c['name'],'Утопление · смертельный срок',[group('table',[duration])],result,bool(c.get('hidden')))
    return result


def observe(room):
    # External damage (e.g. cold) can break an already drowning character.
    # The phase transition makes the D6 once-only across subsequent actions.
    for c in room.get('characters',[]):
        e=exposure(c)
        if alive(c) and e and e['phase']=='drowning' and injuries.current(c)['str']<=0:
            result=mark_broken(room,c,e,injuries.now(room));c['runtime']['waterLast']=dict(time=injuries.now(room),result=result)


def drown_damage(room,c,e,at):
    cur=injuries.current(c);cur['str']=max(0,cur['str']-1)
    if cur['str']<=0:return 'Утопление: Телосложение −1. '+mark_broken(room,c,e,at)
    e['phase']='drowning';schedule(room,e,round_minutes(room))
    return 'Утопление: Телосложение −1. Следующее повреждение через игровой раунд.'


def announce(room,c,p):
    r=p['roll'];positive,negative=score(r)
    r['pushAvailable']=bool(not r['pushed'] and not r['hits'] and can_push(r) and injuries.current(c)['str']>0)
    result=result_text(positive,negative)
    if r['pushed']:result+=f' Риск: Телосложение −{r["damage"]}, износ −{r["wear"]}.'
    result+=' Примите результат для применения последствий.'
    p['diceEvent']=publish(room,c['name'],'Стойкость · '+('держаться на воде' if p['phase']=='afloat' else 'задержать дыхание'),pools(r),result,p['private'],
                           risk=dict(action='water',character=c['id'],roll=p['id'],attribute='str'))


def apply(room,s,data):
    op=data.get('op');gm=s['role']=='gm'
    c=injuries.character(room,data.get('character'));rt=c['runtime'];cur=injuries.current(c)
    if not injuries.controls(c,s):raise PermissionError('Проверку выполняет владелец персонажа или Мастер.')
    e=exposure(c);p=room.get('waterCheck')
    if op=='configure':
        if not gm:raise PermissionError('Обстоятельства в воде задаёт Мастер.')
        if p or pending_other(room):raise ValueError('Сначала завершите текущую проверку.')
        if e and data.get('exposure')!=e['id'] or not e and data.get('exposure'):raise ValueError('Состояние в воде изменилось. Откройте актуальную карточку.')
        if rt.get('dead'):raise ValueError('Погибший персонаж не проходит проверки.')
        phase=e['phase'] if e else data.get('phase','afloat');metal=data.get('metalArmor',False);mod=data.get('modifier',0);description=note(data)
        if phase not in ('afloat','submerged','drowning','broken') or type(metal)!=bool or type(mod)!=int or not -10<=mod<=10:
            raise ValueError('Проверьте фазу, металлический доспех и модификатор от −10 до +10.')
        if not e and phase not in ('afloat','submerged'):raise ValueError('Начните на поверхности или под водой.')
        item=data.get('item','')
        if item and not any(i['id']==item for i in owned(room,c['id'])):raise ValueError('Предмет должен находиться у персонажа.')
        if e:
            e.update(metalArmor=metal,modifier=mod,item=item,note=description)
        else:
            rt['waterExposure']=dict(id=secrets.token_hex(12),phase=phase,metalArmor=metal,modifier=mod,item=item,note=description,nextAt=injuries.now(room),roundMinutes=round_minutes(room))
        log(room,c,'условия в воде уточнены без переноса срока. '+description if e else 'назначена первая проверка в воде сейчас. '+description)
        return
    if not e:raise ValueError('Сцена в воде уже завершена.')
    if op in ('submerge','rescue','confirmDeath','tick','advance'):
        if not gm:raise PermissionError('Последствия и игровое время подтверждает Мастер.')
        if p or pending_other(room):raise ValueError('Сначала завершите текущую проверку.')
        if data.get('exposure')!=e['id']:raise ValueError('Состояние в воде изменилось.')
        if op in ('tick','advance'):
            if type(data.get('nextAt')) not in (int,float) or data['nextAt']!=e['nextAt']:raise ValueError('Этот срок уже изменился. Откройте актуальную карточку.')
            if op=='advance':
                if room.get('combat',{}).get('phase') in ('setup','combat'):raise ValueError('В бою время идёт при смене раунда. Эта кнопка не заменяет боевой ход.')
                if due(room,c):raise ValueError('Сначала разрешите наступивший срок.')
                target=min(x['runtime']['waterExposure']['nextAt'] for x in room['characters'] if alive(x) and exposure(x))
                # Stop at a nearer cold deadline rather than jumping over it.
                cold=[x['runtime']['coldExposure']['nextAt'] for x in room['characters'] if alive(x) and x.get('runtime',{}).get('coldExposure')]
                if cold:target=min(target,*cold)
                if target<=injuries.now(room):raise ValueError('Сначала разрешите уже наступивший срок воды или холода.')
                injuries.advance(room,target-injuries.now(room))
                return
            if not due(room,c) or e['phase']!='drowning':raise ValueError('Повреждение от утопления ещё не наступило или уже учтено.')
            result=drown_damage(room,c,e,e['nextAt']);rt['waterLast']=dict(time=injuries.now(room),result=result)
            log(room,c,result);injuries.sync_battle(room,c);return
        if data.get('confirmed') is not True:raise ValueError('Подтвердите решение Мастера.')
        description=note(data)
        if op=='submerge':
            if e['phase']!='afloat' and not (e['phase']=='submerged' and cur['str']<=0):raise ValueError('Персонаж уже находится под водой.')
            e.update(phase='submerged',nextAt=injuries.now(room),note=description)
            result='погружение под воду подтверждено. '+description
            if cur['str']<=0:result+=' '+drown_damage(room,c,e,e['nextAt'])
            log(room,c,result);injuries.sync_battle(room,c);return
        if op=='confirmDeath':
            if not fatal_due(room,c):raise ValueError('Смертельный срок ещё не наступил.')
            rt['dead']=True;rt.pop('meditation',None);result='гибель от утопления подтверждена Мастером.'
        else:result='спасение из воды подтверждено. Повреждения сохраняются.'
        rt.pop('waterExposure');rt['waterLast']=dict(time=injuries.now(room),result=result,note=description)
        log(room,c,result+' '+description);injuries.sync_battle(room,c)
        from campaign_rules import try_cycle
        try_cycle(room);return
    if op=='roll':
        if p or pending_other(room):raise ValueError('Сначала завершите предыдущую проверку.')
        if data.get('exposure')!=e['id'] or not due(room,c) or e['phase'] not in ('afloat','submerged'):raise ValueError('Проверка ещё не наступила или нужна другая стадия спасения.')
        if cur['str']<=0:raise ValueError('Телосложение сломлено. Мастер должен разрешить погружение или спасение.')
        tool=next((i for i in owned(room,c['id']) if i['id']==e['item']),None)
        if e['item'] and (not tool or tool.get('quantity')!=1 or tool.get('bonus',0) and not bonus(tool)):raise ValueError('Предмет недоступен или сломан. Мастер должен уточнить условия.')
        count,penalties=skill_counts(c['sheet']['skills'].get('endure',0),e['modifier'],injuries.modifiers(c,'endure','str'))
        sides=artifact(tool) if tool else 0
        r=dict(id=secrets.token_hex(12),base=[die() for _ in range(cur['str'])],skillDice=[die() for _ in range(count)],gear=[die() for _ in range(bonus(tool) if tool else 0)],penalty=[die() for _ in range(penalties)],artifacts=[dict(sides=sides,value=die(sides))] if sides else [],pushed=False,skill='endure',attribute='str')
        p=dict(id=r['id'],character=c['id'],exposure=e['id'],phase=e['phase'],roll=r,private=bool(c.get('hidden')),item=e['item'],signature=injuries.signature(c,tool))
        room['waterCheck']=p;announce(room,c,p);return
    if op not in ('push','accept') or not p or p['id']!=data.get('roll') or p['character']!=c['id'] or p['exposure']!=e['id']:
        raise ValueError('Бросок уже завершён или изменился.')
    r=p['roll'];tool=next((i for i in owned(room,c['id']) if i['id']==p['item']),None)
    if op=='push':
        if p['signature']!=injuries.signature(c,tool) or p['item'] and not tool:raise ValueError('Персонаж или предмет изменились. Примите исходный результат.')
        if not r.get('pushAvailable'):raise ValueError('Пойти на риск уже нельзя.')
        damage,wear=push(r,die);cur['str']=max(0,cur['str']-damage)
        if c['kind']=='pc':rt['wp']=min(10,rt.get('wp',0)+damage)
        if tool and wear:tool['wear']=min(tool['bonus'],tool.get('wear',0)+wear);tool['version']+=1
        p['signature']=injuries.signature(c,tool);announce(room,c,p);injuries.sync_battle(room,c);return
    if r['hits']:
        result='Персонаж удержался на воде.' if e['phase']=='afloat' else 'Дыхание удержано.'
        schedule(room,e)
    elif e['phase']=='afloat':
        e['phase']='submerged';schedule(room,e)
        result='Персонаж погрузился под воду. Через раунд понадобится проверка дыхания.'
    else:
        result=drown_damage(room,c,e,e['nextAt'])
    if cur['str']<=0 and e['phase'] in ('afloat','submerged'):
        result+=' Телосложение сломлено: Мастер должен разрешить спасение или подтвердить, что герой захлебнулся.'
    event=next((x for x in room.get('diceRolls',[]) if x['id']==p['diceEvent']),None)
    if event:event['result']+=' '+result;event.pop('risk',None)
    rt['waterLast']=dict(time=injuries.now(room),result=result,hits=r['hits'],diceEvent=p['diceEvent'])
    log(room,c,result);room.pop('waterCheck');injuries.sync_battle(room,c)


def project(room,s):
    targets=[];room['waterWaiting']=any(c.get('hidden') and due(room,c) for c in room['characters'] if c['kind']!='monster')
    room['waterTravelBlocked']=active(room)
    for c in room['characters']:
        if c['kind']=='monster' or c.get('hidden') and s['role']!='gm':continue
        e=exposure(c)
        if not e:continue
        e.update(due=due(room,c),fatalDue=fatal_due(room,c),intervalMinutes=interval(room,e),roundMinutes=round_minutes(room))
        targets.append(dict(id=c['id'],name=c['name'],owner=c['owner'],kind=c['kind'],dead=bool(c['runtime'].get('dead')),exposure={k:copy.deepcopy(v) for k,v in e.items() if k!='item'}))
    room['waterTargets']=targets
    p=room.get('waterCheck')
    if p:
        p.pop('signature',None)
        if p['private'] and s['role']!='gm':room['waterCheck']=dict(waiting=True)
