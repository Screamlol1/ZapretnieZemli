"""Expose authoritative availability, never signatures or private checks of others."""
from skill_checks import signature
from risk_rules import can_push
from injuries import blocked
from pride import available


def project(room):
    for c in room['characters']:
        if not c.get('sheet') or c['kind']=='monster':continue
        for r in (c.get('runtime',{}).get('lastCheck'),room.get('gmChecks',{}).get(c['id'])):
            if not r:continue
            item=next((i for i in room.get('items',[]) if i['id']==r.get('item') and i.get('location')==dict(kind='character',id=c['id'])),None)
            battle=room.get('combat',{});travel=room['journey']
            locked=(battle.get('phase') in ('setup','combat') and any(u['id']==c['id'] for u in battle.get('units',[])) or
                    travel['phase']=='resolving' and c['id'] in travel['party'] or room.get('treatment') or room.get('coldCheck') or room.get('waterCheck') or
                    any(i.get('repair',{}).get('status')=='rolled' and i['repair']['character']==c['id'] for i in room.get('items',[])))
            # Older saves may retain unaccepted rolls after the pair was finished
            # or removed from its bounded history. They are no longer actionable.
            if r.get('opposed'):
                pair=next((p for p in room.get('opposedChecks',[]) if p['id']==r['opposed']),None)
                locked=locked or not pair or pair.get('done')
            r['current']=not locked and not r.get('accepted') and (not r.get('item') or bool(item)) and r.get('signature')==signature(c,item)
            repeat=c['kind']=='pc' and c['sheet']['kin']=='dwarf' and c['runtime'].get('wp',0)>0
            r['pushAvailable']=bool(r['current'] and not r.get('pride') and not c['runtime'].get('prideRequest') and not blocked(c) and min(c['runtime']['current'].values())>0 and can_push(r) and (not r.get('pushed') or repeat))
            r['prideAvailable']=bool(r['current'] and not r.get('opposed') and not r.get('pride') and r['hits']==0 and available(c,travel['session']))
        request=c.get('runtime',{}).get('prideRequest')
        if request:
            r=room.get('gmChecks',{}).get(c['id']) if request.get('private') else c['runtime'].get('lastCheck')
            request['current']=bool(r and r.get('prideAvailable') and r['id']==request['roll'] and r['diceEvent']==request['event'] and request['session']==room['journey']['session'])
    import check_abilities
    check_abilities.project(room)
