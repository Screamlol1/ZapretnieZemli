"""Seeded, authored settlement residents attached to stable plan features.

Population ranges follow GM p.168; names, households and jobs are original
preparation material. These records have no character sheet or combat authority.
"""
import copy
import hashlib
import json
import random
import re
import secrets
from pathlib import Path

DATA=json.loads((Path(__file__).parent/'public'/'settlement-population-data.json').read_text(encoding='utf-8'))
MAX_RESIDENTS=400
ACTIONS=('locationMapPopulationGenerate','locationMapResidentSave','locationMapResidentDelete',
         'locationMapHouseholdSave','locationMapPopulationAssign','locationMapPopulationReveal')
HOUSE_PUBLIC=('id','name','homeFeatureId','note')
PERSON_PUBLIC=('id','name','kin','ageGroup','householdId','familyRole','role','occupation','workplaceFeatureId','description')
TRAITS=('Говорит негромко и внимательно слушает.','Всегда носит с собой небольшую памятную вещь.',
        'Легко запоминает лица гостей.','Предпочитает сначала предложить помощь.',
        'Соблюдает старые семейные обычаи.','Умеет разрядить спор спокойной шуткой.',
        'Внимательно следит за погодой.','С гордостью рассказывает о своей работе.')
MOTIVES=('Копит на ремонт дома.','Ищет пропавшую семейную вещь.','Хочет помириться с соседом.',
         'Мечтает освоить новое ремесло.','Опасается, что семье не хватит зимних запасов.',
         'Хранит обещание, данное давнему другу.')
COMMON_ROLES=('farmer','farmer','artisan','laborer','hunter','merchant','healer','innkeeper')
# Elf origins differ from human families; ogre and whiner accounts do not justify
# inventing biological parentage. These automatic groups are adult communities,
# not a claim that ogres are sterile or the whiner colony stories are proven.
# Manual family descriptions remain unrestricted (GM pp.52–54, 60–61, 70).
COMMUNITY_KINS=('elf','ogre','whiner')
SAURIAN_CRAFTS=('Гончар','Косторез','Плетельщик')
CULTURE_BUILDINGS={a['id']:a['role'] for c in json.loads((Path(__file__).parent/'public'/'location-cultures.json').read_text(encoding='utf-8')) for a in c['assets']}


def text(value,limit=1200):
    if not isinstance(value,str) or len(value)>limit:raise ValueError('Проверьте длину текста жителя или семьи.')
    return value.strip()


def choice(value,values,label):
    if not isinstance(value,str) or value not in values:raise ValueError('Выберите '+label+' из списка.')
    return value


def boolean(value):
    if type(value)!=bool:raise ValueError('Видимость должна быть включена или выключена.')
    return value


def population(m):
    if not m.get('population'):
        m['population']=dict(generatorVersion=1,seed='',source=DATA['source'],households=[],residents=[])
    return m['population']


def feature_tags(f):
    style=f.get('art') or f.get('style','')
    role=f.get('themeRole') or CULTURE_BUILDINGS.get(style,'')
    name=' '.join(str(f.get(k,'')) for k in ('baseLabel','label','style','art')).lower().replace('ё','е')
    tags=set()
    if style in ('building','thatch','shingle','tile','barn','tavern','smithy','chapel','manor','keep','tower','tent','pavilion','room','cave','ruin') or role in ('home','hall','shelter'):
        tags.add('home')
    for tag,pattern in (
        ('ruler',r'старост|правител|дворец|дворц|донжон|manor|keep'),
        ('guard',r'казарм|страж|караул|башн|ворот|tower|gate'),
        ('barracks',r'казарм|barrack'),
        ('artisan',r'кузниц|мастерск|ремесл|плотниц|столяр|гончар|ткац|ткач|кожевн|дубиль|камнерез|smithy|workshop'),
        ('merchant',r'рынок|рыноч|торгов|лавк|market'),
        ('innkeeper',r'таверн|трактир|постоял|tavern|inn'),
        ('priest',r'храм|святилищ|часовн|chapel|temple'),
        ('farmer',r'амбар|мельниц|ферм|хлев|barn'),
        ('hunter',r'леснич|охот|рыба'),
        ('healer',r'лечеб|лекар|знахар|травник')):
        if re.search(pattern,name):tags.add(tag)
    return tags


