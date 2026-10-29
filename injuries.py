"""Persistent injuries, aid and elapsed in-world time (PHB pp. 56–57, 62, 107–110).

No real-world timer runs while players are away. Situational trauma effects are
explicit GM decisions; fixed penalties and deadlines are stored mechanically.
"""
import copy
import json
import math
import secrets
from dice_events import visibility, publish, pools, group
from dice_pools import skill_counts, result_text, artifact_sides
from equipment_rules import bonus, artifact, owned
from risk_rules import push, score, can_push
from injuries_data import TABLES, LABELS, lookup

ATTRS=('str','agi','wit','emp')
NAMES=dict(str='Телосложение',agi='Ловкость',wit='Разум',emp='Эмпатия')
UNITS=dict(minutes=1,turns=15,hours=60,days=1440)

def die(sides=6): return secrets.randbelow(sides)+1
def now(room): return room.get('medicalClock',0)
def current(c): return c.setdefault('runtime',{}).setdefault('current',dict(c['sheet']['attrs']))
def active(c): return [i for i in c.get('runtime',{}).get('injuries',[]) if i.get('status') in ('active','pending')]
def log(room,c,text): room.setdefault('log',[]).append(dict(name='Лечение',text=f'{c["name"]}: {text}',private=bool(c.get('hidden'))))

def character(room,cid):
    c=next((c for c in room['characters'] if c['id']==cid and c['kind']!='monster'),None)
    if not c:raise ValueError('Выберите героя или персонажа ведущего.')
    return c

def controls(c,s): return s['role']=='gm' or c['kind']=='pc' and c['owner']==s['owner'] and not c.get('hidden')

def modifiers(c,skill,attribute):
    return sum(i.get('mechanics',{}).get('modifiers',{}).get(skill,0)+i.get('mechanics',{}).get('attributeModifiers',{}).get(attribute,0) for i in active(c))

def blocked(c):
    return bool(c.get('runtime',{}).get('dead') or any(i.get('overdue') or i.get('mechanics',{}).get('incapacitated') for i in active(c)) or c.get('runtime',{}).get('meditation'))

def check_allowed(c):
    if blocked(c):raise ValueError('Персонаж сейчас не может действовать: проверьте травмы или медитацию.')
    if any(v<=0 for v in current(c).values()):raise ValueError('Сломленный персонаж не может выполнять проверки. Сначала нужна помощь или восстановление.')

def check_pain(room,c,skill):
    damage=sum(skill in i.get('mechanics',{}).get('damageSkills',[]) for i in active(c))
    if damage:
        current(c)['str']=max(0,current(c)['str']-damage)
        log(room,c,f'боль при проверке: Телосложение −{damage}.')
    return damage

def snapshot(room):
    t=room.get('journey',{});b=room.get('combat',{})
    return dict(attrs={c['id']:dict(c.get('runtime',{}).get('current',{})) for c in room['characters']},
                items={i['id']:i.get('location',{}).get('id') for i in room.get('items',[])},
                quarter=t.get('day',1)*4+t.get('quarter',0),round=b.get('round',0),combat=b.get('id'),phase=b.get('phase'))

def pending_injury(room,c,attribute,table=None,source='damage'):
    i=dict(id=secrets.token_hex(8),status='pending',attribute=attribute,table=table or ('horror' if attribute=='wit' else ''),
           name='Травма требует решения Мастера',created=now(room),source=source)
    c['runtime'].setdefault('injuries',[]).append(i)
    log(room,c,'сломан '+NAMES[attribute]+'. Мастер должен определить критическую травму.')
    return i

