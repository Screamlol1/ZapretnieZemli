"""Journey and stronghold state. PH chapters 7–8; complex consequences stay with GM."""
import secrets

TERRAINS = {
    'plain': ('Равнина', 2, -1, 1), 'forest': ('Лес', 2, 1, 1),
    'darkforest': ('Тёмный лес', 1, -1, 0), 'hills': ('Холмы', 2, 0, 0),
    'mountain': ('Горы', 1, -2, -1), 'highmountain': ('Высокие горы', 0, 0, 0),
    'water': ('Вода', 0, 0, 0), 'marsh': ('Болото', 0, 1, -1),
    'rough': ('Топь / трудная местность', 1, -1, 0), 'ruin': ('Руины', 1, -2, -1),
    'road': ('Дорога', 2, -1, 1), 'wall': ('Преграда', 0, 0, 0)}
JOBS = ('hike', 'watch', 'camp', 'rest', 'sleep', 'forageFood', 'forageWater', 'hunt', 'fish', 'explore', 'work')
JOB_NAMES={'forageFood':'сбор пищи','forageWater':'поиск воды','fish':'рыбалка','camp':'лагерь','hunt':'охота'}
CONDITIONS = {'hungry':'Голод', 'thirsty':'Жажда', 'sleepy':'Недосып', 'cold':'Переохлаждение'}
FUNCTIONS = {
    'fireplace': dict(name='Очаг', cost={'stone':20}, days=1, requires=[], builder=False, tools='Нет', effect='Тепло и освещение внутри цитадели.'),
    'bakery': dict(name='Пекарня', cost={'stone':200,'wood':40}, days=7, requires=['fireplace'], builder=True, tools='Кувалда, пила', effect='Повар или пекарь: до 12 муки → еда за четверть дня.'),
    'forge': dict(name='Кузница', cost={'stone':400,'iron':60}, days=7, requires=['fireplace'], builder=True, tools='Кувалда, молоток', effect='Кузнец: до 12 железной руды → железо за четверть дня.'),
    'tower': dict(name='Сторожевая башня (дерево)', cost={'wood':200}, days=14, requires=[], builder=True, tools='Пила, молоток', effect='+2 Наблюдательности, +1 защита цитадели. Эффекты применяет Мастер.'),
}
MATERIALS = ('wood','stone','iron','ore','flour','food','vegetables','meat','fish','pelts','copper')
HOOKS = {
    'plain': ['Старые межевые камни складываются в неизвестный герб.', 'Караван оставил колею, но все следы босых ног ведут обратно.'],
    'forest': ['В стволе дерева спрятана свежая карта без названий.', 'Из чащи зовут по имени человека, которого здесь никто не знает.'],
    'mountain': ['На перевале висит верёвка с недавно завязанными узлами.', 'Отражённый скалами сигнал повторяется с неожиданной стороны.'],
    'water': ['Пустая лодка привязана к камню посреди течения.', 'На отмели блестит печать с незнакомым знаком.'],
    'ruin': ['Ночью в заброшенной башне меняется свет в окнах.', 'Под обломками слышно размеренное дыхание.'],
    'stronghold': ['Гость предлагает услуги за право изучить старые стены.', 'Рабочие нашли замурованный проход и спорят, кому он принадлежит.'],
}

def integer(v, low, high, message='Некорректное число.'):
    if type(v)!=int or not low<=v<=high: raise ValueError(message)
    return v

def coordinate(d):
    if not isinstance(d,dict):raise ValueError('Нужны координаты гекса.')
    return {'x':integer(d.get('x'),0,23), 'y':integer(d.get('y'),0,15)}

def key(p): return f"{p['x']},{p['y']}"

def adjacent(a,b):
    aq=a['x']-(a['y']-a['y']%2)//2; bq=b['x']-(b['y']-b['y']%2)//2
    dq=bq-aq; dr=b['y']-a['y']
    return max(abs(dq),abs(dr),abs(dq+dr))==1

def dice(n, sides=6): return [secrets.randbelow(sides)+1 for _ in range(n)]

