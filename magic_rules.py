"""Persistent spell declarations, casting and explicit adjudication (PHB 117–142).

The catalog distinguishes computed effects from descriptive/GM effects. No client
supplies dice, power, school rank, costs or automatic damage. Rituals use game
time. Generic casting is deliberately separate from ordinary pushable checks.
"""
import copy
import json
import secrets
from pathlib import Path
import injuries
from dice_events import visibility, publish, group
from inventory_rules import text

CATALOG=json.loads((Path(__file__).parent/'public'/'spell-catalog.json').read_text(encoding='utf-8'))
SPELLS={v['id']:v for v in CATALOG['spells']}
SCHOOLS=tuple(k for k in CATALOG['schools'] if k!='general')
ATTRIBUTES=('str','agi','wit','emp')
NAMES=dict(str='Телосложение',agi='Ловкость',wit='Разум',emp='Эмпатия')
UNIT_ATTR=dict(str='str',agi='agi',wit='wits',emp='emp')
PENDING={'requested','approved','ritual','rolled'}

def die(sides=6):return secrets.randbelow(sides)+1
def now(room):return room.get('medicalClock',0)
def quarter(room):
    t=room.get('journey',{})
    return t.get('day',1)*4+t.get('quarter',0)
def character(room,cid):
    c=next((c for c in room['characters'] if c['id']==cid),None)
    if not c:raise ValueError('Персонаж не найден.')
    return c
def controls(c,s):return s['role']=='gm' or c['kind']=='pc' and c.get('owner')==s.get('owner') and not c.get('hidden')
def gm(s):
    if s['role']!='gm':raise PermissionError('Это решение принимает Мастер.')
def integer(v,low,high):
    if type(v)!=int or not low<=v<=high:raise ValueError('Некорректное число для заклинания.')
    return v
def rank(c,school):
    if c['kind']=='monster' or c['kind']=='npc' and not c['sheet'].get('npcTalentsConfigured'):return 0
    sh=c['sheet'];p=sh.get('paths',{}).copy()
    p[sh.get('path','')]=max(p.get(sh.get('path',''),0),sh.get('pathRank',0))
    return max((p.get(k,0) for k in (*SCHOOLS,'ice','elements')),default=0) if school=='general' else p.get(school,0)
def pool(room,c):return room.get('magicWillpower',0) if c['kind']=='npc' else c['runtime'].get('wp',0)
def log(room,r,message):room.setdefault('log',[]).append(dict(name='Магия',text=message,private=r.get('private',False)))
def unit(room,cid):return next((u for u in room.get('combat',{}).get('units',[]) if u['id']==cid),None)
def in_battle(room,c):return room.get('combat',{}).get('phase')=='combat' and bool(unit(room,c['id']))
def owned_item(room,c,iid):
    item=next((i for i in room.get('items',[]) if i['id']==iid and i.get('location')==dict(kind='character',id=c['id']) and i.get('quantity',0)>0),None)
    if not item:raise ValueError('Ингредиент или гримуар отсутствует в инвентаре заклинателя.')
    return item
def signature(room,r):
    c=character(room,r['character']);target=character(room,r['target']) if r.get('target') else None
    def snapshot(x):return [x.get('sheet'),x.get('runtime',{}).get('current'),x.get('runtime',{}).get('wp'),x.get('runtime',{}).get('dead'),x.get('runtime',{}).get('injuries'),x.get('runtime',{}).get('magicEffects')]
    items=[owned_item(room,c,i) for i in (r.get('ingredientItem'),r.get('grimoire')) if i]
    b=room.get('combat',{});u=unit(room,c['id'])
    return json.dumps([snapshot(c),snapshot(target) if target else None,items,pool(room,c),
        [room.get('combatRevision'),b.get('id'),b.get('phase'),b.get('round'),b.get('turn'),b.get('order'),u.get('fast'),u.get('slow'),u.get('q'),u.get('r')] if u else None],sort_keys=True)
