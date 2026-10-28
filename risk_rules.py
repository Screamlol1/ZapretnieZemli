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
    positive=r['base'].count(6)+r['skillDice'].count(6)+r['gear'].count(6)+sum(max(0,a['value']//2-2) for a in r.get('artifacts',[]))
    r['netHits']=positive-penalty;r['hits']=max(0,r['netHits'])
    return positive,penalty