def journal(room,text): room['log'].append(dict(name='Путешествие',text=text))

def check(c,skill,mod=0,gear=0):
    attr={'survive':'wit','scout':'wit','endure':'str','craft':'str','shoot':'agi'}[skill]
    base=c.get('runtime',{}).get('current',c['sheet']['attrs']).get(attr,0)
    n=c['sheet']['skills'].get(skill,0)+mod
    a,b,g=dice(base),dice(abs(n)),dice(gear)
    net=a.count(6)+(1 if n>=0 else -1)*b.count(6)+g.count(6)
    return dict(character=c['id'],name=c['name'],skill=skill,base=a,skillDice=b,negative=n<0,gear=g,modifier=mod,hits=max(0,net),netHits=net)

def pending(room,category,source,roll=None):
    t=room['journey']; item=dict(id=secrets.token_hex(8),category=category,source=source,roll=roll,note='',revealed=False)
    t['pending'].append(item); return item

def state(room):
    return room.setdefault('journey',dict(day=1,quarter=0,season='spring',position={'x':0,'y':0},party=[],plans={},visited=[],history=[],pending=[],revision=0,hikes=0,session=1,homeDays={},encounterDay=0))

def fresh_stock(t):
    now=t['day']*4+t['quarter']
    t['batches']=[b for b in t.get('batches',[]) if b['expires']>now and b['amount']>0]
    t['finds']={k:sum(b['amount'] for b in t['batches'] if b['kind']==k) for k in ('vegetables','meat','fish')}
    t['finds']['pelts']=t.get('pelts',0)

def found(t,kind,amount,after=0):
    if kind=='pelts':t['pelts']=t.get('pelts',0)+amount
    else:t.setdefault('batches',[]).append(dict(kind=kind,amount=amount,expires=t['day']*4+t['quarter']+4+after))
    fresh_stock(t)

def counts_as_rest(c,p):
    talents=c['sheet'].get('talents',{})
    return p.get('job') in ('rest','sleep') or p.get('role')=='lead' and talents.get('pathfinder',0)>=2 or p.get('job')=='fish' and talents.get('fisher',0)>=2 or p.get('job') in ('forageFood','forageWater') and talents.get('herbalist',0)>=2 or p.get('job')=='hunt' and talents.get('masterhunt',0)>=2 or p.get('job')=='hike' and talents.get('wanderer',0)>=3

