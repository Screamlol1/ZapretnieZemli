"""Bridge a GM-approved Pride D12 into the authoritative combat replay.

Only the Pride module calls apply_pride. A client combat command cannot provide
the die. Replay preserves all previous dice and applies no damage twice.
"""
import copy
import json
from node_runtime import run_node
from pathlib import Path
from dice_events import publish
from equipment_rules import sync_wear


def context(room,c,roll,gm=False):
    p=room.get('combat',{}).get('pendingRisk')
    if not p or p.get('id')!=roll or p.get('actor')!=c['id'] or not p.get('prideEligible') or not p.get('roll'):
        raise ValueError('Для гордости нужна незавершённая неудачная боевая проверка героя.')
    if p.get('private') and not gm:raise PermissionError('Скрытую проверку разрешает Мастер.')
    event=next((e for e in reversed(room.get('diceRolls',[])) if e.get('risk',{}).get('roll')==roll),None)
    if not event:raise ValueError('Боевой бросок уже недоступен.')
    p['roll']['diceEvent']=event['id']
    return dict(kind='combat',p=p,r=p['roll'],item=None,private=p.get('private',False),failed=p.get('failed',False),event=event['id'])


def apply_pride(room,c,ctx,value,hits):
    p=ctx['p'];battle=room['combat'];private=ctx['private']
    if p is not battle.get('pendingRisk') or p.get('step') is None:raise ValueError('Боевой результат изменился.')
    clone=copy.deepcopy(battle);replay=clone['pendingRisk']['replay']
    replay.setdefault('prides',{})[str(p['step'])]=dict(value=value,hits=hits)
    command=dict(action='risk',roll=p['id'],push=False,interactive=True)
    result=run_node([str(Path(__file__).with_name('combat-engine.mjs'))],input=json.dumps(dict(battle=clone,command=command)),text=True,capture_output=True,encoding='utf-8',timeout=10)
    if result.returncode:raise ValueError(result.stderr or 'Не удалось применить гордость в бою.')
    updated=json.loads(result.stdout);room['combat']=updated
    if updated.get('pendingRisk'):updated['pendingRisk']['private']=private
    logs=updated.pop('commandLog',[]);updated['publicLog']=(battle.get('publicLog',battle['log'])+([] if private else logs))[-300:]
    for event in updated.pop('diceEvents',[]):publish(room,event['name'],event['label'],event['groups'],event['result'],private,risk=event.get('risk'))
    sync_wear(room,updated)
    for character in room['characters']:
        u=next((u for u in updated['units'] if u['id']==character['id']),None)
        if u:character.setdefault('runtime',{}).update(current=dict(str=u['str'],agi=u['agi'],wit=u['wits'],emp=u['emp']),wp=u['wp'],gearBonus=u['gear'],armor=u['armor'])
    room['combatRevision']=room.get('combatRevision',0)+1
    # Penalty successes still cancel the D12 successes before the zero clamp.
    r=ctx['r'];positive=r['base'].count(6)+r['gear'].count(6)+r['skillDice'].count(6)*(-1 if r.get('negative') else 1)+sum(max(0,a['value']//2-2) for a in r.get('artifacts',[]) if a['value']>=6)+hits
    r['hits']=max(0,positive-r.get('penalty',[]).count(6));r['pride']=dict(value=value,hits=hits)
    return r['hits']<p.get('requiredSuccesses',1)