def feature_ref(m,value,home=False):
    value=text(value,80)
    if not value:return ''
    f=next((f for f in m['features'] if f['id']==value),None)
    if not f or home and 'home' not in feature_tags(f):
        raise ValueError('Выберите существующее жилое здание на этой карте.' if home else 'Место работы не найдено на карте.')
    return value


def detach(pop,feature_id=None):
    """Removing a building leaves its people intact and explicitly unassigned."""
    for h in pop.get('households',[]):
        if feature_id is None or h.get('homeFeatureId')==feature_id:h['homeFeatureId']=''
    for r in pop.get('residents',[]):
        if feature_id is None or r.get('workplaceFeatureId')==feature_id:r['workplaceFeatureId']=''


def default_count(room,m):
    source=m.get('source',{})
    entry=next((e for e in room.get('workshop',[]) if source.get('kind')=='workshop' and e['id']==source.get('id') or source.get('kind')=='hex' and e.get('published',{}).get('kind')=='place' and all(e['published'].get(k)==source.get(k) for k in ('x','y'))),None)
    size=entry.get('fields',{}).get('size','') if entry else ''
    return next((p['default'] for p in DATA['presets'].values() if size.startswith(p['label'])),40)


def generated_occupation(resident,feature):
    """Fit a newly generated job to a specialized workplace, never manual data."""
    if resident['role']!='artisan' or resident['kin']=='saurian':return
    name=' '.join(str(feature.get(k,'')) for k in ('baseLabel','label','style','art')).lower().replace('ё','е')
    for pattern,occupation in ((r'кузниц|smithy','Кузнец'),(r'плотниц|столяр','Плотник'),
                               (r'гончар','Гончар'),(r'ткац|ткач','Ткач'),
                               (r'кожевн|дубиль','Кожевник'),(r'каменщик|камнерез','Каменщик')):
        if re.search(pattern,name):
            resident['occupation']=occupation
            return


def assign(m,household_ids=None,resident_ids=None,generated=False):
    """Only fill missing links, balancing residents without moving map geometry."""
    pop=population(m);features=m['features'];tags={f['id']:feature_tags(f) for f in features}
    homes=[f['id'] for f in features if 'home' in tags[f['id']]]
    by_house={h['id']:[r for r in pop['residents'] if r['householdId']==h['id']] for h in pop['households']}
    used={fid:sum(len(by_house[h['id']]) for h in pop['households'] if h.get('homeFeatureId')==fid) for fid in homes}
    for h in pop['households']:
        if h.get('homeFeatureId') or household_ids is not None and h['id'] not in household_ids:continue
        members=by_house[h['id']];roles={r['role'] for r in members}
        tag='ruler' if 'ruler' in roles else 'barracks' if roles and roles<={'guard'} else None
        preferred=[fid for fid in homes if tag and tag in tags[fid]]
        candidates=preferred or homes
        if generated and any(r['kin']=='saurian' and r['role']=='artisan' for r in members):
            candidates=[fid for fid in candidates if not re.search(r'кузниц|smithy',' '.join(str(f.get(k,'')) for f in features if f['id']==fid for k in ('baseLabel','label','style','art')).lower())]
        if candidates:
            fid=min(candidates,key=lambda f:(used[f],f));h['homeFeatureId']=fid;used[fid]+=len(members)
    household={h['id']:h for h in pop['households']}
    work_count={f['id']:sum(r.get('workplaceFeatureId')==f['id'] for r in pop['residents']) for f in features}
    for r in pop['residents']:
        if r.get('workplaceFeatureId') or resident_ids is not None and r['id'] not in resident_ids or r['role'] in ('child','elder'):continue
        candidates=[f['id'] for f in features if r['role'] in tags[f['id']]]
        # GM pp.68–69: saurians trade for metal tools. Newly generated artisans
        # work nonmetal materials at home; manual jobs and existing people stay.
        if generated and r['kin']=='saurian' and r['role']=='artisan':candidates=[]
        home=household[r['householdId']].get('homeFeatureId','')
        if candidates:
            fid=min(candidates,key=lambda f:(work_count[f],f));r['workplaceFeatureId']=fid;work_count[fid]+=1
        elif home:r['workplaceFeatureId']=home
        if generated and r.get('workplaceFeatureId'):
            generated_occupation(r,next(f for f in features if f['id']==r['workplaceFeatureId']))


