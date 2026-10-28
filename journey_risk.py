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
    ctx=context.get()
    if ctx is None or not can_push(r):return
    i=ctx['check'];ctx['check']+=1;choices=ctx['replay']['choices']
    attribute={'survive':'wit','scout':'wit','endure':'str','craft':'str','shoot':'agi'}[r['skill']]
    if i==len(choices):
        risk=dict(id=secrets.token_hex(12),actor=c['id'],private=r['skill']=='scout' or bool(c.get('hidden')),attribute=attribute)
        room['journeyRisk']=risk
        room['diceRolls'][-1]['risk']=dict(action='journey',roll=risk['id'],character=c['id'],attribute=attribute)
        raise Pause()
    if choices[i]:
        from campaign_rules import dice
        damage,wear=push(r,lambda n:dice(1,n)[0]);c['runtime']['current'][attribute]=max(0,c['runtime']['current'][attribute]-damage)
        if c['kind']=='pc':c['runtime']['wp']=min(10,c['runtime'].get('wp',0)+damage)
        if item and wear:item['wear']=min(item['bonus'],item.get('wear',0)+wear);item['version']+=1
        result=result_text(*score(r))+f' Риск: {attribute} −{damage}, износ {wear}.'
        if wear and not item:result+=' Снаряжение задано вручную: Мастер отмечает его износ.'
        r['diceEvent']=publish(room,c['name'],'Пойти на риск · путешествие',pools(r),result,r['skill']=='scout' or bool(c.get('hidden')))

def resolve(room,data=None):
    from campaign_rules import advance
    replay=room.get('journeyResolution')
    if replay is None:
        replay=dict(before={k:deepcopy(v) for k,v in room.items() if k in ('id','worldLayout','maps','_worldBase','characters','items','journey','strongholds','log','diceRolls')},draws=[],choices=[],events=0,logs=0)
    else:replay['choices'].append(data['push'])
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
    for key in ('characters','items','maps','journey'):room[key]=trial.get(key,[])
    room['journey'].update(phase='resolving',completed={},blocker='',revision=revision)
    if 'journeyRisk' in trial:
        room['journeyRisk']=trial['journeyRisk'];room['journeyResolution']=replay
    else:
        room.pop('journeyRisk',None);room.pop('journeyResolution',None)

def apply(room,s,data):
    risk=room.get('journeyRisk')
    if not risk or data.get('roll')!=risk['id'] or type(data.get('push'))!=bool:raise ValueError('Проверка путешествия уже завершена.')
    c=next(c for c in room['characters'] if c['id']==risk['actor'])
    if s['role']!='gm' and (risk['private'] or c['kind']!='pc' or c['owner']!=s['owner']):raise PermissionError('Решение принимает владелец героя или Мастер.')
    resolve(room,data);room['journey']['revision']+=1
