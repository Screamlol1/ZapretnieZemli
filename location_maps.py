"""Original seeded location plans; geometry is independent of RPG checks."""
import copy
import hashlib
import math
import random
import secrets
from campaign_rules import coordinate
from location_editor import edit as edit_plan, snapshot, remember, undo, feature_bounds

KINDS = {'settlement', 'camp', 'fortress', 'ruins', 'dungeon', 'cave'}
ART_IDS = ('thatch','shingle','tile','barn','tavern','smithy','chapel','manor','keep','tower','gate','ruin','tent','pavilion','supplies','well','market','fire','bridge','oak','pine','rocks','room','cave')
SIZES = dict(small=(760,560), medium=(1000,760), large=(1240,920))

def text(value, limit=80):
    if not isinstance(value,str) or len(value)>limit:raise ValueError('Проверьте длину текста карты.')
    return value.strip()

def settings(raw):
    if not isinstance(raw,dict):raise ValueError('Нужны настройки карты.')
    kind=raw.get('kind','settlement');size=raw.get('size','medium');density=raw.get('density','normal')
    if kind not in KINDS or size not in SIZES or density not in ('sparse','normal','dense'):raise ValueError('Неизвестный тип, размер или плотность карты.')
    for k in ('water','walls'):
        if k in raw and type(raw[k])!=bool:raise ValueError('Проверьте настройки реки и стен.')
    return dict(kind=kind,size=size,density=density,seed=text(raw.get('seed','')) or secrets.token_hex(6),
                water=bool(raw.get('water')) and kind in ('settlement','ruins','camp','fortress'),
                walls=kind=='fortress' or bool(raw.get('walls')) and kind in ('settlement','camp'))

