"""Server-side, per-observer visibility. Clients receive only visible geometry."""
import copy
import math
from functools import lru_cache
import json

from exploration import contains, visible_ids
from location_geometry import crossings


def within_budget(m):
    vertices=sum(len(f.get('points') or [0,0,0,0]) for f in m['features'] if f['style'] in ('room','cave') or f.get('blocksSight'))
    segments=sum(max(0,len(p['points'])-1) for p in m['paths'])
    length=sum(math.dist(a,b) for p in m['paths'] for a,b in zip(p['points'],p['points'][1:]))
    radius=m.get('vision',{}).get('range',30)*m['cellSize']/m['metersPerCell']
    cells=math.ceil(min(m['width'],radius*2)/20)*math.ceil(min(m['height'],radius*2)/20)
    edges=sum(len(f.get('points') or [0,0,0,0]) for f in m['features'])
    lights=1+len(m.get('exploration',{}).get('lights',[])) if m.get('exploration',{}).get('dark') else 1
    # Bound the candidate-ray work as well as file size. Large, heavily lit plans
    # must be split into floors rather than monopolizing the campaign server.
    work=(vertices+segments+1)*(cells*4+length/8+segments+edges)*lights
    return vertices+segments<=1500 and length<=40000 and work<=2_000_000


def polygon(f):
    pts=f.get('points') if f.get('shape')=='polygon' else [[f['x'],f['y']],[f['x']+f['w'],f['y']],[f['x']+f['w'],f['y']+f['h']],[f['x'],f['y']+f['h']]]
    angle=math.radians(f.get('rotation',0));cx=f['x']+f['w']/2;cy=f['y']+f['h']/2
    return [[cx+(x-cx)*math.cos(angle)-(y-cy)*math.sin(angle),cy+(x-cx)*math.sin(angle)+(y-cy)*math.cos(angle)] for x,y in pts]


def blockers(m):
    result=[];doors=m.get('exploration',{}).get('doors',{});unit=m['cellSize']/m['metersPerCell']
    passages=[p for p in m['paths'] if p['style']=='passage']
    for p in m['paths']:
        if p['style'] in ('wall','palisade') and doors.get(p.get('id'))!='open':result.extend(zip(p['points'],p['points'][1:]))
        if p['style']=='passage' and doors.get(p.get('id')) in ('closed','locked'):
            a,b=max(zip(p['points'],p['points'][1:]),key=lambda pair:math.dist(*pair));length=math.dist(a,b)
            if length:
                x,y=(a[0]+b[0])/2,(a[1]+b[1])/2;dx,dy=-(b[1]-a[1])/length*unit*1.6,(b[0]-a[0])/length*unit*1.6
                result.append(([x-dx,y-dy],[x+dx,y+dy]))
    for f in m['features']:
        if f['style'] not in ('room','cave') and not f.get('blocksSight'):continue
        pts=polygon(f)
        for a,b in zip(pts,pts[1:]+pts[:1]):
            gaps=[];length=math.dist(a,b)
            if not length:continue
            for p in passages:
                if f['id'] not in p.get('refs',[]):continue
                for c,d in zip(p['points'],p['points'][1:]):
                    for t,_ in crossings(a,b,c,d):gaps.append((max(0,t-unit*1.6/length),min(1,t+unit*1.6/length)))
            start=0
            for low,high in sorted(gaps)+[(1,1)]:
                if low>start:result.append(([a[0]+(b[0]-a[0])*start,a[1]+(b[1]-a[1])*start],[a[0]+(b[0]-a[0])*low,a[1]+(b[1]-a[1])*low]))
                start=max(start,high)
    return result


def clear_line(a,b,segments):
    if math.dist(a,b)<.01:return True
    # Endpoint contact is allowed: a wall's visible face can be displayed.
    for c,d in segments:
        if max(a[0],b[0])<min(c[0],d[0]) or min(a[0],b[0])>max(c[0],d[0]) or max(a[1],b[1])<min(c[1],d[1]) or min(a[1],b[1])>max(c[1],d[1]):continue
        if any(.00001<t<.99999 for t,_ in crossings(a,b,c,d)):return False
    return True