def formula(room,r):
    c=character(room,r['character']);sp=SPELLS[r['spell']];school=rank(c,sp['school'])
    effective=max(0,sp['rank']-int(bool(r.get('grimoire'))))
    halfelf=int(c['sheet'].get('kin')=='halfelf')
    base=r['wp']+halfelf
    binding=r.get('bind',0)
    dice=max(0,base+binding-(max(0,school-effective) if r.get('safe') else 0))
    return dict(rank=school,effectiveRank=effective,halfelf=halfelf,base=base,dice=dice,cost=r['wp']+binding+int(r.get('obscure',False))+int(r.get('extend',False)),chance=effective>school)
def check_ready(room,r):
    c=character(room,r['character']);sp=SPELLS[r['spell']];f=formula(room,r)
    if c['kind']=='monster':raise ValueError('Чудовища используют собственные способности.')
    injuries.check_allowed(c)
    if f['rank']<1 or f['effectiveRank']>f['rank']+1:raise ValueError('Нет нужной школы или ранг заклинания слишком высок.')
    if r.get('obscure') and rank(c,'general')<2:raise ValueError('Сокрытие требует общего магического ранга 2.')
    if r.get('bind') and (rank(c,'general')<3 or sp['action']=='ritual'):raise ValueError('Связывать можно обычные заклинания при общем магическом ранге 3.')
    if pool(room,c)<f['cost']:raise ValueError('Недостаточно силы воли для заклинания и всех дополнений.')
    for iid in (r.get('ingredientItem'),r.get('grimoire')):
        if iid:owned_item(room,c,iid)
    if r.get('ingredientItem') and r['ingredientItem']==r.get('grimoire'):raise ValueError('Гримуар и расходуемый ингредиент должны быть разными предметами.')
    if room.get('combat',{}).get('phase')=='setup':raise ValueError('Завершите подготовку боя перед сотворением.')
    if any(room.get(k) for k in ('treatment','coldCheck','waterCheck','afflictionCheck','expeditionCheck','journeyRisk')) or room.get('combat',{}).get('pendingRisk'):raise ValueError('Сначала завершите текущую проверку.')
    if any(i.get('repair',{}).get('status')=='rolled' for i in room.get('items',[])):raise ValueError('Сначала завершите проверку ремонта.')
    if any(x['id']!=r['id'] and x['status']=='rolled' for x in room.get('magicCastings',[])):raise ValueError('Сначала разрешите предыдущее заклинание.')
    if in_battle(room,c):
        b=room['combat'];u=unit(room,c['id'])
        if sp['action']=='ritual' or r.get('bind'):raise ValueError('Ритуал нельзя выполнить действием в бою.')
        if sp['id'] in ('mind_trick','stir_blood'):raise ValueError('Это заклинание не действует в бою.')
        if b.get('pendingMishap') or b.get('initiativeDraw') or u.get('pendingMove'):raise ValueError('Сначала завершите текущую фазу боя.')
        if sp['id']!='dispel' and (not b.get('order') or b['order'][b['turn']]!=c['id']):raise ValueError('Сейчас очередь другого бойца.')
        slow=int(sp['action']=='slow');fast=int(sp['action']=='fast')+int(bool(r.get('grimoire')))+int(sp['id']=='deers_dash')
        if u.get('slow',0)<slow or u.get('fast',0)+u.get('slow',0)-slow<fast:raise ValueError('Не хватает действий для заклинания, гримуара или бега.')
    target=character(room,r['target']) if r.get('target') else None
    if sp['range']=='self' and target is not c:raise ValueError('Заклинание действует только на заклинателя.')
    if sp['resolution']=='automatic' and not target:raise ValueError('Для автоматического эффекта выберите цель.')
    if target and sp['noMonsters'] and target['kind']=='monster':raise ValueError('Заклинание не действует на чудовищ.')
    if target is c and sp['id'] in ('cleanse_spirit','healing_hands'):raise ValueError('Это исцеление нельзя применить к себе.')
    if sp['id'] in ('cleanse_spirit','healing_hands'):
        allowed=('wit','emp') if sp['id']=='cleanse_spirit' else ('str','agi')
        if r.get('attribute') not in allowed:raise ValueError('Выберите подходящую характеристику для исцеления.')
    return f

