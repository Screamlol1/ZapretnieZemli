"""Portable adventure templates, with bounded validation and remapped identities."""
import copy
import hashlib
import json
import math
from pathlib import Path
import secrets
import subprocess
from node_runtime import run_node


def label(value,limit=120):
    if not isinstance(value,str) or len(value)>limit:raise ValueError('Слишком длинное или некорректное поле набора.')
    return value.strip()


def number(value,low,high):
    if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:raise ValueError('Неверное число или координаты в наборе.')
    return value


def identifier(value):
    value=label(value,100)
    if not value:raise ValueError('В наборе отсутствует идентификатор.')
    return value


def collection(value,limit):
    if not isinstance(value,list) or len(value)>limit:raise ValueError('Превышен предел объектов набора.')
    if any(not isinstance(v,dict) for v in value):raise ValueError('Некорректная запись набора.')
    return value


def actor_definition(c):
    if c['kind']=='monster':return dict(kind='monster',name=c['name'],hidden=c.get('hidden',False),monster=copy.deepcopy(c['monster']))
    s=c['sheet'];return dict(kind='npc',name=c['name'],hidden=c.get('hidden',False),kin=s['kin'],profession=s['profession'],attrs=s['attrs'],skills=s['skills'],gear=s.get('gear',[]),notes=s.get('notes',''),path=s.get('path'),pathRank=s.get('pathRank',0),talents=s.get('talents',{}))


def export(room,mid,workshop_ids=(),include_floors=True):
    from location_maps import find
    first=find(room,mid);group=first.get('level',{}).get('group',first['id'])
    maps=[m for m in room.get('locationMaps',[]) if m['id']==mid or include_floors and m.get('level',{}).get('group')==group]
    mids={m['id'] for m in maps};cids={t['characterId'] for m in maps for t in m.get('tokens',[])}
    actors=[dict(id=c['id'],definition=actor_definition(c),**({'visual':copy.deepcopy(c['visual'])} if 'visual' in c else {})) for c in room['characters'] if c['id'] in cids and c['kind'] in ('npc','monster')]
    actorids={c['id'] for c in actors};clean=[]
    for m in maps:
        from exploration import ensure_paths
        ensure_paths(m)
        safe={k:copy.deepcopy(v) for k,v in m.items() if k not in ('undoCount','visionPreview','observerId','observerOptions','visibility')}
        safe['source']=dict(kind='library');safe['revealed']=False
        safe['tokens']=[t for t in safe.get('tokens',[]) if t['characterId'] in actorids]
        safe['stairs']=[s for s in safe.get('stairs',[]) if s['targetMap'] in mids]
        for light in safe.get('exploration',{}).get('lights',[]):
            from injuries import now
            light['remainingMinutes']=max(0,light['expiresAt']-now(room)) if light.get('expiresAt') is not None else None
            light.pop('expiresAt',None)
            light.pop('expired',None)
        clean.append(safe)
    workshop=[{k:copy.deepcopy(v) for k,v in e.items() if k in ('kind','fields','locked','tables','trace')} for e in room.get('workshop',[]) if e['id'] in workshop_ids or e.get('locationMapId') in mids]
    pack=dict(format='zz-adventure',version=1,title=first['title'],maps=clean,actors=actors,workshop=workshop)
    if len(maps)>12 or len(actors)>20 or len(json.dumps(pack,ensure_ascii=False).encode('utf-8'))>2_000_000:raise ValueError('Набор слишком велик. Экспортируйте отдельный этаж или уменьшите число размещённых противников (предел 20).')
    return pack