def apply(room,s,data):
    action=data['action']; gm=s['role']=='gm'; t=state(room)
    if data.get('revision')!=t['revision']: raise ValueError('Путешествие обновилось. Повторите действие после синхронизации.')
    if action not in ('travelPlan','travelConsume') and not gm: raise PermissionError('Действие доступно только Мастеру.')
    if room.get('combat',{}).get('phase')=='combat': raise ValueError('Сначала завершите активный бой.')
    if action=='travelSetup':
        ids=data.get('party'); p=coordinate(data); season=data.get('season')
        if not isinstance(ids,list) or not 1<=len(ids)<=11 or len(set(ids))!=len(ids): raise ValueError('Выберите 1–11 разных участников.')
        if any(not any(c['id']==cid and c['kind']!='monster' and not c.get('hidden') for c in room['characters']) for cid in ids): raise ValueError('Нужны открытые герои или ПВ.')
        if season not in ('spring','summer','autumn','winter'): raise ValueError('Неизвестное время года.')
        if t['pending']: raise ValueError('Сначала разрешите незавершённые события.')
        t.update(party=ids,position=p,season=season,mounted=data.get('mounted') is True,plans={})
        if key(p) not in t['visited']:t['visited'].append(key(p))
        journal(room,f"Отряд собран. Старт: {p['x']+1}, {p['y']+1}.")
    elif action=='travelPlan':
        cid=data.get('id'); c=next((c for c in room['characters'] if c['id']==cid),None)
        if cid not in t['party'] or not c or not gm and (c['owner']!=s['owner'] or c['kind']!='pc'): raise PermissionError('Выберите своего героя из отряда.')
        job=data.get('job'); role=data.get('role','none')
        if job not in JOBS or role not in ('none','lead','watch') or job!='hike' and role!='none': raise ValueError('Некорректное занятие или роль.')
        previous=t['plans'].get(cid,{})
        mod=integer(data.get('modifier',0),-10,10) if gm else previous.get('modifier',0)
        gear=integer(data.get('gear',0),0,10) if gm else previous.get('gear',0)
        t['plans'][cid]=dict(job=job,role=role,modifier=mod,gear=gear,scoutModifier=integer(data.get('scoutModifier',0),-10,10) if gm else previous.get('scoutModifier',0),endureModifier=integer(data.get('endureModifier',0),-10,10) if gm else previous.get('endureModifier',0),equipped=(data.get('equipped') is True if gm else previous.get('equipped',False)),darkvision=(data.get('darkvision') is True if gm else previous.get('darkvision',False)))
    elif action=='travelConditions':
        c=next((c for c in room['characters'] if c['id']==data.get('id') and c['kind']!='monster'),None)
        flags=data.get('conditions')
        if not c or not isinstance(flags,dict) or set(flags)!=set(CONDITIONS) or any(type(v)!=bool for v in flags.values()):raise ValueError('Укажите четыре состояния персонажа.')
        c.setdefault('runtime',{})['conditions']=flags
        journal(room,c['name']+': состояния — '+(', '.join(CONDITIONS[k] for k,v in flags.items() if v) or 'нет')+'.')
    elif action=='travelSupplies':
        c=next((c for c in room['characters'] if c['id']==data.get('id')),None)
        if not c or c['kind']=='monster':raise ValueError('Персонаж не найден.')
        res=data.get('resources')
        if not isinstance(res,dict) or set(res)!={'food','water'} or any(type(v)!=int or v not in (0,6,8,10,12) for v in res.values()):raise ValueError('Припасы: 0, D6, D8, D10 или D12.')
        c.setdefault('runtime',{})['resources']=res
    elif action=='travelConsume':
        c=next((c for c in room['characters'] if c['id']==data.get('id')),None)
        if not c or c['id'] not in t['party'] or not gm and (c['owner']!=s['owner'] or c['kind']!='pc'):raise PermissionError('Можно использовать припасы только своего героя.')
        res=data.get('resource')
        if res not in ('food','water'):raise ValueError('Нужны еда или вода.')
        rt=c.setdefault('runtime',{}); used=rt.setdefault('consumed',{})
        if used.get(res)==t['day']:raise ValueError('Суточная порция уже использована.')
        source=data.get('source')
        if source is not None:
            fresh_stock(t)
            if res!='food' or source not in ('vegetables','meat','fish') or not t['finds'][source]:raise ValueError('Свежая пища закончилась или испортилась.')
            batch=min((b for b in t['batches'] if b['kind']==source and b['amount']>0),key=lambda b:b['expires'])
            batch['amount']-=1;used[res]=t['day'];fresh_stock(t)
            rt.setdefault('conditions',{})['hungry']=False
            journal(room,c['name']+': использована одна единица найденной пищи ('+source+').');t['revision']+=1;return
        size=rt.get('resources',{}).get(res,0)
        if not size:raise ValueError('Припасы закончились. Используйте найденную пищу или пополните запасы через Мастера.')
        roll=dice(1,size)[0]; new=[0,6,8,10,12][[0,6,8,10,12].index(size)-1] if roll<=2 else size
        rt['resources'][res]=new;used[res]=t['day']
        rt.setdefault('conditions',{})['hungry' if res=='food' else 'thirsty']=False
        journal(room,f"{c['name']}: {'еда' if res=='food' else 'вода'} D{size} → {roll}; остаток {'D'+str(new) if new else 'пусто'}.")
    elif action=='travelFinds':
        kind=data.get('kind');amount=integer(data.get('amount'),1,100)
        if kind not in ('vegetables','meat','fish','pelts') or data.get('confirmed') is not True:raise ValueError('Подтвердите полученную добычу.')
        found(t,kind,amount);journal(room,'Мастер записал добычу: '+kind+' '+str(amount)+'.')
    elif action=='travelRecover':
        c=next((c for c in room['characters'] if c['id']==data.get('id') and c['kind']!='monster'),None)
        history=next((h for h in reversed(t['history']) if 'plans' in h),None)
        if not c or not history or not counts_as_rest(c,history['plans'].get(c['id'],{})) or data.get('confirmed') is not True:raise ValueError('Нужен завершённый отдых или сон (в том числе от достоинства); подтвердите отсутствие препятствующих состояний и прерываний.')
        if min(c['runtime']['current'].values())<=0:raise ValueError('Восстановление сломленного персонажа сначала разрешается по отдельным правилам.')
        flags=c['runtime'].setdefault('conditions',{})
        if history['plans'].get(c['id'],{}).get('job')=='sleep':flags['sleepy']=False
        blocked=set()
        if flags.get('hungry'):blocked.add('str')
        if flags.get('sleepy'):blocked.add('wit')
        if flags.get('cold'):blocked.update(('str','wit'))
        if flags.get('thirsty'):blocked.update(c['sheet']['attrs'])
        restored=[k for k in c['sheet']['attrs'] if k not in blocked]
        for k in restored:c['runtime']['current'][k]=c['sheet']['attrs'][k]
        journal(room,c['name']+': подтверждён отдых. Восстановлены: '+(', '.join({'str':'ТЕЛ','agi':'ЛОВ','wit':'РАЗ','emp':'ЭМП'}[k] for k in restored) or 'нет — мешают состояния')+'.')
    elif action=='travelResolve':
        item=next((p for p in t['pending'] if p['id']==data.get('id')),None)
        note=str(data.get('note','')).strip()[:1000]
        if not item or not note:raise ValueError('Укажите решение Мастера.')
        if data.get('position') is not None:t['position']=coordinate(data['position'])
        if data.get('reveal') is True:journal(room,item['category']+': '+note)
        t['pending'].remove(item);t['history'].append(dict(day=t['day'],quarter=t['quarter'],resolution=note,private=data.get('reveal') is not True))
    elif action=='travelEvent':
        location=data.get('location','journey')
        if location not in ('journey','stronghold'):raise ValueError('Неизвестный генератор.')
        terrain=room['maps']['world'].get(key(t['position']),{}).get('terrain','plain')
        category='stronghold' if location=='stronghold' else terrain
        hook=secrets.choice(HOOKS.get(category,HOOKS['forest' if terrain=='darkforest' else 'plain']))
        item=pending(room,'Авторская зацепка','Авторский генератор; не официальная таблица.')
        item['note']=hook
    elif action=='travelAdvance':
        advance(room,data)
    elif action=='travelSession':
        t['session']+=1;journal(room,f"Началась игровая сессия {t['session']}.")
    elif action.startswith('hold'):
        stronghold(room,data)
    else:raise ValueError('Неизвестное действие кампании.')
    t['revision']+=1;t['history']=t['history'][-100:]