def change_attribute(room,c,attribute,amount):
    rt=c.setdefault('runtime',{});current=rt.setdefault('current',copy.deepcopy(c.get('sheet',{}).get('attrs',{})))
    maximum=c.get('sheet',{}).get('attrs',{}).get(attribute,c.get('monster',{}).get('strength' if attribute=='str' else 'agility',current.get(attribute,0)))
    before=current.get(attribute,0);current[attribute]=max(0,min(maximum,before+amount))
    u=unit(room,c['id'])
    if u:u[UNIT_ATTR[attribute]]=current[attribute]
    return current[attribute]-before
def effect(room,c,r,kind,**values):
    e=dict(id=secrets.token_hex(8),spell=r['spell'],kind=kind,power=r['power'],source=r['character'],private=r.get('private',False),created=now(room),quarter=quarter(room),**values)
    c.setdefault('runtime',{}).setdefault('magicEffects',[]).append(e)
    return e
def sync_battle(room):
    if room.get('combat'):
        room['combatRevision']=room.get('combatRevision',0)+1
        for c in room['characters']:
            u=unit(room,c['id'])
            if u:
                if c['kind']=='pc':u['wp']=c.get('runtime',{}).get('wp',0)
                u['magicFireproof']=any(e['kind']=='fireproof' for e in c.get('runtime',{}).get('magicEffects',[]))
                if u['magicFireproof']:u['fireproof']=True
                u['injuries']=copy.deepcopy(c.get('runtime',{}).get('injuries',[]))