def validate(pack):
    from location_maps import ART_IDS,KINDS
    if not isinstance(pack,dict) or pack.get('format')!='zz-adventure' or pack.get('version')!=1:raise ValueError('Нужен набор приключения zz-adventure версии 1.')
    try:serialized=json.dumps(pack,ensure_ascii=False,allow_nan=False)
    except (ValueError,TypeError,RecursionError):raise ValueError('Повреждён JSON набора.')
    if len(serialized.encode('utf-8'))>2_000_000:raise ValueError('Набор больше 2 МБ. Разделите приключение.')
    maps=collection(pack.get('maps'),12);actors=collection(pack.get('actors',[]),20);workshop=collection(pack.get('workshop',[]),30)
    if not maps:raise ValueError('В наборе нет карт.')
    result=dict(format='zz-adventure',version=1,title=label(pack.get('title','Приключение')),maps=[],actors=[],workshop=[])
    all_mapids=set()
    for m in maps:
        mid=identifier(m.get('id'))
        if mid in all_mapids:raise ValueError('Повторный идентификатор карты.')
        all_mapids.add(mid)
        if m.get('kind') not in KINDS:raise ValueError('Неизвестный тип карты.')
        safe=dict(id=mid,version=1,title=label(m.get('title'),80),kind=m['kind'],source=dict(kind='library'),revealed=False,
                  width=number(m.get('width'),100,2000),height=number(m.get('height'),100,2000),cellSize=number(m.get('cellSize'),10,100),metersPerCell=number(m.get('metersPerCell'),.5,100),generatorVersion=3,
                  features=[],paths=[],tokens=[],river=[],trees=[],stairs=[])
        def point(p):
            if not isinstance(p,list) or len(p)!=2:raise ValueError('Некорректная точка набора.')
            return [number(p[0],0,safe['width']),number(p[1],0,safe['height'])]
        features=set()
        for f in collection(m.get('features'),300):
            fid=identifier(f.get('id'))
            if fid in features:raise ValueError('Повторный идентификатор объекта.')
            features.add(fid)
            style=f.get('style');art=f.get('art','')
            if style not in (*ART_IDS,'building','square','supply') or art not in ('',*ART_IDS):raise ValueError('Неизвестная иллюстрация набора.')
            x,y=point([f.get('x'),f.get('y')]);w=number(f.get('w'),.1,safe['width']-x);h=number(f.get('h'),.1,safe['height']-y)
            shape=f.get('shape','rect')
            if shape not in ('rect','ellipse','polygon'):raise ValueError('Некорректная форма объекта.')
            obj=dict(id=fid,style=style,art=art,x=x,y=y,w=w,h=h,shape=shape,rotation=number(f.get('rotation',0),0,360),label=label(f.get('label',''),80),note=label(f.get('note',''),1200),gmNote=label(f.get('gmNote',''),1200),secret=f.get('secret') is True,blocksSight=f.get('blocksSight') is True)
            if shape=='polygon':
                raw=f.get('points')
                if not isinstance(raw,list) or not 3<=len(raw)<=40:raise ValueError('Некорректный контур объекта.')
                obj['points']=[point(p) for p in raw]
            from location_editor import feature_bounds
            feature_bounds(safe,obj);safe['features'].append(obj)
        pathids=set()
        for p in collection(m.get('paths'),300):
            pid=identifier(p.get('id'))
            if pid in pathids:raise ValueError('Повторный идентификатор линии.')
            pathids.add(pid)
            if p.get('style') not in ('wall','road','palisade','passage'):raise ValueError('Неизвестный вид линии.')
            pts=p.get('points');refs=p.get('refs',[])
            if not isinstance(pts,list) or not 2<=len(pts)<=500 or not isinstance(refs,list) or len(refs)>2 or any(r not in features for r in refs):raise ValueError('Неверная линия или ссылка на помещение.')
            safe['paths'].append(dict(id=pid,style=p['style'],points=[point(x) for x in pts],refs=refs,secret=p.get('secret') is True))
        for t in collection(m.get('tokens',[]),100):
            x,y=point([t.get('x'),t.get('y')]);safe['tokens'].append(dict(id=identifier(t.get('id')),characterId=identifier(t.get('characterId')),x=x,y=y,rotation=number(t.get('rotation',0),0,360),secret=t.get('secret') is True))
        for key,maximum in (('river',40),('trees',200)):
            raw=m.get(key,[])
            if not isinstance(raw,list) or len(raw)>maximum:raise ValueError('Неверный фон карты.')
            for p in raw:
                xy=point(p[:2]);safe[key].append(xy+[number(p[2],1,100)] if key=='trees' and len(p)==3 else xy)
            if key=='trees' and any(len(p)!=3 for p in safe[key]):raise ValueError('Неверное дерево.')
        from location_themes import style_settings
        cfg=style_settings(dict(culture=m.get('culture','neutral'),ground=m.get('ground','auto'),roadSurface=m.get('roadSurface','auto')))
        safe.update(culture=cfg['culture'],ground=m.get('ground','grass'),roadSurface=m.get('roadSurface','earth'))
        raw_level=m.get('level',{})
        if raw_level:safe['level']=dict(group=identifier(raw_level.get('group')),name=label(raw_level.get('name','Этаж'),80))
        for stair in collection(m.get('stairs',[]),30):
            x,y=point([stair.get('x'),stair.get('y')]);safe['stairs'].append(dict(id=identifier(stair.get('id')),name=label(stair.get('name','Лестница'),80),targetMap=identifier(stair.get('targetMap')),targetStair=identifier(stair.get('targetStair')),x=x,y=y,revealed=stair.get('revealed') is True))
        raw_e=m.get('exploration',{})
        if not isinstance(raw_e,dict):raise ValueError('Неверные параметры исследования.')
        discovered=raw_e.get('discovered',[]);doors=raw_e.get('doors',{})
        if not isinstance(discovered,list) or any(v not in features for v in discovered) or not isinstance(doors,dict) or any(k not in pathids or v not in ('open','closed','locked') for k,v in doors.items()):raise ValueError('Неверные ссылки открытия или дверей.')
        safe['exploration']=dict(enabled=raw_e.get('enabled') is True,dark=raw_e.get('dark') is True,discovered=discovered,doors=doors,lights=[])
        for l in collection(raw_e.get('lights',[]),50):
            x,y=point([l.get('x'),l.get('y')]);remaining=l.get('remainingMinutes')
            safe['exploration']['lights'].append(dict(id=identifier(l.get('id')),name=label(l.get('name','Свет'),80),x=x,y=y,radius=number(l.get('radius'),.1,100),remainingMinutes=None if remaining is None else number(remaining,0,525600),secret=l.get('secret') is True))
        v=m.get('vision',{})
        if not isinstance(v,dict):raise ValueError('Неверные настройки личного обзора.')
        safe['vision']=dict(enabled=v.get('enabled') is True,range=number(v.get('range',30),1,100),personalLight=number(v.get('personalLight',0),0,100))
        from location_vision import within_budget
        if safe['vision']['enabled'] and not within_budget(safe):raise ValueError('Слишком сложный план для личного обзора. Разделите набор на этажи.')
        population=m.get('population')
        if population:
            houses=collection(population.get('households',[]),400);residents=collection(population.get('residents',[]),400)
            clean_h=[];clean_r=[]
            houseids={identifier(h.get('id')) for h in houses}
            if len(houseids)!=len(houses):raise ValueError('Повторный идентификатор семьи.')
            residentids=set()
            for h in houses:
                home=h.get('homeFeatureId','')
                if home and home not in features:raise ValueError('Дом семьи не найден.')
                clean_h.append(dict(id=h['id'],name=label(h.get('name',''),80),homeFeatureId=home,note=label(h.get('note',''),1200),gmNote=label(h.get('gmNote',''),1200),revealed=h.get('revealed') is True))
            for r in residents:
                rid=identifier(r.get('id'));house=r.get('householdId','');work=r.get('workplaceFeatureId','')
                if rid in residentids or house and house not in houseids or work and work not in features:raise ValueError('Неверные связи жителя.')
                residentids.add(rid)
                item={k:label(r.get(k,''),1200 if k in ('description','gmNote') else 80 if k=='occupation' else 60) for k in ('name','kin','ageGroup','familyRole','role','occupation','description','gmNote')}
                from settlement_population import DATA
                for key,values in (('kin',DATA['kins']),('ageGroup',DATA['ageGroups']),('familyRole',DATA['familyRoles']),('role',DATA['roles'])):
                    if item[key] not in values:raise ValueError('Неизвестное значение поля жителя: '+key)
                item.update(id=rid,householdId=house,workplaceFeatureId=work,revealed=r.get('revealed') is True);clean_r.append(item)
            safe['population']=dict(generatorVersion=1,seed='',source='Переносимый набор приключения',households=clean_h,residents=clean_r)
        result['maps'].append(safe)
    actorids=set()
    for a in actors:
        aid=identifier(a.get('id'))
        if aid in actorids:raise ValueError('Повторный идентификатор противника.')
        actorids.add(aid)
        try:checked=run_node([str(Path(__file__).parent/'validate-actor.mjs')],input=json.dumps(a.get('definition')),text=True,encoding='utf-8',capture_output=True,timeout=8)
        except (OSError,subprocess.TimeoutExpired):raise ValueError('Не удалось проверить противников набора.')
        if checked.returncode:raise ValueError('Противник набора: '+checked.stderr[:400])
        character=json.loads(checked.stdout)
        if 'visual' in a:
            from visual_appearance import validate_visual
            character['visual']=validate_visual(a['visual'])
        result['actors'].append(dict(id=aid,character=character))
    for m in result['maps']:
        if any(t['characterId'] not in actorids for t in m['tokens']):raise ValueError('Жетон ссылается на отсутствующего противника.')
        for stair in m['stairs']:
            target=next((x for x in result['maps'] if x['id']==stair['targetMap']),None)
            other=next((x for x in target['stairs'] if x['id']==stair['targetStair']),None) if target else None
            if not other or other['targetMap']!=m['id'] or other['targetStair']!=stair['id']:raise ValueError('Лестница должна иметь ответный переход внутри набора.')
    import workshop as library
    temp=dict(workshop=[])
    for entry in workshop:
        library.apply(temp,dict(role='gm'),dict(action='workshopSave',draft=entry))
    result['workshop']=temp['workshop']
    digest=hashlib.sha256(serialized.encode('utf-8')).hexdigest()
    return result,digest