def advance(room,data):
    t=room['journey']
    if not t['party']:raise ValueError('Сначала соберите отряд.')
    if t['pending']:raise ValueError('Сначала Мастер должен разрешить ожидающие события.')
    party=[next((c for c in room['characters'] if c['id']==cid and not c.get('hidden')),None) for cid in t['party']]
    if any(c is None for c in party):raise ValueError('Состав отряда изменился. Соберите его заново.')
    plans=t['plans']
    if any(c['id'] not in plans for c in party):raise ValueError('Каждый участник должен выбрать занятие.')
    if any(min(c['runtime']['current'].values())<=0 for c in party):raise ValueError('В отряде есть сломленный персонаж. Сначала разрешите его состояние по правилам.')
    hiking=all(plans[c['id']]['job']=='hike' for c in party)
    if any(plans[c['id']]['job']=='hike' for c in party) and not hiking:raise ValueError('Для перехода весь отряд должен идти. Разделение отряда пока разрешается отдельно.')
    lead=[c for c in party if plans[c['id']]['role']=='lead']; watch=[c for c in party if plans[c['id']]['role']=='watch' or plans[c['id']]['job']=='watch']
    campers=[c for c in party if plans[c['id']]['job']=='camp']
    if len(lead)>1 or len(watch)>1 or len(campers)>1 or hiking and len(lead)!=1:raise ValueError('Нужен один проводник для перехода; дозорный и устроитель лагеря — не более одного.')
    path=data.get('path',[])
    if not isinstance(path,list) or len(path)>3 or not hiking and path or hiking and not path:raise ValueError('Укажите маршрут из 1–3 соседних гексов для перехода.')
    position=t['position']; limit=3 if t.get('mounted') else 2; seen={key(position)}
    for p in path:
        p=coordinate(p)
        if not adjacent(position,p) or key(p) in seen:raise ValueError('Маршрут должен идти через разные соседние гексы.')
        seen.add(key(p)); terrain=room['maps']['world'].get(key(p),{}).get('terrain','plain'); speed=TERRAINS[terrain][1]
        if not speed:raise ValueError('Путь перекрыт или требует водного транспорта. Переправу разрешает Мастер отдельно.')
        limit=min(limit,1 if speed==1 else limit);position=p
    if len(path)>limit:raise ValueError('За четверть дня доступны 2 открытых гекса пешком, 3 верхом или 1 трудный гекс.')
    if sum(plans[c['id']]['job']=='fish' for c in party):
        water=[t['position']]+[dict(x=x,y=y) for x in range(24) for y in range(16) if adjacent(t['position'],dict(x=x,y=y))]
        if not any(room['maps']['world'].get(key(p),{}).get('terrain')=='water' for p in water):raise ValueError('Рыбалка требует соседнего водоёма.')
    for c in party:
        if plans[c['id']]['job'] in ('hunt','fish') and not plans[c['id']]['equipped']:raise ValueError('Мастер должен подтвердить снаряжение для охоты/рыбалки.')
    rolls=[]; oldday=t['day']; oldquarter=t['quarter']; completed=[]
    sheltered=any(h['position']==t['position'] for h in room.get('strongholds',[])) and all(plans[c['id']]['job'] in ('rest','sleep','work','watch','camp') for c in party)
    def rolled(c,skill,mod=0,gear=None):
        p=plans[c['id']];extra=p.get({'scout':'scoutModifier','endure':'endureModifier'}.get(skill,'modifier'),0)
        talent='pathfinder' if p['role']=='lead' else {'camp':'quartermaster','fish':'fisher','forageFood':'herbalist','forageWater':'herbalist','hunt':'masterhunt'}.get(p['job'])
        rank=c['sheet'].get('talents',{}).get(talent,0) if skill=='survive' else 0
        bonus=1 if rank>=1 else 0
        if skill=='scout' and c in watch and t.get('camp',{}).get('position')==t['position']:bonus+=t['camp'].get('watchBonus',0)
        r=check(c,skill,mod+extra+bonus,(p['gear'] if skill=='survive' else 0) if gear is None else gear)
        if rank>=3 and talent in ('pathfinder','quartermaster'):
            artifact=dice(1,8)[0];r['artifact']=artifact;r['hits']=max(0,r['netHits']+(2 if artifact==8 else 1 if artifact>=6 else 0))
        rolls.append(r);return r
    if hiking and t['hikes']>=2:
        if t.get('mounted'):raise ValueError('Форсированный марш верхом требует проверки животного. Пока разрешается Мастером отдельно.')
        fails=[]
        for c in party:
            if not rolled(c,'endure',-2 if t['hikes']>=3 else 0,0)['hits']:
                c['runtime']['current']['agi']=max(0,c['runtime']['current']['agi']-1);fails.append(c['name'])
        if fails:
            hiking=False;path=[];pending(room,'Форсированный марш: '+', '.join(fails),'Книга игрока, стр. 146. Отряд остановлен; отдых/сон и разделение решает Мастер.')
    dark=t['quarter'] not in ({'spring':(0,1),'summer':(0,1,2),'autumn':(0,1),'winter':(1,)}[t['season']])
    if hiking:
        t.pop('camp',None)
        t['hikes']+=1
        if dark:
            for c in party:
                if not plans[c['id']]['darkvision'] and not rolled(c,'scout',0,0)['hits']:
                    c['runtime']['current']['str']=max(0,c['runtime']['current']['str']-1)
        for p in path:
            t['position']=coordinate(p);completed.append(key(p))
            if key(p) in room['maps']['world']:room['maps']['world'][key(p)]['hidden']=False
            new=key(p) not in t['visited']
            if new:t['visited'].append(key(p))
            if new and not rolled(lead[0],'survive',-2 if dark else 0)['hits']:
                pending(room,'Неприятность проводника','Книга игрока, стр. 148–149; последствия и дальнейшее перемещение решает Мастер.',10*dice(1)[0]+dice(1)[0]);break
    elif not path and not t['pending']:
        terrain=room['maps']['world'].get(key(t['position']),{}).get('terrain','plain'); season={'spring':-1,'summer':0,'autumn':1,'winter':-2}[t['season']]
        for c in party:
            p=plans[c['id']];job=p['job']
            if job=='camp' and sheltered:
                t['camp']=dict(position=t['position'].copy(),day=t['day'],watchBonus=0)
                continue
            if job in ('forageFood','forageWater','fish','camp','hunt'):
                mod=TERRAINS[terrain][2]+season if job.startswith('forage') else TERRAINS[terrain][3] if job=='hunt' else 0
                r=rolled(c,'survive',mod)
                if job=='camp':t['camp']=dict(position=t['position'].copy(),day=t['day'],watchBonus=2 if c['sheet'].get('talents',{}).get('quartermaster',0)>=2 else 0)
                if not r['hits']:
                    page={'forageFood':'150','forageWater':'150','fish':'153','camp':'154–155','hunt':'152'}[job]
                    die=10*dice(1)[0]+dice(1)[0] if job in ('camp','forageFood','forageWater') else dice(1)[0]
                    pending(room,f"{c['name']}: {JOB_NAMES[job]}",f'Неприятность: Книга игрока, стр. {page}.',die)
                elif job=='forageWater':
                    for member in party:member['runtime'].setdefault('resources',{})['water']=12
                elif job in ('forageFood','fish'):
                    multiplier=2 if c['sheet'].get('talents',{}).get('herbalist' if job=='forageFood' else 'fisher',0)>=3 else 1
                    found(t,'vegetables' if job=='forageFood' else 'fish',r['hits']*multiplier,after=1)
                elif job=='hunt':
                    item=pending(room,c['name']+': добыча найдена','Книга игрока, стр. 152–153: выберите добычу (переброс за дополнительные успехи), затем Стрельба или Выживание для ловушки. Запишите мясо и шкуры вручную.',dice(1)[0])
                    if c['sheet'].get('talents',{}).get('masterhunt',0)>=3:item['note']='Мастер охоты 3: второй вариант добычи '+str(dice(1)[0])+'.'
            elif job in ('sleep','rest'):
                journal(room,c['name']+': '+('сон' if job=='sleep' else 'отдых')+'. Восстановление подтверждает Мастер с учётом состояний и прерываний.')
                if job=='sleep':c['runtime']['sleptDay']=t['day']
    if hiking or not sheltered and t['encounterDay']!=t['day']:
        terrain=room['maps']['world'].get(key(t['position']),{}).get('terrain','plain')
        item=pending(room,'Проверка случайной встречи','Руководство ведущего, глава 7. Местность: '+TERRAINS[terrain][0]+'. Проверка раз в четверть дня в пути, раз в день на стоянке.',10*dice(1)[0]+dice(1)[0])
        if watch:item['scouting']=rolled(watch[0],'scout')
        item['note']='Дозорный: '+(watch[0]['name'] if watch else ('проводник, если путешествует один' if len(party)==1 else 'не назначен'))+'. Предварительный дозор применим к угрозе; для активной засады требуется встречная проверка.'
        if len(party)==1 and not watch:item['scouting']=rolled(party[0],'scout')
        t['encounterDay']=t['day']
    for h in room.get('strongholds',[]):
        at_home=h['position']==t['position']
        h['homeQuarters']=h.get('homeQuarters',0)+1 if at_home and not hiking else 0
        if at_home and h['homeQuarters']>=4:
            for c in party:
                if c['kind']=='pc' and c['runtime'].get('homeWPsession')!=t['session']:
                    c['runtime']['wp']=min(10,c['runtime'].get('wp',0)+1);c['runtime']['homeWPsession']=t['session'];journal(room,c['name']+': +1 СВ за день дома (один раз за сессию).')
    t['history'].append(dict(day=oldday,quarter=oldquarter,path=completed,rolls=rolls,plans={cid:p.copy() for cid,p in plans.items()}))
    trail=['{}, {}'.format(*(int(n)+1 for n in k.split(','))) for k in completed]
    journal(room,f"День {oldday}, {('утро','день','вечер','ночь')[oldquarter]}: "+(' → '.join(trail) if completed else 'стоянка')+'.')
    t['quarter']=(t['quarter']+1)%4
    if t['quarter']==0:
        t['day']+=1;t['hikes']=0
        for c in party:
            rt=c['runtime'];missing=[label for k,label in [('food','еда'),('water','вода')] if rt.get('consumed',{}).get(k)!=oldday]
            if rt.get('sleptDay')!=oldday:missing.append('сон')
            if missing:pending(room,c['name']+': суточные потребности','Книга игрока, стр. 110–111: проверьте состояния, исключения народов/достоинств и полученную пищу. '+', '.join(missing))
        for h in room.get('strongholds',[]):
            if t['day']-h.get('reviewDay',1)>=7:pending(room,'Еженедельная проверка: '+h['name'],'Книга игрока, стр. 162–165: оплата, охрана, обслуживание; Руководство ведущего, стр. 12–13: события цитадели. Заполните отметку проверки.')
    fresh_stock(t);t['plans']={}

