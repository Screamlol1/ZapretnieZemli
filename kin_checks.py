"""Contextual kin powers for ordinary skill checks (PHB 62–63)."""
import secrets
from dice_events import publish, pools
from inventory_rules import character, editable, text


def apply(room,s,data):
    from skill_checks import ATTRS, signature, count
    c=character(room,data.get('character'));editable(room,dict(kind='character',id=c['id']),s)
    if c['kind']!='pc':raise ValueError('Эта кнопка предназначена для способности героя.')
    rt=c['runtime'];kin=c['sheet']['kin'];op=data.get('op');gm=s['role']=='gm'
    if op=='requestAdaptation':
        if kin!='human':raise ValueError('Приспособляемость доступна человеку.')
        skill=data.get('skill');replacement=data.get('replacement');note=text(data.get('note',''),300)
        if skill not in ATTRS or replacement not in ATTRS or skill==replacement or not note:
            raise ValueError('Укажите исходный и другой навык и объясните замену.')
        rt['adaptation']=dict(id=secrets.token_hex(8),skill=skill,replacement=replacement,note=note,status='requested')
    elif op in ('approveAdaptation','cancelAdaptation'):
        p=rt.get('adaptation')
        if not p or p['id']!=data.get('request'):raise ValueError('Заявка замены навыка изменилась.')
        if op=='approveAdaptation':
            if not gm:raise PermissionError('Применимость замены навыка подтверждает Мастер.')
            p['status']='approved'
        else:rt.pop('adaptation')
    elif op=='goblinSuccess':
        if kin!='goblin':raise ValueError('Эта способность доступна гоблину.')
        if data.get('darkConfirmed') is not True:raise ValueError('Подтвердите темноту или тусклое освещение: способность гоблина не действует при ярком свете.')
        r=rt.get('lastCheck');secret=room.get('gmChecks',{}).get(c['id']) if gm else None
        if secret and secret['id']==data.get('roll'):r=secret
        if not r or r['id']!=data.get('roll') or r['skill']!='stealth' or r.get('accepted'):
            raise ValueError('Нужна ещё не принятая проверка Скрытности.')
        item=next((i for i in room.get('items',[]) if i['id']==r['item']),None)
        if signature(c,item)!=r['signature']:raise ValueError('Герой или предмет изменились после проверки.')
        pair=next((p for p in room.get('opposedChecks',[]) if p['id']==r.get('opposed')),None)
        if r.get('opposed') and (not pair or pair.get('done')):raise ValueError('Встречная проверка уже завершена.')
        cost=data.get('wp')
        if type(cost)!=int or not 1<=cost<=rt.get('wp',0):raise ValueError('Укажите доступное число очков силы воли.')
        rt['wp']-=cost;r['kinSuccesses']=r.get('kinSuccesses',0)+cost;r['hits']=count(r);r['signature']=signature(c,item)
        if pair:
            side=next(p for p in (pair['attacker'],pair['defender']) if p['character']==c['id']);side['hits']=r['hits']
            if pair['attacker']['rolled'] and pair['defender']['rolled']:
                pair['net']=max(0,pair['attacker']['hits']-pair['defender']['hits'])
                pair['result']=f"Инициатор {pair['attacker']['hits']} − защитник {pair['defender']['hits']} = {pair['net']}."
        risk=None if r.get('pushed') or pair else dict(action='character',character=c['id'],roll=r['id'],attribute=r['attribute'])
        if pair and pair['attacker']['character']==c['id']:risk=dict(action='opposed',character=c['id'],roll=r['id'],opposed=pair['id'],attribute=r['attribute'])
        r['diceEvent']=publish(room,c['name'],'Крадучись · способность гоблина',pools(r),f'Сила воли −{cost}; дополнительных успехов {r["kinSuccesses"]}, итог {r["hits"]}.',r.get('private',False),risk=risk)
    elif op in ('markPrey','releasePrey'):
        if kin!='wolfkin':raise ValueError('Охотничье чутьё доступно волколаку.')
        if op=='releasePrey':rt.pop('prey',None);return
        target=next((x for x in room['characters'] if x['id']==data.get('target') and not x.get('hidden')),None)
        cost=data.get('wp')
        if not target or target['id']==c['id'] or data.get('confirmed') is not True:
            raise ValueError('Выберите видимую цель и подтвердите, что герой видит её или взял её след.')
        if rt.get('prey',{}).get('target')==target['id']:raise ValueError('Эта добыча уже выбрана. Сначала отпустите её, если хотите назначить заново.')
        if type(cost)!=int or not 1<=cost<=rt.get('wp',0):raise ValueError('Укажите доступное число очков силы воли.')
        rt['wp']-=cost;rt['prey']=dict(target=target['id'],bonus=cost,days=cost,markedDay=room['journey']['day'])
        room['log'].append(dict(name=c['name'],text=f'Охотничье чутьё: добыча — {target["name"]}; СВ −{cost}, след доступен {cost} дн.'))
    else:raise ValueError('Неизвестная способность.')


def adaptation(c,data,skill):
    token=data.get('adaptation')
    if not token:return skill
    p=c['runtime'].get('adaptation')
    if c['sheet']['kin']!='human' or not p or p['id']!=token or p['status']!='approved' or p['skill']!=skill:
        raise ValueError('Мастер должен подтвердить эту замену навыка.')
    if c['runtime'].get('wp',0)<1:raise ValueError('Для Приспособляемости нужна 1 СВ.')
    c['runtime']['wp']-=1;c['runtime'].pop('adaptation')
    return p['replacement']
