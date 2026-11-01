"""Explain stored outcomes without rolling, applying, or replaying an action."""
import copy
import json


def snapshot(room):
    characters={c['id']:dict(name=c['name'],hidden=c.get('hidden',False),values={**c.get('runtime',{}).get('current',{}),'wp':c.get('runtime',{}).get('wp',0)}) for c in room.get('characters',[])}
    items={i['id']:dict(name=i['name'],values={k:i.get(k,0) for k in ('wear','quantity','bonus')}) for i in room.get('items',[])}
    return dict(characters=characters,items=items,events={e['id']:json.dumps({k:v for k,v in e.items() if k!='calculation'},sort_keys=True,ensure_ascii=False) for e in room.get('diceRolls',[])})


def dice_calculation(event):
    rows=[];positive=negative=0;ordinary=all(g['kind'] not in ('table','magic') for g in event['groups'])
    for g in event['groups']:
        hits=sum(max(0,v//2-2) if g['kind']=='artifact' else int(v==6) for v in g['values']) if ordinary else None
        if hits is not None:
            if g.get('negative'):negative+=hits
            else:positive+=hits
        rows.append(dict(label=g['label'],sides=g['sides'],count=len(g['values']),values=g['values'],successes=hits,negative=bool(g.get('negative')),held=sum(bool(v) for v in g.get('held',[]))))
    return dict(rows=rows,positive=positive,negative=negative,net=max(0,positive-negative) if ordinary else None,effects=[])


def record(room,before,data):
    events=room.get('diceRolls',[])
    candidates=[e for e in events if before['events'].get(e['id'])!=json.dumps({k:v for k,v in e.items() if k!='calculation'},sort_keys=True,ensure_ascii=False)]
    if not candidates and data.get('roll'):candidates=[e for e in events if e.get('risk',{}).get('roll')==data['roll']][-1:]
    if not candidates:return
    for e in candidates:
        previous=e.get('calculation',{}).get('effects',[])
        e['calculation']=dice_calculation(e);e['calculation']['effects']=previous
        if e.get('sources'):e['calculation']['sources']=copy.deepcopy(e['sources'])
        r=None
        for c in room.get('characters',[]):
            for possible in (c.get('runtime',{}).get('lastCheck'),room.get('gmChecks',{}).get(c['id'])):
                if possible and possible.get('id')==e.get('risk',{}).get('roll'):r=possible
        if r and isinstance(r.get('formula'),dict):
            e['calculation']['sources']=[dict(label=name,value=r['formula'][key]) for key,name in [('base','Текущая характеристика'),('skill','Уровень навыка'),('modifier','Модификатор обстоятельств'),('gear','Бонус выбранного снаряжения')] if type(r['formula'].get(key))==int]
            if r.get('injuryModifier'):e['calculation']['sources'].append(dict(label='Последствия травм',value=r['injuryModifier']))
    after=snapshot(room);changes=[]
    labels=dict(str='Телосложение',agi='Ловкость',wit='Разум',emp='Эмпатия',wp='Сила воли',wear='Износ',quantity='Количество',bonus='Максимальный бонус')
    for bucket,kind in [('characters','character'),('items','item')]:
        for identifier,a in after[bucket].items():
            old=before[bucket].get(identifier)
            if not old:continue
            for key,value in a['values'].items():
                previous=old['values'].get(key)
                if type(value) in (int,float) and type(previous) in (int,float) and value!=previous:
                    changes.append(dict(kind=kind,id=identifier,name=a['name'],label=labels[key],delta=value-previous))
    if changes:candidates[-1]['calculation']['effects']=(candidates[-1]['calculation']['effects']+changes)[-40:]


def project(room,s):
    if s['role']=='gm':return
    characters={c['id'] for c in room.get('characters',[])};items={i['id'] for i in room.get('items',[])}
    for event in room.get('diceRolls',[]):
        trace=event.get('calculation')
        if trace:trace['effects']=[e for e in trace['effects'] if e['id'] in (characters if e['kind']=='character' else items)]
