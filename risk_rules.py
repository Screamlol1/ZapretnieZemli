"""The shared one-push procedure; penalty dice keep the agreed table variant."""
def can_push(r):
    return any(v!=6 and (k in ('skillDice','penalty') or v!=1) for k in ('base','skillDice','gear','penalty') for v in r.get(k,[])) or any(a['value']<6 for a in r.get('artifacts',[])) or any(v<6 for v in (r.get('artifact',[]) if isinstance(r.get('artifact'),list) else []))

def push(r,die):
    r['held']={}
    for key in ('base','skillDice','gear','penalty'):
        values=r.get(key,[])
        r['held'][key]=[v==6 or key not in ('skillDice','penalty') and v==1 for v in values]
        r[key]=[v if r['held'][key][i] else die(6) for i,v in enumerate(values)]
    for a in r.get('artifacts',[]):
        a['held']=a['value']>=6
        if not a['held']:a['value']=die(a['sides'])
    r.update(pushed=True,damage=r['base'].count(1),wear=r['gear'].count(1))
    return r['damage'],r['wear']

def score(r):
    penalty=r.get('penalty',[]).count(6)
    positive=r['base'].count(6)+r['skillDice'].count(6)+r['gear'].count(6)+sum(max(0,a['value']//2-2) for a in r.get('artifacts',[]))+r.get('pride',{}).get('hits',0)+r.get('kinSuccesses',0)
    r['netHits']=positive-penalty;r['hits']=max(0,r['netHits'])
    return positive,penalty

def can_push_character(c,r):
    """A dwarf pays per additional push; kept 1s hurt on every push (PHB62)."""
    from injuries import blocked,current
    repeat=c['kind']=='pc' and c['sheet'].get('kin')=='dwarf' and c['runtime'].get('wp',0)>0
    return bool(not r.get('pride') and not c['runtime'].get('prideRequest') and not blocked(c) and min(current(c).values())>0 and can_push(r) and (not r.get('pushed') or repeat))

def repeat_push(c,r,data):
    if not can_push_character(c,r):raise ValueError('Нет доступного риска: проверьте кости, состояние и силу воли.')
    if r.get('pushed'):
        if data.get('kinRepeat') is not True or type(data.get('kinAttempt'))!=int or data['kinAttempt']!=r.get('kinPushes',0):raise ValueError('Повторный риск изменился. Проверьте новые кости перед решением.')
        c['runtime']['wp']-=1;r['kinPushes']=r.get('kinPushes',0)+1