def stronghold(room,data):
    t=room['journey'];action=data['action'];holds=room.setdefault('strongholds',[])
    if action=='holdCreate':
        if len(holds)>=10:raise ValueError('Предел: десять цитаделей.')
        name=str(data.get('name','')).strip()[:80]
        if not name or data.get('confirmed') is not True:raise ValueError('Мастер должен подтвердить очищенное и обустроенное место (Ремесло, минимум две четверти дня).')
        p=coordinate(data)
        holds.append(dict(id=secrets.token_hex(8),name=name,position=p,stock={k:0 for k in MATERIALS},functions=[],projects=[],hirelings=[],notes='',reviewDay=t['day'],homeQuarters=0))
        journal(room,'Основана цитадель «'+name+'».');return
    h=next((h for h in holds if h['id']==data.get('hold')),None)
    if not h:raise ValueError('Цитадель не найдена.')
    if action=='holdRoll':
        category=data.get('category')
        if category=='guarded':
            rating=integer(data.get('reputation'),0,20);modifier=integer(data.get('modifier',0),-10,10)
            pool=dice(max(1,rating+modifier));units=dice(1)[0]
            item=pending(room,'Событие цитадели: '+h['name'],'Руководство ведущего, стр. 12–13: старшая кость репутации задаёт десятки D66.',max(pool)*10+units)
            item['note']='Кости репутации: '+str(pool)+'. Единицы: '+str(units)+'.'
        elif category in ('unguarded','upkeep','unpaid'):
            source={'unguarded':'164 (без охраны)','upkeep':'165 (без обслуживания)','unpaid':'162 (неоплата)'}[category]
            pending(room,'Проверка цитадели: '+h['name'],'Книга игрока, стр. '+source+'. Последствия применяет Мастер.',dice(1)[0])
        else:raise ValueError('Неизвестная таблица.')
    elif action=='holdStock':
        changes=data.get('stock')
        if not isinstance(changes,dict) or set(changes)!=set(MATERIALS):raise ValueError('Некорректный склад.')
        h['stock']={k:integer(v,0,1000000) for k,v in changes.items()}
        journal(room,'Обновлён склад: '+h['name']+'.')
    elif action=='holdBuild':
        fid=data.get('function');f=FUNCTIONS.get(fid)
        if not f:raise ValueError('Неизвестная постройка.')
        if fid in h['functions'] or any(p['function']==fid for p in h['projects']):raise ValueError('Постройка уже есть или строится.')
        if any(k not in h['functions'] for k in f['requires']):raise ValueError('Сначала постройте очаг.')
        if data.get('confirmed') is not True:raise ValueError('Подтвердите успешное Ремесло, инструменты и необходимые достоинства.')
        if any(h['stock'][k]<v for k,v in f['cost'].items()):raise ValueError('Недостаточно материалов.')
        for k,v in f['cost'].items():h['stock'][k]-=v
        h['projects'].append(dict(id=secrets.token_hex(8),function=fid,work=0,required=f['days']*2))
        journal(room,h['name']+': начато строительство «'+f['name']+'».')
    elif action=='holdWork':
        project=next((p for p in h['projects'] if p['id']==data.get('project')),None)
        if not project:raise ValueError('Проект не найден.')
        if t['position']!=h['position']:raise ValueError('Отряд должен находиться в цитадели. Работу наёмников отмечает Мастер после возвращения.')
        if project.get('lastWork')==[t['day'],t['quarter']]:raise ValueError('Эта четверть дня уже учтена.')
        if data.get('confirmed') is not True:raise ValueError('Подтвердите фактическую работу в эту четверть дня.')
        project['lastWork']=[t['day'],t['quarter']];project['work']+=1
        if project['work']>=project['required']:
            h['functions'].append(project['function']);h['projects'].remove(project);journal(room,h['name']+': завершена «'+FUNCTIONS[project['function']]['name']+'». Проверьте репутацию и эффекты.')
    elif action=='holdHire':
        name=str(data.get('name','')).strip()[:60];job=str(data.get('job','')).strip()[:60]
        if not name or not job or len(h['hirelings'])>=50 or data.get('confirmed') is not True:raise ValueError('Подтвердите найденного кандидата, успешное Воздействие и требования найма.')
        wage=integer(data.get('wage'),0,10000)
        h['hirelings'].append(dict(id=secrets.token_hex(8),name=name,job=job,wage=wage,paidThrough=t['day']-1))
    elif action=='holdPay':
        person=next((p for p in h['hirelings'] if p['id']==data.get('person')),None)
        if not person:raise ValueError('Наёмник не найден.')
        days=integer(data.get('days'),1,30);cost=days*person['wage']
        if h['stock']['copper']<cost:raise ValueError('Недостаточно монет на складе.')
        h['stock']['copper']-=cost;person['paidThrough']=max(t['day']-1,person['paidThrough'])+days
        journal(room,h['name']+': выплачено '+str(cost)+' медных, '+person['name']+'.')
    elif action=='holdReview':
        note=str(data.get('note','')).strip()[:1500]
        if not note:raise ValueError('Запишите состояние охраны, обслуживания и оплаты.')
        h['reviewDay']=t['day'];h['notes']=note
        journal(room,h['name']+': проверка хозяйства — '+note)
    elif action=='holdProduce':
        fid=data.get('function')
        if fid not in ('forge','bakery') or fid not in h['functions'] or data.get('confirmed') is not True:raise ValueError('Нужны готовая постройка и подтверждение квалифицированного работника.')
        last=h.setdefault('production',{})
        if last.get(fid)==[t['day'],t['quarter']]:raise ValueError('Производство за эту четверть дня уже учтено.')
        n=integer(data.get('amount'),1,12);source,target=('ore','iron') if fid=='forge' else ('flour','food')
        if h['stock'][source]<n:raise ValueError('Недостаточно сырья.')
        h['stock'][source]-=n;h['stock'][target]+=n;last[fid]=[t['day'],t['quarter']]
        journal(room,h['name']+': произведено '+str(n)+' '+target+'.')
    else:raise ValueError('Неизвестное действие цитадели.')
