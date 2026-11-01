"""Hunting, vessels and staffed strongholds (PHB 151–157, 162–169).

Material quantities follow the English PHB. Capacity, river passages and unusual
construction circumstances are explicit GM decisions, never inferred rule data.
"""
import secrets
from copy import deepcopy
import campaign_rules as campaign
from dice_events import publish, pools, group
from dice_pools import result_text
from equipment_rules import owned, bonus, artifact
from risk_rules import can_push_character, repeat_push, push, score
import injuries

PREY = [
    dict(name='Мышь', modifier=1, trap=True, meat=1, pelts=0),
    dict(name='Ворона', modifier=0, trap=False, meat=1, pelts=0),
    dict(name='Кролик', modifier=1, trap=True, meat=2, pelts=1),
    dict(name='Лиса', modifier=-1, trap=True, meat=3, pelts=1),
    dict(name='Кабан', modifier=-1, trap=False, meat=4, pelts=2),
    dict(name='Олень', modifier=0, trap=False, meat=5, pelts=3),
]
RECIPES = {
    'bakery': dict(source='flour', target='food', maximum=12, worker='Повар / пекарь'),
    'forge': dict(source='ore', target='iron', maximum=12, worker='Кузнец'),
    'mill': dict(source='grain', target='flour', maximum=12, worker='Мельник или герой'),
    'inn': dict(source='meat', target='food', maximum=12, worker='Трактирщик или герой'),
    'garden': dict(source=None, target='vegetables', maximum=10, worker='Фермер или герой'),
}
CONDITIONS = {'sound':'Исправно','leaking':'Течь','grounded':'На мели','sunk':'Затонуло','abandoned':'Оставлено'}

def die(sides=6):return campaign.dice(1,sides)[0]
def now(room):return campaign.state(room)['day']*4+room['journey']['quarter']
def gm(s):
    if s['role']!='gm':raise PermissionError('Это решение принимает Мастер.')
def text(value,limit=300):
    if not isinstance(value,str) or not value.strip() or len(value)>limit:raise ValueError('Укажите пояснение допустимой длины.')
    return value.strip()
def actor(room,cid):
    c=next((c for c in room['characters'] if c['id']==cid and c['kind']!='monster'),None)
    if not c:raise ValueError('Персонаж не найден.')
    return c
def control(c,s):
    if s['role']!='gm' and (c.get('hidden') or c['kind']!='pc' or c['owner']!=s['owner']):raise PermissionError('Выберите своего героя.')
def vessel(room,vid=None):
    return next((v for v in room.get('vessels',[]) if v['id']==(vid or room.get('journey',{}).get('vessel'))),None)
def pending_for(room,h):
    return next((p for p in room['journey']['pending'] if p['id']==h['pending']),None)
def unlock(room,pid):
    room['journey']['pending']=[p for p in room['journey']['pending'] if p['id']!=pid]
    room['journey']['completed']={}
def event(room,c,label,values,result):
    return publish(room,c['name'],label,[group('table',values)],result,bool(c.get('hidden')))

def start_hunt(room,c,r):
    choices=[die() for _ in range(2 if c['sheet'].get('talents',{}).get('masterhunt',0)>=3 else 1)]
    p=campaign.pending(room,c['name']+': охота','Продолжите охоту в карточке добычи: выбор, перебросы и проверка оружия или ловушки.')
    h=dict(id=secrets.token_hex(8),actor=c['id'],pending=p['id'],choices=choices,rerolls=max(0,r['hits']-1),stage='prey',revision=0,day=room['journey']['day'],quarter=room['journey']['quarter'])
    room.setdefault('hunts',[]).append(h);room['hunts']=room['hunts'][-60:];p['hunt']=h['id']
    event(room,c,'Охота · добыча',choices,' / '.join(PREY[n-1]['name'] for n in choices))