def armor_save(room,target,power,private):
    """Normal armor: successes block, banes wear armor only if damage gets through."""
    from equipment_rules import armor,artifact,prepare
    u=unit(room,target['id']);items={i['id']:i for i in room.get('items',[])}
    if u and u.get('armorSources'):
        sources=[dict(id=v['id'],rating=v['current'],artifact=v.get('artifact',0),unit=v) for v in u['armorSources']]
    elif target['kind']!='monster':
        prepare(room,target)
        equipped=[items[i] for k,i in target.get('equipment',{}).items() if k in ('armor','helmet') and i in items]
        sources=[dict(id=i['id'],rating=armor(i),artifact=artifact(i)) for i in equipped]
        if not sources:sources=[dict(rating=target.get('runtime',{}).get('armor',0),artifact=0)]
    else:sources=[dict(rating=u.get('armor',0) if u else target.get('monster',{}).get('armor',0),artifact=0)]
    groups=[];stopped=0
    for source in sources:
        source['dice']=[die() for _ in range(source['rating'])];groups.append(group('armor',source['dice']));stopped+=source['dice'].count(6)
        if source['artifact']:
            value=die(source['artifact']);groups.append(group('artifact',[value],source['artifact']));stopped+=max(0,value//2-2)
    if power>stopped:
        for source in sources:
            wear=source['dice'].count(1)
            if not wear:continue
            i=items.get(source.get('id'))
            if i:i['wear']=i.get('wear',0)+wear;i['version']+=1
            if 'unit' in source:source['unit']['current']=max(0,source['rating']-wear)
        if u:
            u['armor']=sum(v['current'] for v in u['armorSources']) if u.get('armorSources') else max(0,u.get('armor',0)-sum(v['dice'].count(1) for v in sources))
            target.setdefault('runtime',{})['armor']=u['armor']
    if groups:publish(room,target['name'],'Броня против магии',groups,f'Поглощено: {stopped}.',private)
    return stopped
def automatic_effect(room,r):
    sp=SPELLS[r['spell']];c=character(room,r['character']);target=character(room,r['target']);power=r['power']
    seals=[e['power'] for e in target.get('runtime',{}).get('magicEffects',[]) if e['kind']=='seal']
    if seals and r['spell']!='seal':
        power=max(0,power-max(seals));r['sealReduction']=r['power']-power
    r['effectivePower']=power
    if not power:return 'Печать поглотила эффект заклинания.'
    if sp['id'] in ('cleanse_spirit','healing_hands'):
        n=change_attribute(room,target,r['attribute'],power)
        return f'{target["name"]}: {NAMES[r["attribute"]]} +{n}; критические травмы не изменены.'
    if sp['id'] in ('firewalker','seal','lightbringer'):
        kind={'firewalker':'fireproof','seal':'seal','lightbringer':'light'}[sp['id']]
        effect(room,target,r,kind,**({'untilQuarter':quarter(room)+1} if sp['id']!='lightbringer' else {'until':now(room)+15*power}))
        return f'{target["name"]}: {sp["name"]}, мощь {power}. Эффект отмечен в листе.'
    attrs={'horrify':['wit'],'ghoulish_aura':['emp'],'hand_doom':['str'],'terror':['wit','emp'],'bears_claw':['str'],'stone_storm':['str'],'immolate':['str']}[sp['id']]
    blocked=0
    if sp['id'] in ('bears_claw','stone_storm'):
        blocked=armor_save(room,target,power,r['private']);r['armor']={'blocked':blocked}
    damage=max(0,power-blocked)
    if sp['id']=='immolate' and any(e['kind']=='fireproof' for e in target.get('runtime',{}).get('magicEffects',[])):damage=0
    results=[]
    for a in attrs:results.append(f'{NAMES[a]} {change_attribute(room,target,a,-damage):+d}')
    if sp['id']=='immolate' and damage:
        effect(room,target,r,'burning',requires='Медленное действие и успешное Проворство: погасить огонь.')
        u=unit(room,target['id'])
        if u:u['burning']=True
    return target['name']+': '+', '.join(results)+'.'

MISHAPS=[(13,'Свидетель рассказывает о магии; репутация +1.'),(15,'Заклинатель голоден.'),(21,'Заклинатель испытывает жажду.'),(23,'Бессонница на D6 дней; сонливость.'),(25,'Ловкость −1.'),(31,'Телосложение −1.'),(33,'Эмпатия −1.'),(35,'Разум −1.'),(41,'Магическая болезнь с вирулентностью 2D6. Заклинатель и находящиеся на расстоянии руки в текущую четверть подвергаются заражению.'),(45,'Дополнительная непреднамеренная цель; полезный эффект затрагивает врага.'),(46,'Внешность меняется навсегда; детали определяет Мастер.'),(51,'Слепота на полные сутки, действия как в полной тьме.'),(55,'Немедленная критическая травма: психическая.'),(56,'Немедленная критическая травма: дробящий удар.'),(61,'В текущую четверть появляется демон.'),(65,'Заклинание обращается против создателя; подробности определяет Мастер.'),(66,'Демон уносит заклинателя в иной мир; возвращение как ПВ через D66 дней.')]
def roll_mishap():
    a,b=die(),die();value=a*10+b
    m=dict(value=value,dice=[a,b],description=next(label for maximum,label in MISHAPS if value<=maximum))
    if 22<=value<=23:m['days']=die()
    if 36<=value<=41:m['virulence']=die()+die()
    if value==66:m['returnDays']=die()*10+die()
    return m
def apply_mishap(room,r):
    c=character(room,r['character']);m=r['mishap'];v=m['value'];rt=c['runtime']
    if v<=13:rt['magicReputationBonus']=rt.get('magicReputationBonus',0)+1
    elif v<=21:rt.setdefault('conditions',{})['hungry' if v<=15 else 'thirsty']=True
    elif v<=23:
        rt.setdefault('conditions',{})['sleepy']=True
        effect(room,c,r,'insomnia',until=now(room)+m['days']*1440)
    elif v<=35:change_attribute(room,c,'agi' if v<=25 else 'str' if v<=31 else 'emp' if v<=33 else 'wit',-1)
    elif v==51:effect(room,c,r,'blind',until=now(room)+1440)
    elif 52<=v<=56:injuries.pending_injury(room,c,'wit' if v<=55 else 'str','horror' if v<=55 else 'blunt',source='magic-mishap')
    # Other results are recorded and explicitly adjudicated by the GM. Never
    # silently pick an unintended target, kill a character, or create a demon.

def finish_cast(room,r):
    c=character(room,r['character']);sp=SPELLS[r['spell']];f=check_ready(room,r)
    if c['kind']=='npc':room['magicWillpower']=pool(room,c)-f['cost']
    else:c['runtime']['wp']=pool(room,c)-f['cost']
    if r.get('ingredientItem') and not sp['reusable']:
        item=owned_item(room,c,r['ingredientItem']);item['quantity']-=1;item['version']+=1
        if item['quantity']==0:
            from equipment_rules import clear_slots
            clear_slots(room,item['id']);room['items'].remove(item)
    if in_battle(room,c):
        b=room['combat'];u=unit(room,c['id'])
        if sp['action']=='slow':u['slow']-=1
        for _ in range(int(sp['action']=='fast')+int(bool(r.get('grimoire')))+int(sp['id']=='deers_dash')):
            if u['fast']:u['fast']-=1
            else:u['slow']-=1
        b['roundStarted']=True
        if b.get('order') and b['order'][b['turn']]==c['id']:b['activationStarted']=True
        b.pop('initiativeOffer',None)
    values=[die() for _ in range(f['dice'])]
    r.update(status='rolled',formula=f,dice=values,power=f['base']+values.count(6)+int(r['ingredient']),castAt=now(room))
    if 1 in values or f['chance']:r['mishap']=roll_mishap()
    groups=[group('magic',values)]
    if r.get('mishap'):groups.append(group('table',r['mishap']['dice']))
    message=f'{sp["name"]}: мощь {r["power"]}; СВ −{f["cost"]}; усиление +{values.count(6)}.'
    if r.get('mishap'):message+=f' Осечка D66: {r["mishap"]["value"]}. Решение Мастера обязательно.'
    r['event']=publish(room,c['name'],'Сотворение заклинания',groups,message,r['private'])
    c['runtime'].setdefault('castSpells',[])
    if sp['id'] not in c['runtime']['castSpells']:c['runtime']['castSpells'].append(sp['id'])
    if sp['resolution']=='automatic' and not r.get('mishap') and not r.get('bind'):
        r['result']=automatic_effect(room,r);r['status']='resolved';log(room,r,r['result'])
    else:r['result']='Нужен вердикт Мастера: '+(r.get('mishap',{}).get('description') or sp['summary'])
    sync_battle(room)

def apply(room,s,data):
    op=data.get('op');casts=room.setdefault('magicCastings',[])
    if op=='pool':
        gm(s);room['magicWillpower']=integer(data.get('value'),0,1000);return
    if op=='declare':
        c=character(room,data.get('character'))
        if not controls(c,s):raise PermissionError('Вы можете заявлять магию только своего персонажа.')
        sp=SPELLS.get(data.get('spell'))
        if not sp:raise ValueError('Выберите заклинание из каталога.')
        if sp['id'] in ('obscure','bind_magic'):raise ValueError('Выберите основное заклинание и включите сокрытие/связывание в его параметрах.')
        if any(r['character']==c['id'] and r['status'] in PENDING for r in casts):raise ValueError('Сначала завершите или отмените текущую магию этого персонажа.')
        private=visibility(s,data) or bool(c.get('hidden'))
        target=data.get('target','')
        if sp['range']=='self':target=c['id']
        if target:
            victim=character(room,target)
            if victim.get('hidden') and s['role']!='gm':raise PermissionError('Цель недоступна.')
            private=private or bool(victim.get('hidden'))
        wp=integer(data.get('wp'),1,1000 if c['kind']=='npc' else 10);binding=integer(data.get('bind',0),0,5)
        if binding not in (0,1,2,5):raise ValueError('Для связывания доплата 1, 2 или 5 СВ.')
        note=text(data.get('note',''),800)
        if not note:raise ValueError('Опишите цель, дистанцию и намерение заклинания для Мастера.')
        ingredient_item=text(data.get('ingredientItem',''),100);ingredient_scene=text(data.get('ingredientScene',''),200)
        if ingredient_item and ingredient_scene:raise ValueError('Выберите один источник ингредиента.')
        r=dict(id=secrets.token_hex(12),character=c['id'],target=target,spell=sp['id'],status='requested',note=note,wp=wp,
            safe=data.get('safe') is True,bind=binding,obscure=data.get('obscure') is True,extend=data.get('extend') is True,
            grimoire=text(data.get('grimoire',''),100),ingredientItem=ingredient_item,ingredientScene=ingredient_scene,
            ingredient=bool(ingredient_item or ingredient_scene),attribute=data.get('attribute','str'),private=private,created=now(room))
        if r['extend'] and sp['id']!='hand_doom':raise ValueError('Продление дистанции этой опцией доступно только «Руке рока».')
        if len([x for x in casts if x['status'] in PENDING])>=20:raise ValueError('Сначала завершите ожидающие заклинания.')
        check_ready(room,r);r['signature']=signature(room,r)
        room['magicCastings']=([x for x in casts if x['status'] in PENDING]+[x for x in casts if x['status'] not in PENDING][-60:]+[r])
        log(room,r,f'{c["name"]} заявляет «{sp["name"]}»: {note}');return
    if op=='end_effect':
        gm(s);c=character(room,data.get('character'));effects=c['runtime'].get('magicEffects',[])
        e=next((e for e in effects if e['id']==data.get('effect')),None)
        note=text(data.get('note',''),500)
        if not e or not note:raise ValueError('Выберите действующий эффект и укажите причину завершения.')
        effects.remove(e)
        u=unit(room,c['id'])
        if u and e['kind']=='burning':u['burning']=False
        if u and e['kind']=='fireproof':u['fireproof']=False
        log(room,e,f'{c["name"]}: {SPELLS[e["spell"]]["name"]} завершено. {note}');sync_battle(room);return
    r=next((r for r in casts if r['id']==data.get('casting')),None)
    if not r:raise ValueError('Заявка заклинания не найдена.')
    c=character(room,r['character'])
    if not controls(c,s) or r['private'] and s['role']!='gm':raise PermissionError('Эта магия управляется другим участником.')
    if op=='cancel':
        if r['status'] not in ('requested','approved','ritual'):raise ValueError('Состоявшийся бросок нельзя отменить или повторить.')
        r['status']='cancelled';log(room,r,f'{c["name"]}: заявка заклинания отменена.');return
    if op=='approve':
        gm(s)
        if r['status']!='requested':raise ValueError('Заявка уже обработана.')
        if data.get('confirmed') is not True:raise ValueError('Подтвердите дистанцию, видимость, допустимость цели и подготовку ингредиента/гримуара.')
        check_ready(room,r);r['status']='approved';r['signature']=signature(room,r);return
    if op=='cast':
        if r['status']!='approved':raise ValueError('Сначала требуется подтверждение Мастера; повторный бросок недоступен.')
        check_ready(room,r)
        if signature(room,r)!=r['signature']:raise ValueError('Персонаж, цель, предметы или очередь изменились. Отмените заявку и подайте заново.')
        if SPELLS[r['spell']]['action']=='ritual' or r.get('bind'):
            r.update(status='ritual',started=now(room),due=now(room)+360)
            log(room,r,f'{c["name"]} начинает ритуал: нужна четверть суток игрового времени без помех.');return
        finish_cast(room,r);return
    if op=='finish_ritual':
        gm(s)
        if r['status']!='ritual' or now(room)<r['due']:raise ValueError('Ритуал ещё не завершён по игровому времени.')
        if data.get('confirmed') is not True:raise ValueError('Мастер должен подтвердить непрерывное выполнение ритуала и сохранение условий.')
        finish_cast(room,r);return
    if op=='resolve':
        gm(s)
        if r['status']!='rolled':raise ValueError('Это заклинание уже завершено или ещё не брошено.')
        note=text(data.get('note',''),1500)
        if not note:raise ValueError('Запишите конкретные последствия заклинания и осечки, если она была.')
        mode=data.get('mode','manual')
        if mode not in ('manual','apply','cancel_effect'):raise ValueError('Выберите способ разрешения эффекта.')
        sp=SPELLS[r['spell']]
        if mode=='apply' and (sp['resolution']!='automatic' or r.get('bind') or r.get('mishap',{}).get('value',0)>=62):raise ValueError('Для этого случая нужен ручной вердикт, а не обычный автоматический эффект.')
        changes=data.get('changes',[])
        if not isinstance(changes,list) or len(changes)>20:raise ValueError('Слишком много последствий.')
        parsed=[]
        for change in changes:
            if not isinstance(change,dict) or change.get('attribute') not in ATTRIBUTES:raise ValueError('Некорректная характеристика последствия.')
            target=character(room,change.get('character'));amount=integer(change.get('amount'),-100,100)
            if target['kind']=='monster' and change['attribute'] in ('wit','emp'):raise ValueError('Чудовище не имеет Разума/Эмпатии для этого эффекта.')
            if target.get('hidden') and not r['private']:raise ValueError('Скрытые цели разрешайте отдельным скрытым решением.')
            parsed.append((target,change['attribute'],amount))
        if r.get('mishap'):apply_mishap(room,r)
        if mode=='apply':r['result']=automatic_effect(room,r)
        elif mode=='cancel_effect':r['result']='Мастер отменил основной эффект; затраты и осечка сохраняются.'
        else:r['result']='Последствия разрешены Мастером.'
        for target,attribute,amount in parsed:change_attribute(room,target,attribute,amount)
        r.update(status='resolved',verdict=note,changes=copy.deepcopy(changes));log(room,r,r['result']+' '+note);sync_battle(room);return
    raise ValueError('Неизвестная команда магии.')

def reconcile(room):
    """Call after injuries.reconcile: expire game-time markers, sync protection.

    Combat burning is advanced by the combat engine. Outside combat it requires
    an explicit GM decision, never damage caused by wall-clock polling.
    """
    for c in room.get('characters',[]):
        effects=c.get('runtime',{}).get('magicEffects',[])
        remaining=[e for e in effects if not ('until' in e and now(room)>=e['until'] or 'untilQuarter' in e and quarter(room)>=e['untilQuarter'])]
        if len(effects)!=len(remaining):
            c['runtime']['magicEffects']=remaining
            u=unit(room,c['id'])
            if u and u.get('magicFireproof') and not any(e['kind']=='fireproof' for e in remaining):u['fireproof']=False;u['magicFireproof']=False
        u=unit(room,c['id'])
        if u and room.get('combat',{}).get('phase')=='combat' and not u.get('burning'):
            c['runtime']['magicEffects']=[e for e in remaining if e['kind']!='burning']
def guard(room,s,data):
    if any(r['status']=='rolled' for r in room.get('magicCastings',[])) and data.get('action') not in ('magic','chat','roll'):
        raise ValueError('Сначала Мастер должен разрешить заклинание и его последствия в разделе «Магия».')
def project(room,s):
    visible=[]
    for r in room.get('magicCastings',[]):
        if r.get('private') and s['role']!='gm':continue
        if r['status'] in ('requested','approved','ritual'):
            try:r['formula']=formula(room,r);r['current']=r['status']=='ritual' or signature(room,r)==r.get('signature')
            except (ValueError,KeyError):r['current']=False
        r.pop('signature',None)
        visible.append(r)
    room['magicCastings']=visible
    if s['role']!='gm':room.pop('magicWillpower',None)
    for c in room.get('characters',[]):
        if c['kind']!='monster':c.setdefault('runtime',{})['magicRanks']={k:rank(c,k) for k in CATALOG['schools']}
        if s['role']!='gm' and c.get('runtime',{}).get('magicEffects'):
            c['runtime']['magicEffects']=[e for e in c['runtime']['magicEffects'] if not e.get('private')]

def restored(room):
    """Invalidate queued commands from the abandoned save branch, retain dice."""
    for r in room.get('magicCastings',[]):
        if r['status'] in PENDING:
            r['id']=secrets.token_hex(12)
            if r['status']=='approved':r['status']='requested'
            if r['status']=='requested':
                try:r['signature']=signature(room,r)
                except (ValueError,KeyError):r.pop('signature',None)
    for c in room.get('characters',[]):
        for e in c.get('runtime',{}).get('magicEffects',[]):e['id']=secrets.token_hex(8)