def reconcile(room,before,data):
    """Call once after a successful action, before saving; snapshot precedes it."""
    t=room.get('journey',{});b=room.get('combat',{})
    quarters=max(0,t.get('day',1)*4+t.get('quarter',0)-before['quarter'])
    rounds=max(0,b.get('round',0)-before['round']) if before['phase']=='combat' else 0
    # PHB p. 84: a round lasts 10–60 seconds, chosen for the circumstances.
    # An individual activation is not the PHB's 15-minute exploration turn.
    if quarters or rounds:advance(room,quarters*360+rounds*room.get('medicalRoundSeconds',10)/60)
    raw_events=b.pop('injuryEvents',[])
    processed=room.get('medicalProcessedEvents',[])
    events=[e for e in raw_events if not e.get('id') or e['id'] not in processed]
    room['medicalProcessedEvents']=(processed+[e['id'] for e in events if e.get('id')])[-2000:]
    broken_targets={c['id'] for c in room['characters'] if any(before['attrs'].get(c['id'],{}).get(a,0)>0 and c.get('runtime',{}).get('current',{}).get(a,0)<=0 for a in ATTRS)}
    # Attack/push events also record a Broken orc that has already stood up.
    # Axe Fighter can cause a critical injury without breaking the prey.
    broken_targets.update(e['character'] for e in events if e.get('character') and e.get('source')!='axeTalent')
    for hunter in room['characters']:
        prey=hunter.get('runtime',{}).get('prey')
        if prey and prey.get('target') in broken_targets:
            hunter['runtime'].pop('prey',None)
            unit=next((u for u in b.get('units',[]) if u['id']==hunter['id']),None)
            if unit is not None:unit.pop('prey',None)
            target=next((c for c in room['characters'] if c['id']==prey['target']),{})
            room.setdefault('log',[]).append(dict(name=hunter['name'],text='Добыча сломлена: Охотничье чутьё больше не даёт бонуса этой цели.',private=bool(hunter.get('hidden') or target.get('hidden'))))
    action=data.get('action','');command=data.get('command',{})
    pushing=(action in ('characterPush','opposedPush','travelRisk','freePush') or action=='inventoryRepair' and data.get('op')=='push'
             or action=='injury' and data.get('op')=='push' or action=='combatAction' and command.get('action')=='risk' and command.get('push'))
    for c in room['characters']:
        if c['kind']=='monster':continue
        rt=c.setdefault('runtime',{});cur=current(c);old=before['attrs'].get(c['id'],{})
        episodes=rt.setdefault('brokenRecovery',{})
        resolved_events=set()
        for attr in ATTRS:
            if cur.get(attr,0)>0:
                episodes.pop(attr,None)
                continue
            if old.get(attr,0)<=0:continue
            episodes[attr]=dict(id=secrets.token_hex(8),due=now(room)+die()*60,created=now(room),attempts=[],orcReady=c['sheet'].get('kin')=='orc')
            if attr not in ('str','wit'):continue
            event=next((e for e in events if e.get('character')==c['id'] and e.get('attribute')==attr),None)
            replayed=not event and any(e.get('character')==c['id'] and e.get('attribute')==attr and e.get('id') in processed for e in raw_events)
            # Attacks accepted after a push can injure the target; only the
            # pushing actor's self-damage is excluded, never the whole attack.
            is_push=event and event.get('source')=='push'
            if not event and pushing:
                actor=(command.get('actor') or (room.get('combat',{}).get('event') or {}).get('actor')) if action=='combatAction' else data.get('character') or data.get('id') or room.get('treatment',{}).get('healer')
                if action=='inventoryRepair':actor=before.get('items',{}).get(data.get('id'))
                if action=='opposedPush':
                    pair=next((p for p in room.get('opposedChecks',[]) if p['id']==data.get('id')),None)
                    actor=pair.get('attacker',{}).get('character') if pair else None
                is_push=not actor or actor==c['id']
            condition=action.startswith('travel') and not event
            if is_push or condition or replayed:continue
            pending_injury(room,c,attr,event.get('table') if event else None)
            resolved_events.add(attr)
        # An orc may recover immediately on being Broken; the injury still
        # happened even though the persisted attribute is positive again.
        for event in events:
            attr=event.get('attribute')
            if event.get('character')==c['id'] and attr in ('str','wit') and attr not in resolved_events and event.get('source')!='push':
                pending_injury(room,c,attr,event.get('table'),event.get('source','damage'))
                resolved_events.add(attr)
        unit=next((u for u in b.get('units',[]) if u['id']==c['id']),None)
        if unit is not None:
            unit['injuries']=copy.deepcopy(active(c));unit['dead']=bool(rt.get('dead'));unit['meditating']=bool(rt.get('meditation'))