def announce(room,p):
    c=actor(room,p['actor']);r=p['roll'];score(r)
    r['pushAvailable']=can_push_character(c,r)
    item=next((i for i in owned(room,c['id']) if i['id']==p['item']),None)
    p['signature']=injuries.signature(c,item)
    p['diceEvent']=publish(room,c['name'],p['label'],pools(r),result_text(*score(r))+' Примите результат для применения последствий.',p['private'],risk=dict(action='expedition',roll=p['id'],character=c['id'],attribute=p['attribute']))
    r.update(id=p['id'],attribute=p['attribute'],diceEvent=p['diceEvent'])

def roll_check(room,c,skill,modifier,item,payload,data=None):
    if room.get('expeditionCheck'):raise ValueError('Сначала завершите предыдущую проверку экспедиции.')
    from kin_checks import adaptation
    from skill_checks import ATTRS
    original=skill;skill=adaptation(c,data or {},skill);attribute=ATTRS[skill]
    injuries.check_allowed(c)
    modifiers=list(modifier) if isinstance(modifier,(list,tuple)) else [modifier]
    r=campaign.check(c,skill,[*modifiers,injuries.modifiers(c,skill,attribute)],bonus(item) if item else 0);r['pushed']=False;r['artifacts']=[];r['originalSkill']=original
    if item and artifact(item):r['artifacts'].append(dict(sides=artifact(item),value=die(artifact(item))))
    p=dict(id=secrets.token_hex(12),actor=c['id'],attribute=attribute,item=item['id'] if item else '',private=bool(c.get('hidden')),roll=r,**payload)
    room['expeditionCheck']=p;announce(room,p)

def hunt_action(room,s,data):
    h=next((h for h in room.get('hunts',[]) if h['id']==data.get('hunt')),None)
    if not h or h['stage']=='done':raise ValueError('Охота уже завершена.')
    c=actor(room,h['actor']);control(c,s)
    if data.get('huntRevision')!=h['revision']:raise ValueError('Добыча уже изменилась. Обновите карточку.')
    op=data['op']
    if h['stage']!='prey':raise ValueError('Сначала примите результат проверки охоты.')
    if op=='huntReroll':
        if h['rerolls']<=0:raise ValueError('Дополнительные успехи уже потрачены.')
        slot=campaign.integer(data.get('slot',0),0,len(h['choices'])-1)
        h['choices'][slot]=die();h['rerolls']-=1;event(room,c,'Охота · новая добыча',[h['choices'][slot]],PREY[h['choices'][slot]-1]['name']+'. Предыдущий вариант утрачен.')
    elif op=='huntAbandon':
        h.update(stage='done',result='Охотник отказался от добычи.');unlock(room,h['pending'])
    elif op=='huntRoll':
        index=campaign.integer(data.get('choice'),0,len(h['choices'])-1);animal=PREY[h['choices'][index]-1];method=data.get('method')
        if method not in ('weapon','trap') or method=='trap' and not animal['trap']:raise ValueError('Для этой добычи нужна стрельба.')
        item=next((i for i in owned(room,c['id']) if i['id']==data.get('item')),None)
        if not item or item.get('quantity',1)!=1 or item.get('bonus',0)>0 and not bonus(item):raise ValueError('Выберите исправный предмет из инвентаря.')
        ranged=item.get('combatProfile') in ('bow','longbow','crossbow') or item.get('catalogId') in ('shortbow','longbow','lightcrossbow','heavycrossbow','sling')
        trap=item.get('catalogId') in ('snare','trap','snaretrap') or 'ловуш' in item.get('name','').lower() or 'силок' in item.get('name','').lower()
        if not (ranged if method=='weapon' else trap) and not (s['role']=='gm' and data.get('confirmed') is True):raise ValueError('Предмет не распознан как оружие охоты / ловушка. Мастер может подтвердить особое снаряжение.')
        modifier=campaign.integer(data.get('modifier',0),-10,10)
        if modifier and s['role']!='gm':raise PermissionError('Дополнительные условия задаёт Мастер.')
        if method=='weapon' and item.get('combatProfile') in ('bow','longbow','crossbow'):
            resources=c['runtime'].setdefault('resources',{});size=resources.get('arrows',0)
            if not size:raise ValueError('Запас стрел исчерпан.')
            value=die(size);resources['arrows']=[0,6,8,10,12][[0,6,8,10,12].index(size)-1] if value<=2 else size
            publish(room,c['name'],'Охота · расход стрел',[group('table',[value],size)],'Остаток: '+('D'+str(resources['arrows']) if resources['arrows'] else 'пусто'),bool(c.get('hidden')))
        h.update(stage='check',prey=h['choices'][index],method=method)
        talent=1 if method=='trap' and c['sheet'].get('talents',{}).get('masterhunt',0)>=1 else 0
        roll_check(room,c,'shoot' if method=='weapon' else 'survive',[animal['modifier'],modifier,talent],item,dict(kind='hunt',hunt=h['id'],label='Охота · '+animal['name']),data)
    else:raise ValueError('Неизвестное действие охоты.')
    h['revision']+=1