def import_pack(room,checked):
    from injuries import now
    if len(room.get('locationMaps',[]))+len(checked['maps'])>40 or len(room['characters'])+len(checked['actors'])>100 or len(room.get('workshop',[]))+len(checked['workshop'])>100:raise ValueError('Недостаточно места для всего набора. Импорт не выполнен.')
    # Build the entire result before mutating the room.
    mids={m['id']:secrets.token_hex(12) for m in checked['maps']};aids={a['id']:secrets.token_hex(12) for a in checked['actors']};groups={}
    stairs={(m['id'],s['id']):secrets.token_hex(8) for m in checked['maps'] for s in m['stairs']}
    maps=[];actors=[]
    for raw in checked['maps']:
        m=copy.deepcopy(raw);old=m['id'];m['id']=mids[old];m['revealed']=False;m['version']=1
        if m.get('level'):
            group=m['level']['group'];m['level']['group']=groups.setdefault(group,secrets.token_hex(12))
        fids={f['id']:secrets.token_hex(8) for f in m['features']};pids={p['id']:secrets.token_hex(8) for p in m['paths']}
        for f in m['features']:f['id']=fids[f['id']]
        for p in m['paths']:p['id']=pids[p['id']];p['refs']=[fids[v] for v in p['refs']]
        e=m['exploration'];e['discovered']=[fids[v] for v in e['discovered']];e['doors']={pids[k]:v for k,v in e['doors'].items()}
        for l in e['lights']:
            minutes=l.pop('remainingMinutes',None);l['id']=secrets.token_hex(8);l['expiresAt']=None if minutes is None else now(room)+minutes
        for t in m['tokens']:t['id']=secrets.token_hex(8);t['characterId']=aids[t['characterId']]
        for s in m['stairs']:
            sid=s['id'];target=s['targetMap'];s['id']=stairs[(old,sid)];s['targetStair']=stairs[(target,s['targetStair'])];s['targetMap']=mids[target]
        if m.get('population'):
            pop=m['population'];hids={h['id']:secrets.token_hex(8) for h in pop['households']}
            for h in pop['households']:h['id']=hids[h['id']];h['homeFeatureId']=fids.get(h['homeFeatureId'],'')
            for r in pop['residents']:r['id']=secrets.token_hex(8);r['householdId']=hids.get(r['householdId'],'');r['workplaceFeatureId']=fids.get(r['workplaceFeatureId'],'')
        maps.append(m)
    for a in checked['actors']:
        c=copy.deepcopy(a['character']);c.update(id=aids[a['id']],owner='gm',hidden=True)
        c['runtime']=dict(current=c['sheet']['attrs'].copy() if c['kind']=='npc' else dict(str=c['monster']['strength'],agi=c['monster']['agility'],wit=1,emp=1),wp=0);actors.append(c)
    entries=copy.deepcopy(checked['workshop'])
    for e in entries:e['id']=secrets.token_hex(12);e['version']=1
    room.setdefault('locationMaps',[]).extend(maps);room['characters'].extend(actors);room.setdefault('workshop',[]).extend(entries)
    return dict(maps=[m['id'] for m in maps],actors=[c['id'] for c in actors],title=checked['title'])