def advance(room,minutes):
    if type(minutes) not in (int,float) or not math.isfinite(minutes) or not 0<=minutes<=525600:
        raise ValueError('Укажите прошедшее игровое время от 0 до 525600 минут.')
    room['medicalClock']=round(now(room)+minutes,4)
    for c in room['characters']:
        if c['kind']=='monster':continue
        rt=c.setdefault('runtime',{});cur=current(c)
        if minutes:
            for episode in rt.get('brokenRecovery',{}).values():episode['orcReady']=False
        for i in active(c):
            if i['status']=='pending':continue
            if i.get('deathAt') is not None and not i.get('stabilized') and now(room)>=i['deathAt']:
                i['overdue']=True
                continue
            if i.get('healAt') is not None and now(room)>=i['healAt']:
                if i.get('special')=='neck' and not i.get('cared'):
                    i.update(permanent=True,healAt=None)
                    log(room,c,f'{i["name"]}: срок помощи истёк, последствие стало постоянным.')
                else:
                    i.update(status='healed',healedAt=now(room))
                    log(room,c,f'{i["name"]}: срок восстановления завершён.')
        if rt.get('dead') or blocked(c):continue
        for attr,episode in list(rt.get('brokenRecovery',{}).items()):
            if now(room)>=episode['due']:
                if cur.get(attr,0)<=0:cur[attr]=1;log(room,c,f'самостоятельное восстановление: {NAMES[attr]} 1.')
                del rt['brokenRecovery'][attr]
        sync_battle(room,c)

def sync_battle(room,c):
    b=room.get('combat',{});u=next((u for u in b.get('units',[]) if u['id']==c['id']),None)
    if not u:return
    cur=current(c)
    for a,k in (('str','str'),('agi','agi'),('wit','wits'),('emp','emp')):u[k]=cur[a]
    u['wp']=c['runtime'].get('wp',0)
    u['injuries']=copy.deepcopy(active(c));u['dead']=bool(c['runtime'].get('dead'));u['meditating']=bool(c['runtime'].get('meditation'))
    room['combatRevision']=room.get('combatRevision',0)+1

def assign(room,c,data):
    table=data.get('table');value=data.get('result')
    dice=[die(),die()] if value is None else []
    value=dice[0]*10+dice[1] if dice else value
    rule=lookup(table,value)
    pending=next((i for i in active(c) if i['id']==data.get('injury') and i['status']=='pending'),None)
    if data.get('injury') and not pending:raise ValueError('Травма уже определена или не найдена.')
    if len(active(c))>=30 and not pending:raise ValueError('Не более 30 действующих травм.')
    i=pending or dict(id=secrets.token_hex(8),created=now(room))
    mechanics={k:copy.deepcopy(rule[k]) for k in ('modifiers','attributeModifiers','runSlow','noTwoHand','damageSkills','incapacitated')}
    if rule['special']=='neck':mechanics.update(incapacitated=False,paralyzed=True)
    days=sum(die() for _ in range(rule['days']))
    limit=die()*UNITS[rule['lethal']] if rule['lethal'] else None
    i.update(status='active',table=table,result=value,name=rule['name'],mechanics=mechanics,effect=rule['effect'],special=rule['special'],
             permanent=rule['permanent'],healingPenalty=rule['healingPenalty'],stabilized=False,attempts={},
             healAt=now(room)+days*1440 if days else None,deathAt=now(room)+limit if limit else None,
             instant=rule['instant'],overdue=rule['instant'],cared=False)
    i['regrowRequired']=table=='slash' and (45<=value<=46 or 55<=value<=56 or 61<=value<=62)
    if not pending:c['runtime'].setdefault('injuries',[]).append(i)
    if not days and not rule['permanent'] and not rule['lethal'] and not rule['instant']:i.update(status='healed',healedAt=now(room))
    if dice:publish(room,c['name'],'Критическая травма',[group('table',dice)],f'{LABELS[table]} · {value}: {i["name"]}',bool(c.get('hidden')))
    log(room,c,f'{i["name"]} ({LABELS[table]}, {value}); '+('смертельный результат — подтвердите исход.' if i['instant'] else 'последствия сохранены в листе.'))
    sync_battle(room,c)
    return i

def signature(c,tool):
    return json.dumps([c['sheet'],current(c),c['runtime'].get('wp',0),tool.get('version') if tool else None],sort_keys=True)

def find_injury(c,iid):
    i=next((i for i in active(c) if i['id']==iid and i['status']=='active'),None)
    if not i:raise ValueError('Действующая травма не найдена.')
    return i