def check_action(room,s,data):
    p=room.get('expeditionCheck')
    if not p or p['id']!=data.get('roll'):raise ValueError('Проверка уже завершена.')
    c=actor(room,p['actor']);control(c,s)
    if p['private'] and s['role']!='gm':raise PermissionError('Скрытую проверку завершает Мастер.')
    if data.get('diceEvent')!=p['diceEvent']:raise ValueError('Результат уже обновился. Откройте последний бросок.')
    r=p['roll'];item=next((i for i in owned(room,c['id']) if i['id']==p['item']),None)
    if p['item'] and not item:raise ValueError('Предмет проверки перемещён. Верните его владельцу.')
    if p.get('signature')!=injuries.signature(c,item):raise ValueError('Персонаж или предмет изменился после броска.')
    if data['op']=='push':
        if not r.get('pushAvailable'):raise ValueError('Этот бросок нельзя повторно рисковать.')
        repeat_push(c,r,data)
        damage,wear=push(r,die);c['runtime']['current'][p['attribute']]=max(0,c['runtime']['current'][p['attribute']]-damage)
        if c['kind']=='pc':c['runtime']['wp']=min(10,c['runtime'].get('wp',0)+damage)
        if item and wear:item['wear']=min(item.get('bonus',0),item.get('wear',0)+wear);item['version']=item.get('version',0)+1
        announce(room,p);return
    if data['op']!='accept':raise ValueError('Выберите риск или принятие результата.')
    score(r)
    if p['kind']=='hunt':
        h=next(h for h in room['hunts'] if h['id']==p['hunt']);animal=PREY[h['prey']-1]
        h.update(stage='done',hits=r['hits'],revision=h['revision']+1)
        if r['hits']:
            campaign.found(room['journey'],'meat',animal['meat'],after=1 if room['journey']['phase']=='resolving' else 0);campaign.found(room['journey'],'pelts',animal['pelts']);h['result']=f"{animal['name']}: мясо {animal['meat']}, шкуры {animal['pelts']}."
        else:
            h['result']='Добыча ушла.'
            if h['prey']==5:campaign.pending(room,'Кабан атакует '+c['name'],'Провал охоты на кабана. Мастер начинает встречу с кабаном; характеристики берутся из бестиария.')['huntBoar']=c['id'];h['result']='Кабан атакует охотника: требуется встреча.'
        unlock(room,h['pending']);campaign.journal(room,c['name']+': '+h['result'])
    else:
        v=vessel(room,p['vessel'])
        if not v:raise ValueError('Судно не найдено.')
        if p['kind']=='repair':
            if r['hits']:v.update(condition='sound');v.pop('sinksAt',None)
            campaign.journal(room,v['name']+': ремонт '+('успешен.' if r['hits'] else 'не удался.'))
        elif p['kind']=='whirlpool':
            if not r['hits']:v['condition']='grounded'
            unlock(room,p['pending']);campaign.journal(room,v['name']+': водоворот — '+('курс сохранён.' if r['hits'] else 'судно село на мель.'))
        v['revision']+=1
    room.pop('expeditionCheck',None)