def generate(room,m,data):
    existing=m.get('population') or {};has_people=bool(existing.get('residents') or existing.get('households'))
    append=data.get('append',False);replace=data.get('replace',False)
    if type(append)!=bool or type(replace)!=bool or append and replace:raise ValueError('Выберите добавление или явную замену жителей.')
    if has_people and not (append or replace):raise ValueError('Жители уже созданы. Выберите добавление или подтвердите замену списка.')
    count=data.get('count',default_count(room,m))
    if type(count)!=int or not 1<=count<=MAX_RESIDENTS:raise ValueError('Количество жителей: целое число от 1 до 400.')
    if append and len(existing.get('residents',[]))+count>MAX_RESIDENTS:raise ValueError('На карте можно сохранить до 400 жителей.')
    kin=choice(data.get('kin','mixed'),('mixed',*DATA['kins']),'народ')
    mode=choice(data.get('mode','mixed'),DATA['modes'],'способ заполнения')
    revealed=boolean(data.get('revealed',False))
    seed=text(data.get('seed',''),80) or secrets.token_hex(6)
    suffix='|append:'+','.join(r['id'] for r in existing.get('residents',[])) if append else ''
    rng=random.Random(int.from_bytes(hashlib.sha256((seed+suffix).encode()).digest(),'big'))
    pop=copy.deepcopy(existing) if append and existing else dict(generatorVersion=1,seed=seed,source=DATA['source'],households=[],residents=[])
    used_ids={x['id'] for field in ('households','residents') for x in pop.get(field,[])}
    used_names={h['name'].casefold() for h in pop.get('households',[])}
    def identifier(prefix):
        while True:
            value=prefix+format(rng.getrandbits(80),'020x')
            if value not in used_ids:used_ids.add(value);return value
    new_houses=set();new_people=set();made=0;index=0
    while made<count:
        family=mode in ('mixed','families')
        number=min(count-made,rng.randint(2,6) if family else rng.randint(1,5))
        kin_id=rng.choice(tuple(DATA['kins'])) if kin=='mixed' else kin
        family=family and kin_id not in COMMUNITY_KINS
        origin=DATA['kins'][kin_id];hid=identifier('h');new_houses.add(hid)
        if len(pop['households'])>=MAX_RESIDENTS:raise ValueError('На карте уже 400 семей или домов.')
        base_name=('Семья ' if family else 'Дом ')+rng.choice(origin['familyNames'])
        house_name=base_name;numbered=2
        while house_name.casefold() in used_names:
            house_name=f'{base_name} · {numbered}';numbered+=1
        used_names.add(house_name.casefold())
        h=dict(id=hid,name=house_name,homeFeatureId='',note='',gmNote='',revealed=revealed)
        pop['households'].append(h)
        names=rng.sample(origin['names'],number)
        head_role=({'guards':'guard','artisans':'artisan','rulers':'ruler'}.get(mode)
                   or (('ruler','guard','artisan','merchant','priest','innkeeper')[index] if mode=='mixed' and index<6 else rng.choice(COMMON_ROLES)))
        for member in range(number):
            age='adult';relation='member';role=head_role
            if family:
                relation='parent' if member==0 else 'partner' if member==1 else 'child' if member<number-1 or rng.random()<.65 else 'relative'
                if relation=='child':age='child';role='child'
                elif relation=='relative':age='old';role='elder'
                elif member:role=rng.choice(COMMON_ROLES)
                elif rng.random()<.2:age='old'
            else:age='adult' if kin_id in COMMUNITY_KINS else rng.choice(('young','adult','adult','old'))
            rid=identifier('r');new_people.add(rid)
            pop['residents'].append(dict(id=rid,name=names[member],kin=kin_id,ageGroup=age,householdId=hid,
                familyRole=relation,role=role,occupation=rng.choice(SAURIAN_CRAFTS if kin_id=='saurian' and role=='artisan' else DATA['roles'][role]['occupations']),workplaceFeatureId='',
                description=rng.choice(TRAITS),gmNote=rng.choice(MOTIVES),revealed=revealed))
            made+=1
        index+=1
    # Never retain a public-view marker on private stored data.
    pop.pop('public',None);m['population']=pop
    assign(m,new_houses,new_people,generated=True)