class Sight:
    def __init__(self,m,origin):
        self.m=m;self.origin=origin;self.unit=m['cellSize']/m['metersPerCell'];self.radius=m.get('vision',{}).get('range',30)*self.unit
        self.segments=blockers(m);e=m.get('exploration',{});self.dark=bool(e.get('dark'))
        self.lights=[l for l in e.get('lights',[]) if not l.get('expired')]
        self.cache={}
    def sees(self,p):
        key=tuple(p)
        if key in self.cache:return self.cache[key]
        value=self._sees(p)
        if len(self.cache)<100000:self.cache[key]=value
        return value
    def _sees(self,p):
        if self.origin is None:return False
        if math.dist(self.origin,p)>self.radius or not clear_line(self.origin,p,self.segments):return False
        if not self.dark:return True
        # A personal light radius is an explicit GM-authorized scene setting.
        personal=self.m.get('vision',{}).get('personalLight',0)*self.unit
        if personal and math.dist(self.origin,p)<=personal:return True
        return any(math.dist([l['x'],l['y']],p)<=l['radius']*self.unit and clear_line([l['x'],l['y']],p,self.segments) for l in self.lights)

    def segment_visible(self,a,b):
        """Prove the whole segment visible, including arbitrarily narrow shadows.

        Along a segment, line-of-sight changes only at a blocker intersection or
        a ray through a blocker endpoint. Illumination additionally changes at
        light-circle intersections. Test every resulting interval, not a fixed
        sampling step, which can miss a thin wall or a narrow unlit gap.
        """
        if not all(self.sees(p) for p in (a,b,[(a[0]+b[0])/2,(a[1]+b[1])/2])):return False
        dx,dy=b[0]-a[0],b[1]-a[1];length2=dx*dx+dy*dy
        if length2<1e-16:return True
        cuts={0.,1.}
        origins=[self.origin]
        if self.dark:origins.extend([[l['x'],l['y']] for l in self.lights])
        for origin in origins:
            minx,maxx=min(origin[0],a[0],b[0]),max(origin[0],a[0],b[0]);miny,maxy=min(origin[1],a[1],b[1]),max(origin[1],a[1],b[1])
            for c,d in self.segments:
                if max(c[0],d[0])<minx or min(c[0],d[0])>maxx or max(c[1],d[1])<miny or min(c[1],d[1])>maxy:continue
                for t,_ in crossings(a,b,c,d):cuts.add(t)
                for end in (c,d):
                    vx,vy=end[0]-origin[0],end[1]-origin[1];det=dx*vy-dy*vx
                    if abs(det)<1e-12:continue
                    t=((origin[0]-a[0])*vy-(origin[1]-a[1])*vx)/det
                    if 0<t<1:
                        px,py=a[0]+dx*t-origin[0],a[1]+dy*t-origin[1]
                        if px*vx+py*vy>=vx*vx+vy*vy-1e-10:cuts.add(t)
        if self.dark:
            circles=[([l['x'],l['y']],l['radius']*self.unit) for l in self.lights]
            personal=self.m.get('vision',{}).get('personalLight',0)*self.unit
            if personal:circles.append((self.origin,personal))
            for center,radius in circles:
                ox,oy=a[0]-center[0],a[1]-center[1];linear=2*(ox*dx+oy*dy);constant=ox*ox+oy*oy-radius*radius;disc=linear*linear-4*length2*constant
                if disc>=0:
                    for t in ((-linear-math.sqrt(disc))/(2*length2),(-linear+math.sqrt(disc))/(2*length2)):
                        if 0<t<1:cuts.add(t)
        ordered=sorted(cuts)
        return all(self.sees([a[0]+dx*t,a[1]+dy*t]) for t in [*ordered,*[(lo+hi)/2 for lo,hi in zip(ordered,ordered[1:])]])

    def polygon_visible(self,points):
        return all(self.segment_visible(a,b) for a,b in zip(points,points[1:]+points[:1]))


def observer(room,m,s):
    characters={c['id']:c for c in room.get('characters',[])}
    options=[t for t in m.get('tokens',[]) if t.get('characterId') in characters and not t.get('secret') and not characters[t['characterId']].get('hidden') and (s.get('role')=='gm' or characters[t['characterId']].get('owner')==s.get('owner'))]
    wanted=room.get('locationObservers',{}).get(s.get('owner','')) or m.get('observerId')
    token=next((t for t in options if t['characterId']==wanted),options[0] if options else None)
    return token,[dict(id=t['characterId'],name=characters[t['characterId']]['name']) for t in options]