def sea_mishap(room,v,c):
    value=die();labels={1:'Ошибка навигации',2:'Шквал',3:'Водоворот',4:'Течь',5:'За бортом',6:'Мель'}
    p=campaign.pending(room,'На воде · '+labels[value],'Книга игрока, стр. 156. Откройте судно: разрешите неприятность и подтвердите последствия.',value)
    p.update(vessel=v['id'],seaMishap=value,skipper=c['id'])
    if value==4:
        hours=die();v.update(condition='leaking',sinksAt=now(room)*360+hours*60);p['note']=f'Ремонт занимает 15 минут. Без ремонта судно затонет через {hours} ч. Время и гибель судна подтверждает Мастер.'
    if value==6:v['condition']='grounded'
    v['revision']+=1
    event(room,c,'Водный путь · неприятность',[value],labels[value])
    return p

def vessel_action(room,s,data):
    gm(s);op=data['op'];t=campaign.state(room)
    if op=='vesselCreate':
        if len(room.get('vessels',[]))>=20:raise ValueError('Предел: 20 судов.')
        v=dict(id=secrets.token_hex(8),name=text(data.get('name'),80),kind=text(data.get('kind'),40),capacity=campaign.integer(data.get('capacity'),1,100),cargoLimit=campaign.integer(data.get('cargoLimit'),0,100000),cargo=0,condition='sound',position=deepcopy(t['position']),revision=0,note='')
        room.setdefault('vessels',[]).append(v);return
    v=vessel(room,data.get('vessel'))
    if not v or data.get('vesselRevision')!=v['revision']:raise ValueError('Судно изменилось. Обновите карточку.')
    if op=='vesselBoard':
        if t['phase']!='planning' or t.get('gmReady') or t['pending']:raise ValueError('Менять транспорт можно при планировании без ожидающих событий.')
        if data.get('aboard'):
            if v['position']!=t['position'] or v['condition'] not in ('sound','leaking'):raise ValueError('Исправное судно должно находиться у отряда.')
            if len(t['party'])>v['capacity'] or v['cargo']>v['cargoLimit']:raise ValueError('Недостаточно мест или превышен груз.')
            t['vessel']=v['id'];t['riverRoute']=data.get('riverRoute') is True
        else:t.pop('vessel',None);t.pop('riverRoute',None)
        t.update(route=[],gmReady=False,plans={});t['routeVersion']+=1;t['cycleId']=secrets.token_hex(8)
    elif op=='vesselCargo':
        v['cargo']=campaign.integer(data.get('cargo'),0,100000);v['note']=str(data.get('note',''))[:500]
    elif op=='vesselRepair':
        if v['condition'] not in ('grounded','leaking'):raise ValueError('Судно не нуждается в таком ремонте.')
        if v['position']!=t['position']:raise ValueError('Ремонтник должен находиться у судна.')
        if v['condition']=='grounded' and data.get('shore') is not True:raise ValueError('Ремонт севшего на мель судна требует берега.')
        c=actor(room,data.get('character'));item=next((i for i in owned(room,c['id']) if i['id']==data.get('item')),None)
        if data.get('item') and not item:raise ValueError('Выбранный инструмент должен принадлежать ремонтнику.')
        if item and item.get('bonus',0)>0 and not bonus(item):raise ValueError('Инструмент сломан. Выберите исправный предмет.')
        if c['id'] not in t['party']:raise ValueError('Ремонтник должен быть участником отряда у судна.')
        roll_check(room,c,'craft',campaign.integer(data.get('modifier',0),-10,10),item,dict(kind='repair',vessel=v['id'],label='Ремонт судна · '+v['name']),data)
    elif op=='vesselMishap':
        p=next((p for p in t['pending'] if p['id']==data.get('pending') and p.get('vessel')==v['id']),None)
        if not p:raise ValueError('Неприятность уже разрешена.')
        if p['seaMishap']==3:
            c=actor(room,p['skipper']);rank=c['sheet'].get('talents',{}).get('sailor',0)
            roll_check(room,c,'survive',1 if rank else 0,None,dict(kind='whirlpool',vessel=v['id'],pending=p['id'],label='Водоворот · Выживание'))
            if rank>=3:room['expeditionCheck']['roll']['artifacts'].append(dict(sides=8,value=die(8)));announce(room,room['expeditionCheck'])
        else:
            description=text(data.get('note'))
            if p['seaMishap']==5:
                import water_exposure
                c=actor(room,data.get('character'))
                water_exposure.apply(room,s,dict(op='configure',character=c['id'],phase='afloat',metalArmor=data.get('metalArmor') is True,modifier=0,note='За бортом: '+description,exposure=c.get('runtime',{}).get('waterExposure',{}).get('id')))
            if p['seaMishap']==1:
                t['position']=deepcopy(p['origin']);v['position']=deepcopy(p['origin'])
            unlock(room,p['id']);campaign.journal(room,v['name']+': '+description)
    elif op=='vesselCondition':
        if data.get('condition') not in CONDITIONS:raise ValueError('Неизвестное состояние судна.')
        v['condition']=data['condition'];campaign.journal(room,v['name']+': '+CONDITIONS[v['condition']]+'. '+text(data.get('note')))
    else:raise ValueError('Неизвестное действие судна.')
    v['revision']+=1

