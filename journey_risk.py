"""Pause quarter resolution at each skill check, before applying its outcome."""
from contextvars import ContextVar
from copy import deepcopy
import secrets
from risk_rules import can_push,push,score
from dice_events import publish,pools
from dice_pools import result_text

context=ContextVar('journey_risk',default=None)
class Pause(Exception):pass

def draw(n,sides,random):
    ctx=context.get()
    if ctx is None:return random(n,sides)
    values=[]
    for _ in range(n):
        i=ctx['cursor'];ctx['cursor']+=1;tape=ctx['replay']['draws']
        if i==len(tape):tape.append([sides,random(1,sides)[0]])
        if tape[i][0]!=sides:raise ValueError('Состав проверки путешествия изменился.')
        values.append(tape[i][1])
    return values

def check(room,c,r,item):
    from injuries import signature
    from skill_checks import ATTRS
    from risk_rules import can_push_character,repeat_push
    ctx=context.get()
    if ctx is None:return
    i=ctx['check'];ctx['check']+=1;choices=ctx['replay']['choices']
    if i==len(choices):choices.append(dict(pushes=0,done=False))
    choice=choices[i]
    if isinstance(choice,bool):choice=dict(pushes=int(choice),done=True);choices[i]=choice
    attribute=ATTRS[r['skill']];r.update(attribute=attribute,pushed=False)
    from campaign_rules import dice
    for attempt in range(choice.get('pushes',0)):
        repeat_push(c,r,dict(kinRepeat=attempt>0,kinAttempt=max(0,attempt-1)))
        damage,wear=push(r,lambda n:dice(1,n)[0]);c['runtime']['current'][attribute]=max(0,c['runtime']['current'][attribute]-damage)
        if c['kind']=='pc':c['runtime']['wp']=min(10,c['runtime'].get('wp',0)+damage)
        if item and wear:item['wear']=min(item['bonus'],item.get('wear',0)+wear);item['version']+=1
        result=result_text(*score(r))+f' Риск: {attribute} −{damage}, износ {wear}.'
        if wear and not item:result+=' Снаряжение задано вручную: Мастер отмечает его износ.'
        r['diceEvent']=publish(room,c['name'],'Пойти на риск · путешествие',pools(r),result,r.get('originalSkill',r['skill'])=='scout' or bool(c.get('hidden')))
    if choice.get('pride'):r['pride']=deepcopy(choice['pride']);score(r)
    if not choice.get('done'):
        rid=choice.setdefault('id',secrets.token_hex(12));r['id']=rid;r['pushAvailable']=can_push_character(c,r)
        risk=dict(id=rid,actor=c['id'],private=r.get('originalSkill',r['skill'])=='scout' or bool(c.get('hidden')),attribute=attribute,roll=r,item=item['id'] if item else '',signature=signature(c,item),diceEvent=r['diceEvent'])
        room['journeyRisk']=risk
        room['diceRolls'][-1]['risk']=dict(action='journey',roll=rid,character=c['id'],attribute=attribute)
        raise Pause()

def record_pride(room,value,hits):
    replay=room['journeyResolution'];replay.setdefault('abilityStates',{})
    replay['choices'][-1]['pride']=dict(value=value,hits=hits)

def resolve(room,data=None):
    from campaign_rules import advance
    replay=room.get('journeyResolution')
    if replay is None:
        replay=dict(before={k:deepcopy(v) for k,v in room.items() if k in ('id','worldLayout','maps','_worldBase','characters','items','journey','strongholds','vessels','hunts','expeditionCheck','log','diceRolls')},draws=[],choices=[],events=0,logs=0)
    elif data is not None:
        choice=replay['choices'][-1]
        if data['push']:choice['pushes']=choice.get('pushes',0)+1
        else:choice['done']=True
    trial=deepcopy(replay['before']);baseline_events={e['id'] for e in trial.get('diceRolls',[])};baseline_logs=len(trial['log'])
    token=context.set(dict(replay=replay,cursor=0,check=0))
    try:advance(trial,dict(path=trial['journey']['route']),defer_clock=True)
    except Pause:pass
    finally:context.reset(token)
    events=[e for e in trial.get('diceRolls',[]) if e['id'] not in baseline_events];logs=trial['log'][baseline_logs:]
    room['diceRolls']=(room.get('diceRolls',[])+events[replay['events']:])[-200:]
    room['log']+=logs[replay['logs']:]
    replay['events']=len(events);replay['logs']=len(logs)
    revision=room['journey']['revision']
    for key in ('characters','items','maps','journey','strongholds','vessels','hunts'):
        if key in trial:room[key]=trial[key]
    if trial.get('expeditionCheck'):room['expeditionCheck']=trial['expeditionCheck']
    for c in room['characters']:
        saved=replay.get('abilityStates',{}).get(c['id'])
        if saved:c['runtime']['pride']=deepcopy(saved['pride']);c['sheet']['pride']=saved['text'];c['runtime'].pop('prideRequest',None)
    room['journey'].update(phase='resolving',completed={},blocker='',revision=revision)
    if 'journeyRisk' in trial:
        room['journeyRisk']=trial['journeyRisk'];room['journeyResolution']=replay
        from injuries import signature
        pending=room['journeyRisk'];actor=next(c for c in room['characters'] if c['id']==pending['actor']);item=next((i for i in room.get('items',[]) if i['id']==pending.get('item')),None)
        pending['signature']=signature(actor,item)
    else:
        room.pop('journeyRisk',None);room.pop('journeyResolution',None)

def apply(room,s,data):
    risk=room.get('journeyRisk')
    if not risk or data.get('roll')!=risk['id'] or type(data.get('push'))!=bool:raise ValueError('Проверка путешествия уже завершена.')
    c=next(c for c in room['characters'] if c['id']==risk['actor'])
    if s['role']!='gm' and (risk['private'] or c['kind']!='pc' or c['owner']!=s['owner']):raise PermissionError('Решение принимает владелец героя или Мастер.')
    if not risk.get('roll'):
        # Saved pre-adapter campaigns have boolean choices for finished checks,
        # and no choice entry yet for the currently displayed check.
        room['journeyResolution']['choices'].append(dict(id=risk['id'],pushes=int(data['push']),done=not data['push']))
        resolve(room);room['journey']['revision']+=1;return
    if data['push']:
        from risk_rules import repeat_push
        if data.get('diceEvent') and data['diceEvent']!=risk['diceEvent']:raise ValueError('Кости изменились. Откройте текущий бросок.')
        repeat_push(deepcopy(c),deepcopy(risk['roll']),data)
    resolve(room,data);room['journey']['revision']+=1
