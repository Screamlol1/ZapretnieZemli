"""Privacy and campaign guards for server-owned close-combat combinations."""
import copy

CARD_COMMANDS={'cardStart','cardChoose','cardDeclare','cardInsight','cardPeek','cardResolve','cardCancel'}
TACTICAL_COMMANDS={'tacticalReaction','tacticalOffhand','tacticalOffhandAttack','tacticalCharge','tacticalMount','tacticalMountedCharge','tacticalGuard','tacticalPlains','tacticalRecover','tacticalFinishCharge','tacticalPlainsSpeed','tacticalRide','closeAction'}

def actor(battle,cmd):
    return cmd.get('unit') if cmd.get('action') in CARD_COMMANDS|TACTICAL_COMMANDS else None

def guard(room,s,data):
    b=room.get('combat',{});x=b.get('cardExchange');reactions=b.get('tacticalReactions',[]);recovery=any(u.get('painRecovery') for u in b.get('units',[]));charge=b.get('chargeContinuation')
    command=data.get('command',{}) if isinstance(data.get('command',{}),dict) else {}
    if data.get('action')=='combatAction' and command.get('action') in ('cardEnable','cardCancel','tacticalMount') and s['role']!='gm':raise PermissionError('Этот параметр меняет Мастер.')
    if not x and not reactions and not recovery and not charge:return
    allowed=('chat','roll','freePush','freeAccept','audioDirector','characterPride','campaignCodex')
    if data.get('action') in allowed:return
    if data.get('action')!='combatAction':raise ValueError('Сначала завершите скрытую комбинацию или боевую реакцию.')
    name=command.get('action')
    if x and name not in CARD_COMMANDS|{'risk','tacticalRecover','tacticalReaction'}:raise ValueError('Сначала завершите скрытую комбинацию.')
    if recovery and name not in ('tacticalRecover','risk'):raise ValueError('Сначала распределите восстановление Стойкости к боли.')
    if charge and not reactions and name not in ('tacticalFinishCharge','tacticalRecover','risk'):raise ValueError('Сначала завершите удар натиска.')
    if reactions and name not in ('tacticalReaction','tacticalRecover','risk'):raise ValueError('Сначала завершите перехват копьём.')

def project(room,s):
    b=room.get('combat',{});x=b.get('cardExchange')
    own={c['id'] for c in room['characters'] if c['kind']=='pc' and c['owner']==s['owner'] and not c.get('hidden')}
    if s['role']!='gm':
        for u in b.get('units',[]):
            if u['id'] not in own:u.pop('offhandOptions',None)
    if not x:return
    choices=x.get('choices',{});x['ready']={who:who in choices for who in (x['attacker'],x['defender'])}
    # GM may run either side, but no player receives another participant's future card.
    x['choices']={who:[card if s['role']=='gm' or who in own or x['stage']!='choose' and i<=x['step'] else None for i,card in enumerate(cards)] for who,cards in choices.items()}
    insight=x.get('insight')
    if insight:insight['complete']=bool(insight.get('revealed'))
    if insight and s['role']!='gm' and insight['actor'] not in own:insight['revealed']=[]

def prepare(room,battle):
    from equipment_rules import owned,prepare as prepare_equipment,weapon_properties
    for u in battle['units']:
        c=next((c for c in room['characters'] if c['id']==u['id']),None)
        if not c or c['kind']=='monster':continue
        prepare_equipment(room,c)
        u['offhandOptions']=[dict(id=i['id'],name=i['name'],profile=i['combatProfile'],maximum=i['bonus'],gear=max(0,i['bonus']-i.get('wear',0)),damage=i['damage'],artifact={'D8':8,'D10':10,'D12':12}.get(i.get('artifactDie',''),0),light=i.get('weight',1)<=.5,heavy=i.get('weight',1)>=2,properties=weapon_properties(i),grip=i.get('grip','1Р')) for i in owned(room,c['id']) if i.get('combatProfile') and i['id']!=u.get('equipmentIds',{}).get('weapon') and i.get('quantity')==1 and '2' not in i.get('grip','') and i['combatProfile'] not in ('greatsword','halberd','staff','bow','longbow','crossbow','sling','throwingknife','throwingspear')]
