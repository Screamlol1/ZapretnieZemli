"""Owned equipment, persistent wear and load. PH pp. 37–38, 50, 88."""
PROFILES={'broadsword':'sword','longspear':'spear','battleaxe':'axe','shortbow':'bow','lightcrossbow':'crossbow','longbow':'longbow','greatsword':'greatsword','mace':'mace','halberd':'halberd','staff':'staff','dagger':'dagger'}
WEAPONS=set(PROFILES.values())
SLOTS=('weapon','armor','helmet','shield')

def bonus(item):return max(0,item.get('bonus',0)-item.get('wear',0))
def armor(item):return max(0,item.get('armor',0)-item.get('wear',0))
def artifact(item):
    return {'D8':8,'D10':10,'D12':12}.get(item.get('artifactDie','').upper(),0)

def slot(item):
    if item.get('combatProfile'):return 'weapon'
    if item['kind']=='shield':return 'shield'
    if item['kind']=='armor':return item.get('armorSlot','armor')
    return None

def owned(room,cid):return [i for i in room.get('items',[]) if i['location']==dict(kind='character',id=cid)]

def prepare(room,c):
    items=owned(room,c['id'])
    for i in items:
        i.setdefault('combatProfile',PROFILES.get(i.get('catalogId'),''))
        i.setdefault('armorSlot','helmet' if i.get('catalogId') in ('openhelm','closedhelm') else 'armor')
        i.setdefault('wear',0)
    if 'equipment' in c:return
    c['equipment']={};c['equipmentVersion']=1
    for i in items:
        k=slot(i)
        if k and k not in c['equipment'] and i['quantity']==1:c['equipment'][k]=i['id']
    weapon=next((i for i in items if i['id']==c['equipment'].get('weapon')),None)
    if weapon and weapon.get('grip')=='2Р':c['equipment'].pop('shield',None)
    # Carry old aggregate damage forward once, without recreating transferred items.
    equipped={k:next(i for i in items if i['id']==v) for k,v in c['equipment'].items()}
    w=equipped.get('weapon')
    if w and 'gearBonus' in c.get('runtime',{}):w['wear']=max(w['wear'],w['bonus']-c['runtime']['gearBonus'])
    pieces=[equipped[k] for k in ('armor','helmet') if k in equipped]
    loss=max(0,sum(armor(i) for i in pieces)-c.get('runtime',{}).get('armor',sum(armor(i) for i in pieces)))
    for i in pieces:
        take=min(armor(i),loss);i['wear']+=take;loss-=take

def clear_slots(room,item_id):
    for c in room['characters']:
        eq=c.get('equipment',{})
        if item_id in eq.values():
            c['equipment']={k:v for k,v in eq.items() if v!=item_id};c['equipmentVersion']=c.get('equipmentVersion',0)+1

def load(room,c):
    weight=sum(i['weight']*i['quantity'] for i in owned(room,c['id']))
    supplies=sum(v>0 for v in c.get('runtime',{}).get('resources',{}).values())
    coins=c.get('runtime',{}).get('coins',{})
    coin_weight=(sum(coins.values())//100)*.5
    capacity=2*c['sheet']['attrs']['str']+{1:2,2:5,3:10}.get(c['sheet'].get('talents',{}).get('packrat',0),0)
    return dict(items=weight,supplies=supplies,coins=coin_weight,total=weight+supplies+coin_weight,capacity=capacity,overloaded=weight+supplies+coin_weight>capacity)

def combat_gear(room,c):
    prepare(room,c)
    items={i['id']:i for i in owned(room,c['id'])}
    eq={k:items[v] for k,v in c['equipment'].items() if v in items}
    return dict(slots={k:{key:i[key] for key in ('id','name','bonus','damage','armor','wear','combatProfile','artifactDie','grip') if key in i} for k,i in eq.items()},load=load(room,c))

def sync_wear(room,battle):
    items={i['id']:i for i in room.get('items',[])}
    for u in battle.get('units',[]):
        for source in u.get('equipmentWear',[]):
            i=items.get(source['id'])
            if not i or i['location']!=dict(kind='character',id=u['id']):continue
            value=max(i.get('wear',0),source['maximum']-source['current'])
            if value!=i.get('wear',0):i['wear']=value;i['version']+=1