def household_save(m,raw):
    if not isinstance(raw,dict):raise ValueError('Нужны параметры семьи.')
    pop=population(m);hid=raw.get('id','')
    if not isinstance(hid,str):raise ValueError('Некорректная семья.')
    old=next((h for h in pop['households'] if h['id']==hid),None)
    if hid and not old:raise ValueError('Семья уже удалена. Обновите список.')
    if not old and len(pop['households'])>=MAX_RESIDENTS:raise ValueError('На карте уже 400 семей или домов.')
    values={**(old or {}),**raw};name=text(values.get('name','Новый дом'),80)
    if not name:raise ValueError('Укажите название семьи или дома.')
    saved=dict(id=hid or secrets.token_hex(10),name=name,homeFeatureId=feature_ref(m,values.get('homeFeatureId',''),True),
               note=text(values.get('note','')),gmNote=text(values.get('gmNote','')),revealed=boolean(values.get('revealed',False)))
    pop['households']=[h for h in pop['households'] if h['id']!=saved['id']]+[saved]
    return saved


def resident_save(m,raw):
    if not isinstance(raw,dict):raise ValueError('Нужны параметры жителя.')
    pop=population(m);rid=raw.get('id','')
    if not isinstance(rid,str):raise ValueError('Некорректный житель.')
    old=next((r for r in pop['residents'] if r['id']==rid),None)
    if rid and not old:raise ValueError('Житель уже удалён. Обновите список.')
    if not old and len(pop['residents'])>=MAX_RESIDENTS:raise ValueError('На карте можно сохранить до 400 жителей.')
    values={**(old or {}),**raw};name=text(values.get('name',''),60)
    if not name:raise ValueError('Укажите имя жителя.')
    hid=text(values.get('householdId',''),80)
    if hid and not any(h['id']==hid for h in pop['households']):raise ValueError('Семья не найдена на этой карте.')
    role=choice(values.get('role','laborer'),DATA['roles'],'занятие')
    saved=dict(id=rid or secrets.token_hex(10),name=name,kin=choice(values.get('kin','human'),DATA['kins'],'народ'),
               ageGroup=choice(values.get('ageGroup','adult'),DATA['ageGroups'],'возраст'),
               householdId=hid,familyRole=choice(values.get('familyRole','member'),DATA['familyRoles'],'положение в семье'),
               role=role,occupation=text(values.get('occupation',DATA['roles'][role]['label']),80),
               workplaceFeatureId=feature_ref(m,values.get('workplaceFeatureId','')),
               description=text(values.get('description','')),gmNote=text(values.get('gmNote','')),
               revealed=boolean(values.get('revealed',False)))
    if not hid:
        home=household_save(m,dict(name='Дом '+name,revealed=saved['revealed']))
        saved['householdId']=home['id']
    pop['residents']=[r for r in pop['residents'] if r['id']!=saved['id']]+[saved]


def apply(room,m,data):
    action=data['action']
    if action=='locationMapPopulationGenerate':generate(room,m,data)
    elif action=='locationMapResidentSave':resident_save(m,data.get('resident'))
    elif action=='locationMapHouseholdSave':household_save(m,data.get('household'))
    elif action=='locationMapResidentDelete':
        if data.get('confirmed') is not True:raise ValueError('Подтвердите удаление жителя.')
        pop=population(m);rid=data.get('resident')
        if not any(r['id']==rid for r in pop['residents']):raise ValueError('Житель уже удалён.')
        pop['residents']=[r for r in pop['residents'] if r['id']!=rid]
    elif action=='locationMapPopulationAssign':assign(m)
    elif action=='locationMapPopulationReveal':
        shown=boolean(data.get('revealed'));pop=population(m)
        for field in ('households','residents'):
            for entry in pop[field]:entry['revealed']=shown
    else:raise ValueError('Неизвестное действие с жителями.')


def public_population(pop,visible_features):
    """Explicit allowlists protect state, player preview and exported plans."""
    if not isinstance(pop,dict):return None
    public=pop.get('public') is True
    def shown(entry):return entry.get('revealed') is True or public and entry.get('revealed') is not False
    houses={h['id']:h for h in pop.get('households',[]) if shown(h)
            and (not h.get('homeFeatureId') or h['homeFeatureId'] in visible_features)}
    residents=[]
    for r in pop.get('residents',[]):
        if not shown(r) or r.get('householdId') not in houses:continue
        if r.get('workplaceFeatureId') and r['workplaceFeatureId'] not in visible_features:continue
        residents.append({key:r[key] for key in PERSON_PUBLIC if key in r})
    used={r['householdId'] for r in residents}
    return dict(generatorVersion=1,public=True,households=[{key:h[key] for key in HOUSE_PUBLIC if key in h} for hid,h in houses.items() if hid in used],residents=residents)
