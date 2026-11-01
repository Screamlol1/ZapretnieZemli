"""Adapters for abilities that modify a pending character check, never a free roll."""
from equipment_rules import owned
from risk_rules import score

def close_request(c,roll):
    if c.get('runtime',{}).get('prideRequest',{}).get('roll')==roll:c['runtime'].pop('prideRequest',None)

def context(room,c,roll,gm=False):
    from skill_checks import signature
    rt=c['runtime'];ctx=None
    for key,actor,itemkey in (('coldCheck','character','item'),('waterCheck','character','item'),('afflictionCheck','character','item'),('treatment','healer','tool'),('expeditionCheck','actor','item')):
        p=room.get(key)
        if p and p.get(actor)==c['id'] and p.get('roll',{}).get('id')==roll:
            ctx=dict(kind=key,p=p,r=p['roll'],itemId=p.get(itemkey),private=p.get('private',False),signature=p.get('signature'));break
    if ctx is None:
        for item in room.get('items',[]):
            p=item.get('repair',{})
            if p.get('status')=='rolled' and p.get('character')==c['id'] and p['roll']['id']==roll:
                ctx=dict(kind='repair',p=p,r=p['roll'],target=item,itemId=p.get('tool'),private=p.get('private',False),signature=p.get('signature'));break
    if ctx is None and room.get('journeyRisk',{}).get('id')==roll:
        p=room['journeyRisk']
        if p.get('actor')==c['id'] and p.get('roll'):ctx=dict(kind='journeyRisk',p=p,r=p['roll'],itemId=p.get('item'),private=p['private'],signature=p.get('signature'))
    if ctx is None and room.get('combat',{}).get('pendingRisk',{}).get('id')==roll:
        try:
            import combat_check_abilities
            ctx=combat_check_abilities.context(room,c,roll,gm)
            if ctx:ctx['kind']='combat'
        except ImportError:pass
    if ctx is None:
        r=rt.get('lastCheck');secret=room.get('gmChecks',{}).get(c['id']) if gm else None
        if secret and secret['id']==roll:r=secret
        if r and r['id']==roll and not r.get('accepted'):ctx=dict(kind='ordinary',p=r,r=r,itemId=r.get('item'),private=r.get('private',False),signature=r.get('signature'))
    if not ctx or ctx.get('private') and not gm:raise ValueError('Нужна доступная незавершённая проверка персонажа.')
    if ctx['kind']=='ordinary':
        b=room.get('combat',{});t=room.get('journey',{})
        if b.get('phase') in ('setup','combat') and any(u['id']==c['id'] for u in b.get('units',[])) or t.get('phase')=='resolving' and c['id'] in t.get('party',[]) or any(room.get(k) for k in ('coldCheck','waterCheck','afflictionCheck','treatment','expeditionCheck')):raise ValueError('Сначала завершите текущую специальную проверку.')
    item=next((i for i in owned(room,c['id']) if i['id']==ctx.get('itemId')),None);ctx['item']=item
    if ctx.get('signature') is not None and (ctx['signature']!=signature(c,item) or ctx.get('itemId') and not item):raise ValueError('Герой или предмет изменились после броска. Эта проверка устарела.')
    r=ctx['r'];ctx['event']=ctx['p'].get('diceEvent') or r.get('diceEvent')
    ctx['failed']=ctx.get('failed',r['hits']==0)
    if ctx['kind']=='afflictionCheck':ctx['failed']=r['hits']<ctx['p']['enemyHits']
    if r.get('opposed'):
        pair=next((p for p in room.get('opposedChecks',[]) if p['id']==r['opposed']),None)
        if not pair or pair.get('done') or not all(pair[k]['rolled'] for k in ('attacker','defender')):raise ValueError('Сначала нужны оба броска встречной проверки.')
        attacker=pair['attacker']['character']==c['id'];ctx['pair']=pair
        ctx['failed']=r['hits']<=pair['defender']['hits'] if attacker else r['hits']<pair['attacker']['hits']
    if ctx['kind']=='combat':ctx['failed']=ctx.get('failed',r['hits']==0)
    return ctx