@lru_cache(maxsize=48)
def _projection(serialized,origin):
    m=json.loads(serialized);sight=Sight(m,origin);safe=copy.deepcopy(m)
    ids=visible_ids(m)
    safe['features']=[f for f in m['features'] if f['id'] in ids and sight.sees([f['x']+f['w']/2,f['y']+f['h']/2]) and sight.polygon_visible(polygon(f))]
    visible_features={f['id'] for f in safe['features']}
    # Clip paths on the server; unseen bends are never included in the payload.
    paths=[]
    for path in m['paths']:
        if path.get('secret') or any(i not in ids for i in path.get('refs',[])):continue
        pieces=[];current=[]
        for a,b in zip(path['points'],path['points'][1:]):
            count=max(1,math.ceil(math.dist(a,b)/8))
            for i in range(count):
                p=[a[k]+(b[k]-a[k])*i/count for k in (0,1)];q=[a[k]+(b[k]-a[k])*(i+1)/count for k in (0,1)]
                if sight.segment_visible(p,q):
                    if not current:current=[p]
                    current.append(q)
                elif current:pieces.append(current);current=[]
        if current:pieces.append(current)
        for i,pts in enumerate(pieces):paths.append({**path,'id':path.get('id','path')+'-visible-'+str(i),'points':pts,'refs':[v for v in path.get('refs',[]) if v in visible_features]})
    safe['paths']=paths;safe['river']=[];safe['trees']=[t for t in m.get('trees',[]) if sight.sees(t[:2])]
    safe['tokens']=[t for t in m.get('tokens',[]) if sight.sees([t['x'],t['y']])]
    safe['stairs']=[x for x in m.get('stairs',[]) if x.get('revealed') and sight.sees([x['x'],x['y']])]
    safe['exploration']['lights']=[l for l in m.get('exploration',{}).get('lights',[]) if not l.get('secret') and sight.sees([l['x'],l['y']])]
    safe['exploration']['doors']={}
    # Conservative full-cell visibility avoids disclosing geometry across edges.
    cells=[];step=20
    if origin:
        for y in range(max(0,int((origin[1]-sight.radius)//step)*step),min(m['height'],int(origin[1]+sight.radius)+step),step):
            for x in range(max(0,int((origin[0]-sight.radius)//step)*step),min(m['width'],int(origin[0]+sight.radius)+step),step):
                w,h=min(step,m['width']-x),min(step,m['height']-y)
                if sight.sees([x+w/2,y+h/2]) and sight.polygon_visible([[x,y],[x+w,y],[x+w,y+h],[x,y+h]]):cells.append([x,y,w,h])
    safe['visibility']=dict(enabled=True,cells=cells,observerPlaced=origin is not None)
    return safe


def filter_map(room,m,s):
    token,options=observer(room,m,s)
    if not m.get('vision',{}).get('enabled'):return copy.deepcopy(m)
    if not within_budget(m):
        safe=copy.deepcopy(m)
        for key in ('features','paths','tokens','stairs','trees','river'):safe[key]=[]
        safe['exploration']=dict(enabled=False,discovered=[],dark=True,doors={},lights=[])
        safe['population']=dict(generatorVersion=1,public=True,households=[],residents=[])
        safe['visibility']=dict(enabled=True,cells=[],observerPlaced=token is not None,reason='План слишком сложен для личного обзора. Мастер должен разделить его на этажи.')
        return safe
    # Another hero moving must not invalidate every viewer's geometric sight.
    # Version and token visibility are current data, applied after the cache.
    raw={k:copy.deepcopy(v) for k,v in m.items() if k not in ('version','tokens','visionPreview','observerOptions','population','settings','undoCount')}
    raw.setdefault('exploration',dict(enabled=False,discovered=[],dark=False,doors={},lights=[]))
    result=copy.deepcopy(_projection(json.dumps(raw,sort_keys=True,separators=(',',':')),tuple([token['x'],token['y']]) if token else None))
    sight=Sight(m,[token['x'],token['y']] if token else None)
    result['version']=m['version'];result['tokens']=[copy.deepcopy(t) for t in m.get('tokens',[]) if sight.sees([t['x'],t['y']])]
    result['observerId']=token['characterId'] if token else '';result['observerOptions']=options
    if 'population' in m:
        from settlement_population import public_population
        result['population']=public_population(m['population'],{f['id'] for f in result['features']})
    return result
