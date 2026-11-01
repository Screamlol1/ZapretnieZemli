"""Explicit, revisioned campaign choices. Enabling a catalog never grants ranks."""
import copy
import secrets
from inventory_rules import text

MODULES={'reforgedSpells':'Заклинания Reforged Power 3.3','advancedMagic':'Подтверждённые ранги магических путей 4–5','magicReactions':'Окно ответного рассеивания'}
SCHOOLS={'healing','shapes','sight','signs','stone','blood','death','ice','elements','nature','swarm','magma','mentalism','dream','magnetism'}
SOURCES=[dict(id='official',name='Forbidden Lands Player’s Handbook',version='2nd printing',scope='Базовые правила и 68 заклинаний. Дополнения обозначаются на карточке.'),dict(id='errata',name='Официальные исправления',version='проверяемые изменения по подсистемам',scope='Не означает автоматическое включение всех изменений пятого тиража. Применённые исправления указаны в документации соответствующих механик.'),dict(id='reforged',name='Reforged Power',version='3.3',scope='Отдельный модуль заклинаний. Обучение по Wits, лимит известных заклинаний и изменение гримуаров не включаются вместе с каталогом.'),dict(id='house',name='Правила этой кампании',version='по журналу паспорта',scope='Штрафные кости бросаются отдельно по запросу пользователя. Существующий общий запас воли ПВ сохраняется; это не правило пятого тиража.')]

def ensure(room):
    p=room.setdefault('rulePassport',{})
    p.setdefault('version',1);p.setdefault('revision',0)
    modules=p.setdefault('modules',{})
    for key in MODULES:modules.setdefault(key,False)
    p.setdefault('houseNotes','');p.setdefault('history',[]);p.setdefault('trainingRequests',[])
    p['sources']=copy.deepcopy(SOURCES)
    return p

def enabled(room,key):return room.get('rulePassport',{}).get('modules',{}).get(key) is True
def gm(s):
    if s.get('role')!='gm':raise PermissionError('Паспорт правил и допуск к школам подтверждает Мастер.')
def char(room,cid):
    c=next((x for x in room.get('characters',[]) if x['id']==cid),None)
    if not c or c['kind']=='monster':raise ValueError('Выберите персонажа, способного изучать магию.')
    return c
def owns(c,s):return s.get('role')=='gm' or c['kind']=='pc' and c.get('owner')==s.get('owner') and not c.get('hidden')
def entry(p,room,message):
    p['revision']+=1;p['history']=(p['history']+[dict(revision=p['revision'],clock=room.get('medicalClock',0),text=message)])[-50:]
    room.setdefault('log',[]).append(dict(name='Правила кампании',text=message,private=False))

def apply(room,s,data):
    p=ensure(room);op=data.get('op')
    if op=='configure':
        gm(s)
        if data.get('revision')!=p['revision']:raise ValueError('Паспорт изменился. Обновите страницу перед сохранением.')
        if any(x.get('status') not in ('resolved','cancelled') for x in room.get('magicCastings',[])):raise ValueError('Завершите текущую магию перед изменением правил.')
        modules=data.get('modules')
        if not isinstance(modules,dict) or set(modules)!=set(MODULES) or any(type(v)!=bool for v in modules.values()):raise ValueError('Неверный набор модулей правил.')
        if modules['advancedMagic'] and not modules['reforgedSpells']:raise ValueError('Высшие ранги требуют включённого модуля Reforged.')
        note=text(data.get('note',''),500)
        if not note:raise ValueError('Запишите причину изменения правил для участников.')
        p['modules']=copy.deepcopy(modules);p['houseNotes']=text(data.get('houseNotes',''),4000)
        entry(p,room,'Паспорт обновлён: '+note);return
    if op=='requestTraining':
        c=char(room,data.get('character'))
        if not owns(c,s):raise PermissionError('Заявляйте обучение только своего персонажа.')
        if not enabled(room,'reforgedSpells'):raise ValueError('Мастер ещё не включил модуль Reforged.')
        school=data.get('school');level=data.get('rank')
        if school not in SCHOOLS or type(level)!=int or not 1<=level<=(5 if enabled(room,'advancedMagic') else 3):raise ValueError('Выберите доступную школу и ранг.')
        from magic_rules import rank
        if level!=rank(c,school)+1:raise ValueError('Изучается следующий ранг уже известной школы либо первый ранг новой.')
        if any(r['character']==c['id'] and r['status']=='requested' for r in p['trainingRequests']):raise ValueError('У персонажа уже есть заявка обучения.')
        note=text(data.get('note',''),1000)
        if not note:raise ValueError('Укажите учителя, подготовку, время обучения и как учтён опыт.')
        p['trainingRequests']=(p['trainingRequests']+[dict(id=secrets.token_hex(12),character=c['id'],school=school,rank=level,status='requested',note=note)])[-100:]
        p['revision']+=1;return
    if op=='decideTraining':
        gm(s);r=next((r for r in p['trainingRequests'] if r['id']==data.get('request')),None)
        if not r or r['status']!='requested':raise ValueError('Заявка обучения уже обработана или не найдена.')
        note=text(data.get('note',''),1000)
        if not note:raise ValueError('Укажите конкретное основание допуска или отказа.')
        accepted=data.get('accept') is True;c=char(room,r['character'])
        if accepted:
            if not enabled(room,'reforgedSpells') or r['rank']>3 and not enabled(room,'advancedMagic'):raise ValueError('Нужный модуль выключен.')
            from magic_rules import rank
            if rank(c,r['school'])+1!=r['rank']:raise ValueError('Ранг изменился с момента заявки. Отклоните её и подайте актуальную.')
            if data.get('confirmed') is not True:raise ValueError('Подтвердите предпосылки школы, обучение и отдельный учёт опыта.')
            c.setdefault('runtime',{}).setdefault('magicTraining',{})[r['school']]=dict(rank=r['rank'],basis=note,request=r['id'])
        r.update(status='accepted' if accepted else 'declined',verdict=note)
        # Hidden NPC identities never enter the public passport journal.
        entry(p,room,('Допуск к школе подтверждён.' if accepted else 'Заявка обучения отклонена.')+' '+('Подробности скрыты Мастером.' if c.get('hidden') else c['name']+': '+note));return
    raise ValueError('Неизвестная команда паспорта правил.')

def project(room,s):
    p=ensure(room)
    if s.get('role')!='gm':
        p['trainingRequests']=[r for r in p['trainingRequests'] if any(c['id']==r['character'] and owns(c,s) for c in room.get('characters',[]))]
        for c in room.get('characters',[]):
            if not owns(c,s):c.get('runtime',{}).pop('magicTraining',None)