def worker(room,h,wid):
    if wid.startswith('hire:'):
        w=next((w for w in h['hirelings'] if w['id']==wid[5:]),None)
        if not w:raise ValueError('Наёмник не найден.')
        if w['paidThrough']<room['journey']['day']:raise ValueError('Сначала оплатите работу наёмника.')
        return w
    c=actor(room,wid)
    if room['journey']['position']!=h['position'] or c['id'] not in room['journey']['party']:raise ValueError('Герой должен находиться в цитадели.')
    if room['journey']['plans'].get(c['id'],{}).get('job')!='work':raise ValueError('Герою требуется заявка «Работа в цитадели».')
    return c

def hold_action(room,s,data):
    gm(s);h=next((h for h in room.get('strongholds',[]) if h['id']==data.get('hold')),None)
    if not h:raise ValueError('Цитадель не найдена.')
    for k in campaign.MATERIALS:h['stock'].setdefault(k,0)
    op=data['op']
    if op=='holdAssign':
        wid=text(data.get('worker'),80);worker(room,h,wid);task=data.get('task');valid=['upkeep','guard',*['project:'+p['id'] for p in h['projects']],*['produce:'+f for f in h['functions'] if f in RECIPES]]
        if task not in valid:raise ValueError('Выберите доступный проект или работу.')
        if data.get('qualified') is not True:raise ValueError('Подтвердите квалификацию, инструменты и условия работника.')
        h.setdefault('assignments',{})[wid]=dict(task=task,qualified=True)
    elif op=='holdUnassign':h.setdefault('assignments',{}).pop(data.get('worker'),None)
    elif op=='holdShift':
        wid=data.get('worker');w=worker(room,h,wid);assignment=h.get('assignments',{}).get(wid)
        if not assignment:raise ValueError('Сначала назначьте работника.')
        stamp=now(room);ledger=h.setdefault('workLedger',[])
        if any(x['worker']==wid and x['at']==stamp for x in ledger):raise ValueError('Эта четверть работы уже учтена.')
        shifts=sum(x['worker']==wid and x['at']//4==stamp//4 for x in ledger)
        if shifts>=2 and wid.startswith('hire:'):
            if shifts>=3:raise ValueError('Доступно две обычных смены и одна дополнительная смена наёмника.')
            if data.get('overtime') is not True:raise ValueError('Третья смена требует двойной дневной оплаты. Подтвердите доплату.')
            if h['stock']['copper']<w['wage']:raise ValueError('Недостаточно монет на доплату за третью смену.')
        task=assignment['task'];result=''
        if task.startswith('project:'):
            p=next((p for p in h['projects'] if p['id']==task[8:]),None)
            if not p:raise ValueError('Строительство уже завершено.')
            if p.get('lastWork')==[room['journey']['day'],room['journey']['quarter']]:raise ValueError('Четверть строительства уже записана; помощь не сокращает время автоматически.')
            p['work']+=1;p['lastWork']=[room['journey']['day'],room['journey']['quarter']];result='строительство '+campaign.FUNCTIONS[p['function']]['name']
            if p['work']>=p['required']:
                h['functions'].append(p['function']);h['projects'].remove(p)
                h['assignments']={k:v for k,v in h['assignments'].items() if v['task']!=task};result+=' завершено; проверьте репутацию'
        elif task.startswith('produce:'):
            fid=task[8:];recipe=RECIPES.get(fid)
            if not recipe or fid not in h['functions']:raise ValueError('Производство недоступно.')
            if h.setdefault('production',{}).get(fid)==[room['journey']['day'],room['journey']['quarter']]:raise ValueError('Производство постройки за эту четверть уже учтено.')
            amount=campaign.integer(data.get('amount',recipe['maximum']),1,recipe['maximum']);source=recipe['source']
            if fid=='garden':
                if room['journey']['season'] not in ('spring','summer'):raise ValueError('Огород даёт овощи только весной и летом.')
                if stamp-h.get('lastHarvest',-28)<28:raise ValueError('Огород ещё не дал недельный урожай.')
                amount=10;h['lastHarvest']=stamp
            if fid=='inn':
                source=data.get('source','meat')
                if source not in ('meat','vegetables'):raise ValueError('Трактир перерабатывает мясо или овощи.')
            if source and h['stock'].get(source,0)<amount:raise ValueError('На складе не хватает сырья: '+source+'.')
            if source:h['stock'][source]-=amount
            h['stock'][recipe['target']]+=amount;h['production'][fid]=[room['journey']['day'],room['journey']['quarter']];result=f"произведено {amount} {recipe['target']}"
        else:
            h[task+'At']=stamp;result='обслуживание' if task=='upkeep' else 'охрана'
        if shifts>=2 and wid.startswith('hire:'):h['stock']['copper']-=w['wage']
        ledger.append(dict(worker=wid,at=stamp,task=task,result=result));h['workLedger']=ledger[-200:]
        campaign.journal(room,h['name']+' · '+w['name']+': '+result+'.')
    elif op=='holdLayout':
        fid=data.get('function')
        if fid not in h['functions'] and fid not in [p['function'] for p in h['projects']]:raise ValueError('Постройка отсутствует.')
        x=campaign.integer(data.get('x'),0,5);y=campaign.integer(data.get('y'),0,3)
        if any(k!=fid and v==[x,y] for k,v in h.get('layout',{}).items()):raise ValueError('Место уже занято другой постройкой.')
        h.setdefault('layout',{})[fid]=[x,y]
    else:raise ValueError('Неизвестная работа цитадели.')

def apply(room,s,data):
    t=campaign.state(room)
    if data.get('revision')!=t['revision']:raise ValueError('Экспедиция обновилась. Повторите после синхронизации.')
    op=data.get('op','')
    if room.get('combat',{}).get('phase') in ('setup','combat') and op not in ('push','accept'):raise ValueError('Сначала завершите текущую боевую сцену.')
    if op not in ('push','accept'):
        from water_exposure import pending_other
        if pending_other(room):raise ValueError('Сначала завершите предыдущую проверку персонажа.')
    if room.get('expeditionCheck') and op not in ('push','accept'):raise ValueError('Сначала примите результат проверки экспедиции.')
    if op in ('push','accept'):check_action(room,s,data)
    elif op.startswith('hunt'):hunt_action(room,s,data)
    elif op.startswith('vessel'):vessel_action(room,s,data)
    elif op.startswith('hold'):hold_action(room,s,data)
    else:raise ValueError('Неизвестное действие экспедиции.')
    t['revision']+=1

def project(room,s):
    """Called on the copied response, before normal player redaction."""
    room['expeditionCatalog']=dict(prey=PREY,recipes=RECIPES,conditions=CONDITIONS,functions=campaign.FUNCTIONS,materials=list(campaign.MATERIALS))
    p=room.get('expeditionCheck')
    if p:
        p.pop('signature',None)
        p.get('roll',{}).pop('signature',None)
    if s['role']=='gm':return
    visible={c['id'] for c in room.get('characters',[]) if not c.get('hidden')}
    room['hunts']=[h for h in room.get('hunts',[]) if h['actor'] in visible]
    if p and (p.get('private') or p['actor'] not in visible):room['expeditionCheck']={'waiting':True,'private':True}