def after_pride(room,c,ctx,value,hits):
    from dice_events import publish,pools
    from skill_checks import signature,count
    r=ctx['r'];r['pride']=dict(value=value,hits=hits);r['pushAvailable']=False
    if ctx['kind']=='combat':
        import combat_check_abilities
        return combat_check_abilities.apply_pride(room,c,ctx,value,hits)
    if ctx['kind']=='ordinary':r['hits']=count(r)
    else:score(r)
    if ctx.get('pair'):
        pair=ctx['pair'];side=next(pair[k] for k in ('attacker','defender') if pair[k]['character']==c['id']);side['hits']=r['hits']
        pair['net']=max(0,pair['attacker']['hits']-pair['defender']['hits']);pair['result']=f"Инициатор {pair['attacker']['hits']} − защитник {pair['defender']['hits']} = {pair['net']}."
        ctx['failed']=r['hits']<=pair['defender']['hits'] if side is pair['attacker'] else r['hits']<pair['attacker']['hits']
    else:ctx['failed']=r['hits']<ctx['p']['enemyHits'] if ctx['kind']=='afflictionCheck' else r['hits']==0
    if ctx['kind']=='journeyRisk':
        import journey_risk
        journey_risk.record_pride(room,value,hits)
    return ctx['failed']

def refresh(room,c,ctx,outcome):
    from dice_events import publish,pools
    from skill_checks import signature
    r=ctx['r'];p=ctx['p'];kind=ctx['kind']
    if kind=='combat':return
    p['signature']=signature(c,ctx['item'])
    if kind=='ordinary':r['signature']=p['signature']
    if kind=='ordinary':
        if not ctx.get('pair'):r['accepted']=True
        risk=dict(action='opposed',character=c['id'],roll=r['id'],opposed=ctx['pair']['id'],attribute=r['attribute']) if ctx.get('pair') and ctx['pair']['attacker']['character']==c['id'] else None
    else:
        names={'coldCheck':'cold','waterCheck':'water','afflictionCheck':'affliction','treatment':'treatment','repair':'repair','journeyRisk':'journey','expeditionCheck':'expedition'}
        risk=dict(action=names[kind],character=c['id'],roll=p.get('id') or r['id'],attribute=r.get('attribute','str'))
        if kind=='repair':risk['item']=ctx['target']['id']
    event=publish(room,c['name'],'Гордость · D12',pools(r),outcome,ctx.get('private',False),risk=risk)
    r['diceEvent']=event;p['diceEvent']=event
    if kind=='journeyRisk':
        # Replay starts from the original snapshot: carry the spent Pride too.
        room['journeyResolution']['abilityStates'][c['id']]=dict(pride=c['runtime']['pride'].copy(),text=c['sheet']['pride'])

def project(room):
    from pride import available
    for c in room['characters']:
        if c['kind']!='pc':continue
        ids=[]
        for key in ('coldCheck','waterCheck','afflictionCheck','treatment','expeditionCheck','journeyRisk'):
            p=room.get(key) or {};r=p.get('roll') or {};ids.append(p.get('id') or r.get('id'))
        ids += [i['repair']['roll']['id'] for i in room.get('items',[]) if i.get('repair',{}).get('status')=='rolled']
        ids += [room.get('combat',{}).get('pendingRisk',{}).get('id')]
        ids += [r['id'] for r in (c['runtime'].get('lastCheck'),room.get('gmChecks',{}).get(c['id'])) if r and r.get('opposed') and not r.get('accepted')]
        for rid in filter(None,ids):
            try:ctx=context(room,c,rid,True)
            except (ValueError,PermissionError):continue
            r=ctx['r'];r['prideAvailable']=bool(not r.get('pride') and ctx['failed'] and available(c,room['journey']['session']))
        request=c['runtime'].get('prideRequest')
        if request:
            try:ctx=context(room,c,request['roll'],True);request['current']=bool(not ctx['r'].get('pride') and ctx['failed'] and available(c,room['journey']['session']) and ctx['event']==request['event'] and request['session']==room['journey']['session'])
            except (ValueError,PermissionError):request['current']=False