def begin_treatment(room,s,data):
    if room.get('treatment'):raise ValueError('Сначала завершите текущую проверку лечения.')
    healer=character(room,data.get('healer'));target=character(room,data.get('target'))
    if not controls(healer,s):raise PermissionError('Можно бросать только за своего целителя.')
    if target.get('hidden') and s['role']!='gm':raise PermissionError('Этот персонаж недоступен.')
    if target['runtime'].get('dead'):raise ValueError('Обычное лечение не возвращает умерших.')
    check_allowed(healer)
    if any(i.get('repair',{}).get('status')=='rolled' and i['repair'].get('character')==healer['id'] for i in room.get('items',[])):
        raise ValueError('Сначала завершите ремонт целителя.')
    purpose=data.get('purpose');attr=data.get('attribute');injury=None
    if purpose=='recover':
        if healer['id']==target['id'] or attr not in ATTRS or current(target)[attr]>0:
            raise ValueError('Помощь нужна другому персонажу со сломленной характеристикой.')
        episode=target['runtime'].setdefault('brokenRecovery',{}).setdefault(attr,dict(id=secrets.token_hex(8),due=now(room)+die()*60,attempts=[]))
        attempted=episode['attempts'];skill='heal' if attr in ('str','agi') else 'perform'
        penalty=0
    elif purpose in ('save','care'):
        injury=find_injury(target,data.get('injury'));skill='heal'
        if injury.get('instant') or injury.get('overdue'):raise ValueError('Срок спасения истёк: сначала Мастер должен подтвердить исход и игровое время.')
        if purpose=='save' and (not injury.get('deathAt') or injury.get('stabilized')):raise ValueError('Этой травме уже не требуется спасение жизни.')
        if purpose=='care' and (injury.get('cared') or not injury.get('healAt')):raise ValueError('Срок этой травмы уже сокращён или не сокращается обычным уходом.')
        attempted=injury.setdefault('attempts',{}).setdefault(purpose,[])
        penalty=(injury.get('healingPenalty',0) if purpose=='save' else 0)+(-2 if healer['id']==target['id'] else 0)
    else:raise ValueError('Выберите цель лечения.')
    if skill=='heal' and any(i.get('mechanics',{}).get('paralyzed') for i in active(healer)):
        raise ValueError('Парализованный целитель не может оказывать физическую помощь.')
    if healer['id'] in attempted:raise ValueError('Этот целитель уже пробовал помочь с этой задачей. Нужен другой целитель.')
    if data.get('nearby') is not True:raise ValueError('Подтвердите, что целитель находится рядом и может оказать помощь.')
    mod=data.get('modifier',0)
    if type(mod)!=int or not -10<=mod<=10 or mod and s['role']!='gm':raise ValueError('Дополнительные обстоятельства проверки задаёт Мастер.')
    tool=next((i for i in owned(room,healer['id']) if i['id']==data.get('tool')),None)
    if data.get('tool') and (not tool or tool.get('quantity')!=1 or tool.get('bonus',0) and not bonus(tool)):
        raise ValueError('Инструмент недоступен или сломан.')
    extras=artifact_sides(data)
    if extras and s['role']!='gm':raise PermissionError('Дополнительные артефактные кости добавляет Мастер.')
    sides=artifact(tool) if tool else 0
    if len(extras)+bool(sides)>10:raise ValueError('Не более десяти артефактных костей.')
    b=room.get('combat',{});unit=next((u for u in b.get('units',[]) if u['id']==healer['id']),None)
    if b.get('phase')=='combat':
        victim=next((u for u in b['units'] if u['id']==target['id']),None)
        if b.get('pendingRisk') or not unit or not victim or not b.get('order') or b['order'][b['turn']]!=unit['id'] or unit['slow']<1:
            raise ValueError('Для помощи в бою нужен ваш ход и медленное действие без незавершённых бросков.')
        dq=unit['q']-victim['q'];dr=unit['r']-victim['r']
        if max(abs(dq),abs(dr),abs(dq+dr))>1:raise ValueError('Подойдите к пострадавшему вплотную.')
        if purpose=='care':raise ValueError('Уход для сокращения срока травмы выполняется вне боя.')
        unit['slow']-=1;b['roundStarted']=True;b['activationStarted']=True;b.pop('initiativeOffer',None)
        room['combatRevision']=room.get('combatRevision',0)+1
    elif b.get('phase')=='setup':raise ValueError('Завершите подготовку боя перед лечением.')
    if room.get('journey',{}).get('phase')=='resolving':raise ValueError('Сначала завершите проверки текущей четверти суток.')
    skill_n,penalty_n=skill_counts(healer['sheet']['skills'].get(skill,0),penalty,mod,modifiers(healer,skill,'emp'))
    r=dict(id=secrets.token_hex(8),base=[die() for _ in range(current(healer)['emp'])],skillDice=[die() for _ in range(skill_n)],gear=[die() for _ in range(bonus(tool) if tool else 0)],
           penalty=[die() for _ in range(penalty_n)],artifacts=[dict(sides=n,value=die(n)) for n in (([sides] if sides else [])+extras)],pushed=False,attribute='emp',skill=skill)
    score(r);attempted.append(healer['id'])
    private=visibility(s,data) or bool(healer.get('hidden') or target.get('hidden'))
    treatment=dict(healer=healer['id'],target=target['id'],purpose=purpose,attribute=attr,injury=injury['id'] if injury else None,
                   tool=tool['id'] if tool else '',signature=signature(healer,tool),private=private,roll=r,owner=healer['owner'])
    room['treatment']=treatment
    announce(room,healer,treatment)

