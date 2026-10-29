"""Keep visible, compatible line junctions welded during a manual transform."""
import math


def family(path):
    return 'barrier' if path['style'] in ('wall','palisade') else path['style']


def private(m, path):
    hidden={f['id'] for f in m['features'] if f.get('secret')}
    return bool(path.get('secret') or hidden.intersection(path.get('refs',[])))


def parameter(p, a, b):
    dx,dy=b[0]-a[0],b[1]-a[1];length=dx*dx+dy*dy
    if length<1e-12:return 0 if math.dist(p,a)<.002 else None
    t=((p[0]-a[0])*dx+(p[1]-a[1])*dy)/length
    if -.000001<=t<=1.000001 and math.dist(p,[a[0]+t*dx,a[1]+t*dy])<.002:
        return max(0,min(1,t))
    return None


def crossings(a,b,c,d):
    dx,dy=b[0]-a[0],b[1]-a[1];ex,ey=d[0]-c[0],d[1]-c[1]
    det=dx*ey-dy*ex
    if abs(det)>1e-9:
        t=((c[0]-a[0])*ey-(c[1]-a[1])*ex)/det
        u=((c[0]-a[0])*dy-(c[1]-a[1])*dx)/det
        if -.000001<=t<=1.000001 and -.000001<=u<=1.000001:
            return [(max(0,min(1,t)),max(0,min(1,u)))]
        return []
    result=[]
    for p in (a,b,c,d):
        t,u=parameter(p,a,b),parameter(p,c,d)
        if t is not None and u is not None:result.append((t,u))
    return result


def subdivide(points, cuts):
    result=[]
    for i,(a,b) in enumerate(zip(points,points[1:])):
        for t in sorted({0,1,*cuts.get(i,[])}):
            p=[a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t]
            if not result or math.dist(result[-1],p)>.001:result.append(p)
    if len(result)>500:raise ValueError('Слишком много стыков на одной линии. Разделите её на участки.')
    return result


def transform_line(m, target, transform, validate):
    cuts={};neighbors=[];connections=[];comparisons=0
    visible=private(m,target)
    compatible=[p for p in m['paths'] if not p.get('refs') and family(p)==family(target) and private(m,p)==visible]
    def intersections(a,b,c,d):
        nonlocal comparisons
        comparisons+=1
        if comparisons>500_000:raise ValueError('Слишком сложная сеть стыков. Разделите план на несколько локаций.')
        return crossings(a,b,c,d)
    for other in compatible:
        # A secret branch must not change the publicly visible geometry.
        # Room-linked passages keep their own attachment rules.
        if other is target:continue
        other_cuts={}
        for i,(a,b) in enumerate(zip(target['points'],target['points'][1:])):
            for j,(c,d) in enumerate(zip(other['points'],other['points'][1:])):
                for t,u in intersections(a,b,c,d):
                    cuts.setdefault(i,[]).append(t);other_cuts.setdefault(j,[]).append(u)
                    connections.append([a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t])
        if other_cuts:neighbors.append((other,other_cuts))
    moved=[validate(m,transform(p)) for p in subdivide(target['points'],cuts)]
    updates=[]
    for other,other_cuts in neighbors:
        # Keep the neighbor's other junctions stationary while its attached end
        # follows the selected line. Otherwise a second T joint would detach.
        for third in compatible:
            if third is other or third is target:continue
            for i,(a,b) in enumerate(zip(other['points'],other['points'][1:])):
                for c,d in zip(third['points'],third['points'][1:]):
                    for t,u in intersections(a,b,c,d):other_cuts.setdefault(i,[]).append(t)
        pts=subdivide(other['points'],other_cuts)
        new=[validate(m,transform(p)) if any(math.dist(p,c)<.002 for c in connections) else p for p in pts]
        if any(math.dist(a,b)<.001 for a,b in zip(new,new[1:])):
            raise ValueError('Перемещение схлопывает соседний участок. Выберите другое положение.')
        updates.append((other,new))
    target['points']=moved
    for other,pts in updates:
        other['points']=pts
        other.pop('rotation',None);other.pop('rotationCenter',None)
