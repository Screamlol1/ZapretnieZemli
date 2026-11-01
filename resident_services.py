"""Resident offers and reviewed contracts. Prices/availability are GM-authored.

Purchases are atomic campaign actions. Service quotes reserve no money; completing
a contract charges the agreed price exactly once. Teaching grants prerequisites,
never XP or a free rank. Repairs reuse the ordinary final-result rule.
"""
import copy
import secrets
from inventory_rules import character, editable, ensure, validate, text, number
from injuries import now


def visible_residents(room):
    from location_maps import redact
    probe=dict(locationMaps=copy.deepcopy(room.get('locationMaps',[])),characters=room['characters'],maps=dict(world=copy.deepcopy(room['maps']['world'])));redact(probe)
    return {(m['id'],r['id']) for m in probe.get('locationMaps',[]) for r in m.get('population',{}).get('residents',[])}


def resident(room, mid, rid, s):
    m=next((m for m in room.get('locationMaps',[]) if m['id']==mid),None)
    r=next((r for r in (m or {}).get('population',{}).get('residents',[]) if r['id']==rid),None)
    if not r or s['role']!='gm' and (mid,rid) not in visible_residents(room):raise PermissionError('Житель пока недоступен.')
    return m,r


def wallet(c, cost):
    coins=c['runtime'].get('coins',{})
    total=sum(coins.get(k,0)*v for k,v in [('gold',100),('silver',10),('copper',1)])
    if total<cost:raise ValueError(f'Недостаточно монет: нужно {cost} медных, есть {total}.')
    total-=cost
    return dict(gold=total//100,silver=total%100//10,copper=total%10)


def apply(room,s,d):
    gm=s['role']=='gm';op=d.get('op')
    store=room.setdefault('residentServices',dict(offers=[],contracts=[],relations=[]))
    if op in ('offer','relation'):
        if not gm:raise PermissionError('Предложения и отношение жителей задаёт Мастер.')
        m,r=resident(room,d.get('map'),d.get('resident'),s)
        if op=='relation':
            row=next((x for x in store['relations'] if x['map']==m['id'] and x['resident']==r['id']),None)
            if row and d.get('version')!=row['version']:raise ValueError('Отношение уже изменилось. Откройте карточку заново.')
            value=dict(map=m['id'],resident=r['id'],attitude=text(d.get('attitude',''),100),interest=text(d.get('interest',''),400),quest=text(d.get('quest',''),1000),gmNote=text(d.get('gmNote',''),1000),version=(row or {}).get('version',0)+1)
            if row:store['relations'].remove(row)
            store['relations'].append(value);return
        old=next((x for x in store['offers'] if x['id']==d.get('id')),None)
        if old and (old['map']!=m['id'] or old['resident']!=r['id'] or old['version']!=d.get('version')):raise ValueError('Предложение уже изменилось.')
        kind=d.get('kind')
        if kind not in ('goods','repair','training','service','quest'):raise ValueError('Выберите вид предложения.')
        title=text(d.get('title',''),100)
        if not title:raise ValueError('Укажите название предложения.')
        value=dict(id=old['id'] if old else secrets.token_hex(8),version=(old or {}).get('version',0)+1,map=m['id'],resident=r['id'],kind=kind,title=title,price=number(d.get('price',0),100000,True),stock=number(d.get('stock',1),999,True),minutes=number(d.get('minutes',0),525600,True),terms=text(d.get('terms',''),1000),active=d.get('active') is True)
        if kind=='goods':value['item']=validate(d.get('item',dict(name=title)))
        if kind=='training':
            from progression import SKILLS
            if d.get('skill') not in SKILLS:raise ValueError('Выберите навык для обучения.')
            value.update(skill=d['skill'],teacherRank=number(d.get('teacherRank',1),5,True),minutes=max(360,value['minutes']))
            if not value['teacherRank']:raise ValueError('У учителя навык должен быть не ниже 1.')
        if old:store['offers'].remove(old)
        elif len(store['offers'])>=1000:raise ValueError('Предел: 1000 предложений в кампании.')
        store['offers'].append(value);return
    if op in ('buy','request'):
        offer=next((o for o in store['offers'] if o['id']==d.get('offer')),None)
        if not offer or offer['version']!=d.get('version') or not offer['active']:raise ValueError('Предложение изменилось или закрыто. Откройте его заново.')
        m,r=resident(room,offer['map'],offer['resident'],s)
        c=character(room,d.get('character'));editable(room,dict(kind='character',id=c['id']),s);ensure(room,c['id'])
        if op=='buy':
            if offer['kind']!='goods':raise ValueError('Для услуги оформите заказ.')
            count=number(d.get('count',1),999,True)
            if not count or count>offer['stock']:raise ValueError('Такого количества нет в наличии.')
            raw=copy.deepcopy(offer['item']);raw['quantity']*=count;item=validate(raw)
            if len(room.setdefault('items',[]))>=1000:raise ValueError('Предел: 1000 предметов кампании.')
            coins=wallet(c,offer['price']*count)
            room['items'].append(dict(**item,id=secrets.token_hex(8),version=1,wear=0,location=dict(kind='character',id=c['id'])))
            c['runtime']['coins']=coins;c['equipmentVersion']=c.get('equipmentVersion',0)+1
            offer['stock']-=count;offer['version']+=1
            message=f"{c['name']}: куплено «{offer['title']}» ×{count} у {r['name']} за {offer['price']*count} медных."
        else:
            if offer['kind']=='goods':raise ValueError('Товары покупаются сразу.')
            if offer['kind']=='training' and (c['kind']!='pc' or c['sheet']['skills'][offer['skill']]!=0):raise ValueError('Этот курс даёт основание изучить новый навык с нуля. Повышение известных навыков доступно в развитии.')
            if len(store['contracts'])>=500:raise ValueError('Предел: 500 заказов в кампании.')
            item=None
            if offer['kind']=='repair':
                from inventory_repair import repair_stat
                item=next((i for i in room.get('items',[]) if i['id']==d.get('item') and i['location']==dict(kind='character',id=c['id'])),None)
                if not item:raise ValueError('Выберите повреждённый предмет своего персонажа.')
                repair_stat(item)
            if any(x['status']=='requested' and x['character']==c['id'] and x['quote']['id']==offer['id'] for x in store['contracts']):raise ValueError('Такой заказ уже ожидает выполнения.')
            wallet(c,offer['price'])
            store['contracts'].append(dict(id=secrets.token_hex(8),version=1,quote=copy.deepcopy(offer),character=c['id'],owner=c['owner'],status='requested',createdAt=now(room),dueAt=now(room)+offer['minutes'],item=item['id'] if item else '',itemVersion=item['version'] if item else None))
            message=f"{c['name']}: заказ «{offer['title']}» у {r['name']}. Оплата после подтверждения выполнения."
    elif op in ('complete','cancel'):
        contract=next((x for x in store['contracts'] if x['id']==d.get('contract')),None)
        if not contract or contract['version']!=d.get('version') or contract['status']!='requested':raise ValueError('Заказ уже изменился или завершён.')
        c=character(room,contract['character']);editable(room,dict(kind='character',id=c['id']),s)
        if op=='complete' and not gm:raise PermissionError('Выполнение подтверждает Мастер.')
        quote=contract['quote'];note=text(d.get('note',''),500)
        if op=='complete':
            if d.get('confirmed') is not True or len(note)<3:raise ValueError('Подтвердите выполненную работу и запишите результат.')
            if now(room)<contract['dueAt']:raise ValueError('Согласованное игровое время ещё не прошло.')
            coins=wallet(c,quote['price'])
            if quote['kind']=='repair':
                from inventory_repair import finish,repair_stat
                item=next((i for i in room['items'] if i['id']==contract['item'] and i['location']==dict(kind='character',id=c['id'])),None)
                if not item or item['version']!=contract['itemVersion'] or item.get('repair'):raise ValueError('Предмет изменился. Отмените заказ и оформите новый.')
                hits=number(d.get('hits'),30,True)
                note+=' '+finish(room,c,item,dict(hits=hits,pushed=False,private=False),repair_stat(item))
            if quote['kind']=='training':
                from progression import apply as progression,initialize
                p=initialize(c['sheet'])
                progression(room,s,dict(id=c['id'],operation='training',revision=p['revision'],skill=quote['skill'],method='teacher',confirmed=True,note=note))
            c['runtime']['coins']=coins;c['equipmentVersion']=c.get('equipmentVersion',0)+1
        contract.update(status='completed' if op=='complete' else 'cancelled',version=contract['version']+1,result=note,finishedAt=now(room))
        message=f"{c['name']}: {quote['title']} — {'выполнено' if op=='complete' else 'отменено без оплаты'}. {note}"
    else:raise ValueError('Неизвестное действие жителя.')
    source=offer if op in ('buy','request') else quote
    private=c.get('hidden') or (source['map'],source['resident']) not in visible_residents(room)
    room.setdefault('log',[]).append(dict(name='Поселение',text=message,private=bool(private)))


def project(room,s):
    store=room.get('residentServices')
    if not store or s['role']=='gm':return
    visible=visible_residents(room)
    store['offers']=[{**o,'item':{k:v for k,v in o['item'].items() if k!='gmNote'}} if 'item' in o else o for o in store['offers'] if o['active'] and (o['map'],o['resident']) in visible]
    store['relations']=[{k:v for k,v in r.items() if k!='gmNote'} for r in store['relations'] if (r['map'],r['resident']) in visible]
    store['contracts']=[{**x,'quote':{k:v for k,v in x['quote'].items() if k!='item'}} for x in store['contracts'] if x['owner']==s['owner'] and (x['quote']['map'],x['quote']['resident']) in visible]