def announce(room,c,p):
    r=p['roll'];positive,negative=score(r)
    target=character(room,p['target'])
    r['pushAvailable']=not r['pushed'] and can_push(r) and (r['hits']==0 or p['purpose']=='recover' and r['hits']<target['sheet']['attrs'][p['attribute']])
    result=result_text(positive,negative)
    if r['pushed']:result+=f' Риск: Эмпатия −{r["damage"]}, износ −{r["wear"]}.'
    publish(room,c['name'],'Лечение · '+dict(recover='помощь сломленному',save='спасение жизни',care='уход')[p['purpose']],pools(r),result,p['private'],
            risk=dict(action='treatment',character=c['id'],roll=r['id'],attribute='emp'))

def finish_treatment(room,s,data):
    p=room.get('treatment')
    if not p or p['roll']['id']!=data.get('roll'):raise ValueError('Эта проверка лечения уже завершена.')
    c=character(room,p['healer']);target=character(room,p['target']);r=p['roll']
    if not controls(c,s) or p['private'] and s['role']!='gm':raise PermissionError('Решение принимает владелец целителя или Мастер.')
    tool=next((i for i in owned(room,c['id']) if i['id']==p['tool']),None)
    if data['op']=='push':
        if r['pushed'] or not can_push(r) or not r.get('pushAvailable',True):raise ValueError('Риск недоступен: повтор уже был или дополнительные успехи не увеличат эффект помощи.')
        if p['signature']!=signature(c,tool) or p['tool'] and not tool:raise ValueError('Целитель или инструмент изменился. Примите исходный результат.')
        damage,wear=push(r,die);current(c)['emp']=max(0,current(c)['emp']-damage)
        if c['kind']=='pc':c['runtime']['wp']=min(10,c['runtime'].get('wp',0)+damage)
        if tool and wear:tool['wear']=tool.get('wear',0)+wear;tool['version']+=1
        score(r);announce(room,c,p)
    result='Помощь не удалась. Этот целитель больше не может повторять данную попытку.'
    if r['hits']:
        if p['purpose']=='recover':
            attr=p['attribute'];current(target)[attr]=min(target['sheet']['attrs'][attr],r['hits'])
            target['runtime'].get('brokenRecovery',{}).pop(attr,None)
            result=f'{NAMES[attr]} восстановлено до {current(target)[attr]}.'
        else:
            i=find_injury(target,p['injury'])
            if p['purpose']=='save':
                i['stabilized']=True;i['overdue']=False
                if i['table']=='other':i['mechanics']['incapacitated']=False;i['status']='healed'
                result='Угроза жизни устранена. Утраченную характеристику и срок травмы лечат отдельно.'
            else:
                i['healAt']=now(room)+max(0,i['healAt']-now(room))/2;i['cared']=True
                result='Оставшийся срок травмы уменьшен вдвое.'
    if not p['private']:target['runtime']['lastTreatment']=dict(healer=c['name'],purpose=p['purpose'],result=result,hits=r['hits'],time=now(room))
    room.setdefault('log',[]).append(dict(name='Лечение',text=f'{target["name"]}: {result}',private=p['private']))
    room.pop('treatment',None);sync_battle(room,c);sync_battle(room,target)