def generate(cfg):
    """Version 1: one local PRNG, stable ordering and no global random state."""
    rng=random.Random(int.from_bytes(hashlib.sha256(cfg['seed'].encode()).digest(),'big'))
    w,h=SIZES[cfg['size']];kind=cfg['kind'];features=[];paths=[];trees=[]
    count={'sparse':.7,'normal':1,'dense':1.3}[cfg['density']]
    def feature(style,x,y,fw,fh,label='',shape='rect',points=None):
        f=dict(id='f'+str(len(features)+1),style=style,x=round(x,1),y=round(y,1),w=round(fw,1),h=round(fh,1),
               label=label,note='',gmNote='',secret=False,shape=shape)
        if points:f['points']=[[round(a,1),round(b,1)] for a,b in points]
        features.append(f);return f
    def path(points,style='road',refs=None):paths.append(dict(points=points,style=style,refs=refs or []))
    river=[]
    if cfg['water']:
        rx=round(w*.80);river=[[rx-20,0],[rx+10,h*.28],[rx-10,h*.55],[rx+25,h],[rx+78,h],[rx+42,h*.55],[rx+63,h*.28],[rx+30,0]]
    if kind in ('dungeon','cave'):
        cols={'small':3,'medium':4,'large':5}[cfg['size']];rows={'small':2,'medium':3,'large':3}[cfg['size']]
        cw=(w-100)/cols;ch=(h-100)/rows;rooms=[]
        for row in range(rows):
            for col in range(cols):
                rw=rng.uniform(.48,.66)*cw;rh=rng.uniform(.43,.65)*ch
                x=50+col*cw+(cw-rw)/2+rng.uniform(-8,8);y=50+row*ch+(ch-rh)/2+rng.uniform(-8,8)
                points=None
                if kind=='cave':points=[(x+rw/2+math.cos(i*math.pi/5)*rw/2*rng.uniform(.8,1.12),y+rh/2+math.sin(i*math.pi/5)*rh/2*rng.uniform(.8,1.12)) for i in range(10)]
                rooms.append(feature('cave' if kind=='cave' else 'room',x,y,rw,rh,'Вход' if not rooms else f'Зал {len(rooms)+1}', 'polygon' if points else 'rect',points))
        # A spanning tree guarantees every room is reachable. Extra connections form loops.
        connected={0};edges=set()
        while len(connected)<len(rooms):
            choices=[(a,b) for a in sorted(connected) for b in range(len(rooms)) if b not in connected and (abs(a-b)==cols or a//cols==b//cols and abs(a-b)==1)]
            a,b=rng.choice(choices);edges.add(tuple(sorted((a,b))));connected.add(b)
        for a in range(len(rooms)):
            for b in (a+1,a+cols):
                if b<len(rooms) and (b-a==cols or a//cols==b//cols) and rng.random()<.18*count:edges.add((a,b))
        for a,b in sorted(edges):
            f,g=rooms[a],rooms[b];sx,sy=round(f['x']+f['w']/2),round(f['y']+f['h']/2);tx,ty=round(g['x']+g['w']/2),round(g['y']+g['h']/2)
            path([[sx,sy],[tx,sy],[tx,ty]],'passage',[f['id'],g['id']])
        path([[rooms[0]['x']+rooms[0]['w']/2,0],[rooms[0]['x']+rooms[0]['w']/2,rooms[0]['y']+rooms[0]['h']/2]],'passage',[rooms[0]['id']])
    elif kind=='fortress':
        left,top,right,bottom=90,75,w*.71 if cfg['water'] else w-90,h-75
        mid=(left+right)/2
        path([[mid-28,bottom],[left,bottom],[left,top],[right,top],[right,bottom],[mid+28,bottom]],'wall')
        for x,y in ((left,top),(right,top),(right,bottom),(left,bottom)):feature('tower',x-24,y-24,48,48,'Башня','ellipse')
        cx=(left+right)/2;path([[cx,h],[cx,top+100]])
        feature('keep',cx-70,top+65,140,115,'Донжон')
        feature('gate',cx-35,bottom-17,70,34,'Ворота')
        feature('well',cx-12,bottom-120,24,24,'Колодец','ellipse')
        for i in range(max(2,round((h-320)/110))):
            y=top+220+i*95
            for x in (left+35,right-120):feature('building',x,y,85,50,'Казарма' if i==0 else 'Склад')
    elif kind=='camp':
        cx,cy=w*.43 if cfg['water'] else w/2,h/2
        path([[cx,h],[cx,cy+30]])
        feature('fire',cx-18,cy-18,36,36,'Костёр','ellipse')
        n=round({'small':8,'medium':12,'large':16}[cfg['size']]*count)
        for i in range(n):
            angle=2*math.pi*i/n;rx=min(w*.28,240);ry=h*.29
            feature('tent',cx+math.cos(angle)*rx-28,cy+math.sin(angle)*ry-22,56,44,'Шатёр вожака' if i==0 else f'Палатка {i+1}')
        feature('supply',cx-105,cy-65,45,30,'Припасы')
        if cfg['walls']:path([[cx-25,h-60],[cx-w*.34,h-60],[cx-w*.34,60],[cx+w*.34,60],[cx+w*.34,h-60],[cx+25,h-60]],'palisade')
    else:
        cx=round(w*.46);cy=round(h*.50);path([[0,cy],[w,cy]]);path([[cx,0],[cx,h]])
        if river:feature('bridge',w*.80-15,cy-15,88,30,'Мост')
        if cfg['walls']:
            for pts in ([[cx-20,55],[55,55],[55,cy-20]],[[55,cy+20],[55,h-55],[cx-20,h-55]],[[cx+20,h-55],[w-55,h-55],[w-55,cy+20]],[[w-55,cy-20],[w-55,55],[cx+20,55]]):path(pts,'wall')
        spacing={'sparse':150,'normal':120,'dense':100}[cfg['density']]
        labels=['Таверна','Кузница','Дом старосты','Святилище','Амбар','Торговый двор'] if kind=='settlement' else ['Разрушенный храм','Старая башня','Заросший двор','Обрушенный дом']
        building_index=0
        for y in range(90,h-75,spacing):
            for x in range(90,w-75,spacing):
                if abs(x-cx)<55 or abs(y-cy)<50 or cfg['water'] and abs(x-w*.80)<85 or rng.random()<.18:continue
                if cx+5<x<cx+135 and cy+5<y<cy+120:continue # Leave space for the market square.
                fw=rng.randint(30,48);fh=rng.randint(28,44)
                label=labels[building_index] if building_index<len(labels) else ''
                fw,fh={'Таверна':(72,56),'Кузница':(48,40),'Дом старосты':(64,56),'Святилище':(56,72),'Амбар':(64,40),'Торговый двор':(64,56)}.get(label,(fw,fh))
                feature('building' if kind=='settlement' else 'ruin',x-fw/2+rng.randint(-7,7),y-fh/2+rng.randint(-7,7),fw,fh,label)
                building_index+=1
        feature('square',cx+35,cy+35,68,55,'Рынок' if kind=='settlement' else 'Древняя площадь')
        feature('well',cx-40,cy+32,23,23,'Колодец','ellipse')
    if kind not in ('dungeon','cave'):
        for i in range(48):
            x=rng.randrange(16,w-16);y=rng.choice([rng.randrange(12,48),rng.randrange(h-48,h-12)])
            if cfg['water'] and abs(x-w*.80)<80:continue
            trees.append([x,y,rng.randrange(8,16)])
    return dict(generatorVersion=2,width=w,height=h,cellSize=40,metersPerCell=5 if kind in ('dungeon','cave') else 2 if kind=='camp' else 10,
                features=features,paths=paths,river=river,trees=trees)

def find(room, identifier):
    m=next((m for m in room.get('locationMaps',[]) if m['id']==identifier),None)
    if not m:raise ValueError('Карта локации не найдена.')
    return m

def source(room, raw):
    if not isinstance(raw,dict):raise ValueError('Не указано место карты.')
    if raw.get('kind')=='library':return dict(kind='library'),None
    if raw.get('kind')=='hex':
        p=coordinate(raw,room);cell=room['maps']['world'].get(f"{p['x']},{p['y']}",{})
        if not cell.get('label'):raise ValueError('Сначала сохраните место с названием в этом гексе.')
        return dict(kind='hex',**p),cell
    if raw.get('kind')=='workshop':
        e=next((e for e in room.get('workshop',[]) if e['id']==raw.get('id')),None)
        if not e or e['kind'] not in ('settlement','ruin'):raise ValueError('Нужна заготовка поселения или руин.')
        if e.get('published',{}).get('kind')=='place':return source(room,dict(kind='hex',x=e['published']['x'],y=e['published']['y']))
        return dict(kind='workshop',id=e['id']),e
    raise ValueError('Неизвестное место карты.')

def apply(room, session, data):
    if session['role']!='gm':raise PermissionError('Карты локаций создаёт и изменяет Мастер.')
    maps=room.setdefault('locationMaps',[]);action=data['action']
    if action=='locationMapGenerate':
        if data.get('id'):
            old=find(room,data['id']);src,parent=source(room,old['source'])
        else:
            src,parent=source(room,data.get('source',dict(kind='library')))
            old=find(room,parent['locationMapId']) if parent and parent.get('locationMapId') else None
        if old:
            if data.get('version')!=old['version']:raise ValueError('Карта уже изменена. Откройте актуальную версию.')
            if data.get('replace') is not True:raise ValueError('Подтвердите замену плана: ручные правки будут сброшены.')
        elif len(maps)>=40:raise ValueError('В кампании уже 40 карт. Удалите ненужную карту.')
        title=text(data.get('title',''))
        if not title:raise ValueError('Назовите локацию.')
        cfg=settings(data.get('settings',{}))
        saved=dict(id=old['id'] if old else secrets.token_hex(12),version=old['version']+1 if old else 1,
                   title=title,kind=cfg['kind'],settings=cfg,source=src,revealed=False,**generate(cfg))
        room['locationMaps']=[m for m in maps if m['id']!=saved['id']]+[saved]
        room.get('locationHistory',{}).pop(saved['id'],None)
        if parent:
            parent['locationMapId']=saved['id']
            if src['kind']=='workshop':parent['version']+=1
        return
    m=find(room,data.get('id'))
    if data.get('version')!=m['version']:raise ValueError('Карта уже изменена. Обновите её перед сохранением.')
    before=snapshot(m) if action in ('locationMapEdit','locationMapFeature') else None
    if action=='locationMapReveal':
        if type(data.get('revealed'))!=bool:raise ValueError('Выберите видимость карты.')
        if data['revealed'] and m['source']['kind']=='workshop':raise ValueError('Сначала разместите заготовку на общей карте.')
        if data['revealed'] and m['source']['kind']=='hex':
            _,cell=source(room,m['source'])
            if cell.get('hidden') or cell.get('siteHidden'):raise ValueError('Сначала откройте само место игрокам на общей карте.')
        m['revealed']=data['revealed']
    elif action=='locationMapEdit':
        edit_plan(room,m,data,ART_IDS)
    elif action=='locationMapUndo':
        undo(room,m)
    elif action=='locationMapFeature':
        f=next((f for f in m['features'] if f['id']==data.get('feature')),None)
        if not f:raise ValueError('Объект не найден.')
        if type(data.get('secret'))!=bool:raise ValueError('Выберите видимость объекта.')
        art=data.get('art',f.get('art',''))
        if not isinstance(art,str) or art not in ('',*ART_IDS):raise ValueError('Выберите иллюстрацию из набора.')
        if 'widthMeters' in data or 'heightMeters' in data:
            width,height=data.get('widthMeters'),data.get('heightMeters')
            if any(type(v) not in (int,float) or not math.isfinite(v) or not .5<=v<=100 for v in (width,height)):raise ValueError('Размеры объекта: от 0,5 до 100 метров.')
            fw,fh=width*m['cellSize']/m['metersPerCell'],height*m['cellSize']/m['metersPerCell']
            x,y=f['x']+(f['w']-fw)/2,f['y']+(f['h']-fh)/2
            if x<0 or y<0 or x+fw>m['width'] or y+fh>m['height']:raise ValueError('Объект такого размера выходит за границы плана.')
            if f.get('points'):f['points']=[[x+(px-f['x'])*fw/f['w'],y+(py-f['y'])*fh/f['h']] for px,py in f['points']]
            f.update(x=x,y=y,w=fw,h=fh)
            feature_bounds(m,f)
        f.update(label=text(data.get('label','')),note=text(data.get('note',''),1200),gmNote=text(data.get('gmNote',''),1200),secret=data['secret'],art=art)
    elif action=='locationMapDelete':
        if data.get('confirmed') is not True:raise ValueError('Подтвердите удаление карты.')
        room['locationMaps']=[x for x in maps if x['id']!=m['id']]
        room.get('locationHistory',{}).pop(m['id'],None)
        for cell in room['maps']['world'].values():
            if cell.get('locationMapId')==m['id']:cell.pop('locationMapId')
        for e in room.get('workshop',[]):
            if e.get('locationMapId')==m['id']:e.pop('locationMapId');e['version']+=1
        return
    else:raise ValueError('Неизвестное действие карты локации.')
    if before is not None:remember(room,m,before)
    m['version']+=1

def publish_workshop_map(room, entry, cell, p):
    if entry.get('locationMapId'):
        m=find(room,entry['locationMapId']);m['source']=dict(kind='hex',**p);m['version']+=1
        cell['locationMapId']=m['id']

def redact(room):
    room.pop('locationHistory',None)
    visible=[]
    for m in room.get('locationMaps',[]):
        if not m.get('revealed') or m['source']['kind']=='workshop':continue
        if m['source']['kind']=='hex':
            cell=room['maps']['world'].get(f"{m['source']['x']},{m['source']['y']}",{})
            if cell.get('hidden') or cell.get('siteHidden') or cell.get('locationMapId')!=m['id']:continue
        safe=copy.deepcopy(m);safe.pop('settings',None) # Seed could reconstruct secret rooms.
        safe.pop('undoCount',None)
        ids={f['id'] for f in safe['features'] if not f['secret']}
        safe['features']=[{k:v for k,v in f.items() if k not in ('gmNote','secret')} for f in safe['features'] if f['id'] in ids]
        safe['paths']=[{k:v for k,v in p.items() if k!='secret'} for p in safe['paths'] if not p.get('secret') and all(i in ids for i in p['refs'])]
        actors={c['id'] for c in room['characters'] if not c.get('hidden')}
        safe['tokens']=[{k:v for k,v in t.items() if k!='secret'} for t in safe.get('tokens',[]) if not t.get('secret') and t['characterId'] in actors]
        visible.append(safe)
    room['locationMaps']=visible;ids={m['id'] for m in visible}
    for cell in room['maps']['world'].values():
        if cell.get('locationMapId') not in ids:cell.pop('locationMapId',None)
