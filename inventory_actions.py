"""Versioned stack operations and PH p. 38 consumable dice."""
import secrets
from dice_events import publish, group, visibility
from equipment_rules import clear_slots

RESOURCE_NAMES=dict(food='Еда',water='Вода',arrows='Стрелы',torches='Факелы')
STEPS=(0,6,8,10,12)


def apply(room,s,data):
    from inventory_rules import character, destination, editable, ensure, owns, number, text, ITEM_ART
    action=data['action'];gm=s['role']=='gm'
    if action=='inventoryResource':
        location=destination(room,dict(kind='character',id=data.get('character')),s)
        if not gm and not owns(room,location,s):raise PermissionError('Можно управлять припасами только своего героя.')
        if data.get('revision')!=room['revision']:raise ValueError('Припасы или кампания изменились. Проверьте актуальные значения и повторите действие.')
        c=character(room,location['id']);resource=data.get('resource');op=data.get('op')
        if resource not in RESOURCE_NAMES:raise ValueError('Выберите еду, воду, стрелы или факелы.')
        if room.get('combat',{}).get('pendingRisk'):raise ValueError('Сначала завершите текущий боевой бросок.')
        ensure(room,c['id']);rt=c['runtime'];stock=rt.setdefault('resources',{});size=stock.get(resource,0)
        if 'expectedValue' in data and data['expectedValue']!=size:raise ValueError('Этот запас изменился. Закройте окно, проверьте новое значение и откройте действие заново.')
        private=visibility(s,data) or bool(c.get('hidden'))
        if op=='use':
            if resource in ('food','water'):
                if room.get('combat',{}).get('phase')=='combat':raise ValueError('Используйте суточную порцию после завершения боя.')
                used=rt.setdefault('consumed',{})
                if used.get(resource)==room['journey']['day']:raise ValueError('Суточная порция уже использована.')
            if size not in STEPS[1:]:raise ValueError('Этот запас закончился. Пополните его или получите от другого персонажа.')
            roll=secrets.randbelow(size)+1
            new=STEPS[STEPS.index(size)-1] if roll<=2 else size
            stock[resource]=new
            if resource in ('food','water'):
                rt['consumed'][resource]=room['journey']['day']
                rt.setdefault('conditions',{})['hungry' if resource=='food' else 'thirsty']=False
            dice=group('table',[roll],size);dice['label']=RESOURCE_NAMES[resource]
            publish(room,c['name'],'Расход: '+RESOURCE_NAMES[resource],[dice],f"Запас D{size} → {'D'+str(new) if new else 'пусто'}. "+('Запас уменьшился.' if new!=size else 'Запас сохранился.'),private=private)
        elif op=='set':
            if not gm:raise PermissionError('Пополнение и исправление запасов записывает Мастер.')
            editable(room,location,s)
            value=data.get('value')
            if type(value)!=int or value not in STEPS:raise ValueError('Запас: пусто, D6, D8, D10 или D12.')
            note=text(data.get('note',''),300)
            if not note:raise ValueError('Укажите источник припасов или причину исправления.')
            stock[resource]=value
            room['log'].append(dict(name=s['name'],text=f"{c['name']}: {RESOURCE_NAMES[resource]} — {'D'+str(value) if value else 'пусто'}. {note}",private=private))
        elif op=='share':
            editable(room,location,s)
            target=destination(room,dict(kind='character',id=data.get('target')),s)
            if target==location:raise ValueError('Выберите другого персонажа.')
            editable(room,target,{**s,'role':'gm'});ensure(room,target['id']);other=character(room,target['id'])
            other_stock=other['runtime'].setdefault('resources',{});other_size=other_stock.get(resource,0)
            steps=number(data.get('steps'),4,True)
            if not steps or size not in STEPS or other_size not in STEPS:raise ValueError('Укажите от 1 до 4 ступеней запаса.')
            a,b=STEPS.index(size),STEPS.index(other_size)
            if steps>a:raise ValueError('Недостаточно запаса для передачи.')
            if b+steps>4:raise ValueError('У получателя не поместится столько: предел запаса — D12.')
            stock[resource]=STEPS[a-steps];other_stock[resource]=STEPS[b+steps]
            room['log'].append(dict(name=s['name'],text=f"Переданы припасы: {RESOURCE_NAMES[resource]}, ступеней: {steps}.",private=private or bool(other.get('hidden'))))
        else:raise ValueError('Неизвестное действие с припасами.')
        return

    item=next((i for i in room.get('items',[]) if i['id']==data.get('id')),None)
    if not item:raise ValueError('Предмет не найден.')
    editable(room,item['location'],s)
    if data.get('version')!=item['version']:raise ValueError('Предмет уже изменён. Обновите инвентарь.')
    if action=='itemAppearance':
        art=data.get('art','')
        if art not in ('',*ITEM_ART):raise ValueError('Выберите картинку из набора.')
        item['art']=art
    elif action=='itemSplit':
        quantity=number(data.get('quantity'),item['quantity']-1,True)
        if quantity<1:raise ValueError('Для разделения нужны хотя бы два предмета.')
        if len(room['items'])>=1000:raise ValueError('Предел предметов кампании: 1000.')
        room['items'].append({**item,'id':secrets.token_hex(8),'version':1,'quantity':quantity})
        item['quantity']-=quantity
    elif action=='itemConsume':
        quantity=number(data.get('quantity'),item['quantity'],True)
        if quantity<1 or data.get('confirmed') is not True:raise ValueError('Подтвердите количество потраченных или убранных предметов.')
        item['quantity']-=quantity
        if not item['quantity']:
            clear_slots(room,item['id']);room['items']=[i for i in room['items'] if i['id']!=item['id']]
        room['log'].append(dict(name=s['name'],text='Списаны предметы из инвентаря: '+str(quantity)+'.',private=gm))
    elif action=='itemMerge':
        other=next((i for i in room['items'] if i['id']==data.get('target') and i['location']==item['location']),None)
        if not other or other['id']==item['id']:raise ValueError('Выберите другую стопку в этом инвентаре.')
        if data.get('targetVersion')!=other['version']:raise ValueError('Вторая стопка изменилась.')
        equipped={v for c in room['characters'] for v in c.get('equipment',{}).values()}
        if item['id'] in equipped or other['id'] in equipped:raise ValueError('Перед объединением снимите предметы.')
        signature=lambda i:{k:v for k,v in i.items() if k not in ('id','version','quantity') and not (k=='art' and not v)}
        if signature(item)!=signature(other):raise ValueError('Объединить можно только предметы с полностью одинаковыми свойствами и износом.')
        if item['quantity']+other['quantity']>999:raise ValueError('В стопке может быть не больше 999 предметов.')
        item['quantity']+=other['quantity'];room['items'].remove(other)
    else:raise ValueError('Неизвестное действие с предметом.')
    item['version']+=1