def apply(room,s,data):
    op=data.get('op');gm=s['role']=='gm'
    if not isinstance(op,str):raise ValueError('Выберите действие лечения.')
    if op=='treat':return begin_treatment(room,s,data)
    if op in ('push','accept'):return finish_treatment(room,s,data)
    if room.get('treatment'):raise ValueError('Сначала завершите проверку лечения.')
    if op=='advance':
        if not gm:raise PermissionError('Игровое время изменяет Мастер.')
        if not isinstance(data.get('note'),str) or not data['note'].strip():raise ValueError('Укажите, где прошло это время.')
        if 'roundSeconds' in data:
            if type(data['roundSeconds'])!=int or not 10<=data['roundSeconds']<=60:raise ValueError('Раунд длится от 10 до 60 секунд по обстоятельствам.')
            room['medicalRoundSeconds']=data['roundSeconds']
        advance(room,data.get('minutes'))
        room.setdefault('log',[]).append(dict(name='Лечение',text=f'Прошло {data["minutes"]} мин. {data["note"][:300]}'))
        return
    c=character(room,data.get('character'));rt=c.setdefault('runtime',{})
    if op=='orcRecover':
        if not controls(c,s):raise PermissionError('Доступно владельцу орка или Мастеру.')
        attr=data.get('attribute');wp=data.get('wp')
        episode=rt.get('brokenRecovery',{}).get(attr,{}) if isinstance(attr,str) else {}
        if c['sheet'].get('kin')!='orc' or not episode.get('orcReady') or current(c).get(attr,1)>0:
            raise ValueError('Несгибаемость используется сразу после того, как орк сломлен.')
        if rt.get('dead') or any(i.get('overdue') for i in active(c)):raise ValueError('Сначала Мастер должен разрешить смертельный исход.')
        if room.get('combat',{}).get('phase')=='combat':raise ValueError('В бою используйте Несгибаемость в окне боевого решения.')
        npc=c['kind']=='npc'
        if type(wp)!=int or not 1<=wp<=min(1 if npc else rt.get('wp',0),c['sheet']['attrs'][attr]):raise ValueError('Потратьте от 1 СВ до значения сломленной характеристики; СВ должно хватать. ПВ восстанавливает 1 пункт без СВ.')
        if not npc:rt['wp']-=wp
        current(c)[attr]=wp;rt['brokenRecovery'].pop(attr,None)
        log(room,c,f'Несгибаемость: {NAMES[attr]} восстановлено до {wp}'+(' без СВ (ПВ)' if npc else f' за {wp} СВ')+'. Травмы сохраняются.')
        return
    if op.startswith('meditat'):
        if not controls(c,s):raise PermissionError('Доступно владельцу эльфа или Мастеру.')
        if c['sheet'].get('kin')!='elf':raise ValueError('Внутренний покой доступен эльфам.')
        if op=='meditate':
            if rt.get('dead') or rt.get('meditation') or c['kind']=='pc' and rt.get('wp',0)<1:raise ValueError('Для медитации нужны 1 СВ и живой эльф без текущей медитации.')
            if room.get('combat',{}).get('phase') in ('setup','combat'):raise ValueError('Медитация требует четверти суток покоя вне боя.')
            if room.get('journey',{}).get('phase')=='resolving':raise ValueError('Начинайте медитацию перед действиями четверти, а не после их выполнения.')
            if c['kind']=='pc':rt['wp']-=1
            rt['meditation']=dict(start=now(room),due=now(room)+360)
            log(room,c,'начал эльфийскую медитацию'+(' за 1 СВ' if c['kind']=='pc' else ' без СВ (ПВ)')+'. Нужны шесть часов без помех.')
        elif op=='meditationCancel':
            if not rt.get('meditation'):raise ValueError('Медитация не начата.')
            rt.pop('meditation');log(room,c,'медитация прервана; потраченная СВ не возвращается.')
        elif op=='meditationFinish':
            if not gm:raise PermissionError('Мастер подтверждает, что медитация прошла без помех.')
            if not rt.get('meditation') or now(room)<rt['meditation']['due'] or data.get('undisturbed') is not True:
                raise ValueError('Должны пройти шесть игровых часов; подтвердите отсутствие помех.')
            if any(i.get('overdue') or i['status']=='pending' for i in active(c)):raise ValueError('Сначала разрешите неопределённые и смертельные травмы, срок которых истёк во время медитации.')
            rt['current']=dict(c['sheet']['attrs']);rt['brokenRecovery']={};rt.pop('meditation')
            for i in active(c):
                if i.get('regrowRequired'):i.update(stabilized=True,overdue=False,healAt=None)
                else:i.update(status='healed',healedAt=now(room),stabilized=True)
            log(room,c,'Внутренний покой восстановил характеристики и исцелил травмы; утраченные конечности не отрастают (официальное исправление, с. 62).')
        else:raise ValueError('Неизвестное действие медитации.')
        sync_battle(room,c);return
    if not gm:raise PermissionError('Критические травмы разрешает Мастер.')
    if op=='assign':return assign(room,c,data)
    i=find_injury(c,data.get('injury'))
    if op=='resolve':
        note=data.get('note','')
        if not isinstance(note,str) or not note.strip() or len(note)>500:raise ValueError('Укажите основание решения Мастера.')
        outcome=data.get('outcome')
        if outcome=='dead':
            if not i.get('overdue'):raise ValueError('Смертельный срок этой травмы ещё не истёк.')
            rt['dead']=True;i['status']='fatal';rt.pop('meditation',None)
        elif outcome=='healed':i.update(status='healed',healedAt=now(room),stabilized=True)
        elif outcome=='extend':
            minutes=data.get('minutes')
            if type(minutes)!=int or not 1<=minutes<=1440 or i.get('instant'):raise ValueError('Уточните оставшееся время: 1–1440 минут; мгновенную смерть нельзя продлевать.')
            i.update(deathAt=now(room)+minutes,overdue=False)
        else:raise ValueError('Выберите исход травмы.')
        log(room,c,f'{i["name"]}: {dict(dead="смерть подтверждена",healed="исцеление подтверждено",extend="срок спасения уточнён")[outcome]}. {note.strip()}')
        sync_battle(room,c);return
    if op=='effect':
        amount=data.get('damage');attribute=data.get('attribute');note=data.get('note','')
        if type(amount)!=int or not 0<=amount<=20 or attribute not in ATTRS or not isinstance(note,str) or not note.strip() or len(note)>300:
            raise ValueError('Укажите характеристику, урон 0–20 и причину срабатывания эффекта травмы.')
        current(c)[attribute]=max(0,current(c)[attribute]-amount);log(room,c,f'{i["name"]}: {note}; {NAMES[attribute]} −{amount}.');sync_battle(room,c);return
    raise ValueError('Неизвестное действие лечения.')

def redact(room,s):
    """Run before stripping other characters' sheets/runtime in Game.view."""
    targets=[];room.pop('medicalProcessedEvents',None)
    for c in room['characters']:
        if c['kind']=='monster' or c.get('hidden') and s['role']!='gm':continue
        rt=c.get('runtime',{});cur=rt.get('current',{})
        if s['role']!='gm':
            # Attempts can include an unrevealed GM-controlled helper. Only the
            # server needs these IDs to enforce once-per-healer attempts.
            for i in rt.get('injuries',[]):i.pop('attempts',None)
            for episode in rt.get('brokenRecovery',{}).values():episode.pop('attempts',None)
        targets.append(dict(id=c['id'],name=c['name'],kind=c['kind'],owner=c['owner'],dead=bool(rt.get('dead')),
                            broken=[a for a in ATTRS if cur.get(a,1)<=0],injuries=copy.deepcopy(active(c)),
                            recovery=copy.deepcopy(rt.get('brokenRecovery',{})),meditation=copy.deepcopy(rt.get('meditation'))))
    room['medicalTargets']=targets
    p=room.get('treatment')
    if p:
        p.pop('signature',None)
        if p.get('private') and s['role']!='gm':room['treatment']=dict(waiting=True)
