"""Server checks and one push, with the agreed separate-penalty table rule."""
import json
import secrets
import time
import injuries
import kin_checks
from dice_pools import skill_counts, result_text, artifact_sides
from dice_events import publish, pools, visibility
from inventory_rules import character, editable, ensure, number, text
from equipment_rules import owned, bonus, artifact

ATTRS=dict(melee='str',might='str',craft='str',endure='str',sleight='agi',shoot='agi',move='agi',stealth='agi',survive='wit',lore='wit',insight='wit',scout='wit',influence='emp',animal='emp',perform='emp',heal='emp')
def die(sides=6):return secrets.randbelow(sides)+1
def successes(value):return max(0,value//2-2) if value>=6 else 0
def signature(c,item):return json.dumps([c['sheet'],c['runtime']['current'],c['runtime'].get('wp',0),item.get('version') if item else None],sort_keys=True)
def artifact_successes(r):return sum(successes(v) for v in r['artifact'])+sum(successes(a['value']) for a in r.get('artifacts',[]))
def count(r):return max(0,r['base'].count(6)+r['gear'].count(6)+r['skillDice'].count(6)*(-1 if r['negative'] else 1)+artifact_successes(r)+r.get('kinSuccesses',0)-r.get('penalty',[]).count(6))

def apply(room,s,data,opposed=False):
    private=visibility(s,data)
    c=character(room,data.get('character'));editable(room,dict(kind='character',id=c['id']),s);ensure(room,c['id'])
    rt=c['runtime']
    if data['action']=='characterRoll':
        if not opposed and any(not p.get('done') and any(p[k]['character']==c['id'] for k in ('attacker','defender')) for p in room.get('opposedChecks',[])):raise ValueError('Сначала завершите или отмените встречную проверку этого персонажа.')
        if data.get('revision')!=room['revision']:raise ValueError('Состояние изменилось. Проверьте состав броска и повторите.')
        skill=data.get('skill');mod=data.get('modifier',0)
        if skill not in ATTRS or type(mod)!=int or not -10<=mod<=10:raise ValueError('Проверьте навык и модификатор.')
        injuries.check_allowed(c)
        original_skill=skill
        skill=kin_checks.adaptation(c,data,skill)
        injury_mod=injuries.modifiers(c,skill,ATTRS[skill])
        iid=data.get('item','');item=next((i for i in owned(room,c['id']) if i['id']==iid),None)
        if iid and (not item or item['version']!=data.get('itemVersion')):raise ValueError('Предмет недоступен или изменён.')
        if item and item['bonus']>0 and bonus(item)==0:raise ValueError('Предмет сломан. Сначала нужен ремонт.')
        note=text(data.get('note',''),300)
        attr=ATTRS[skill];base=rt['current'][attr];skill_value=c['sheet']['skills'].get(skill,0);skill_count,penalty_count=skill_counts(skill_value,mod,injury_mod)
        if base<=0:raise ValueError('Персонаж сломлен по этой характеристике.')
        gear=bonus(item) if item else 0;sides=artifact(item) if item else 0
        extras=artifact_sides(data)
        if len(extras)+bool(sides)>10:raise ValueError('Не более 10 артефактных костей вместе с костью выбранного предмета.')
        r=dict(id=secrets.token_hex(8),skill=skill,attribute=attr,note=note,item=iid,itemName=item['name'] if item else '',base=[die() for _ in range(base)],skillDice=[die() for _ in range(skill_count)],gear=[die() for _ in range(gear)],negative=False,penalty=[die() for _ in range(penalty_count)],poolRule='separate-penalties-v1',artifact=[die(sides)] if sides else [],sides=sides,pushed=False,formula=dict(base=base,skill=skill_value,modifier=mod,gear=gear))
        r['private']=private or bool(c.get('hidden'))
        r['originalSkill']=original_skill;r['injuryModifier']=injury_mod
        r['artifacts']=[dict(sides=n,value=die(n)) for n in extras]
        r['signature']=signature(c,item)
        if r['private']:room.setdefault('gmChecks',{})[c['id']]=r
        else:rt['lastCheck']=r
    else:
        r=rt.get('lastCheck')
        secret=room.get('gmChecks',{}).get(c['id']) if s['role']=='gm' else None
        if secret and secret['id']==data.get('roll'):r=secret
        repeat=bool(r and r.get('pushed') and c['kind']=='pc' and c['sheet']['kin']=='dwarf' and data.get('kinRepeat') is True)
        if not r or r['id']!=data.get('roll') or (r['pushed'] and not repeat and data['action']!='characterAccept') or r.get('accepted'):raise ValueError('Этот бросок уже форсирован или устарел.')
        if r.get('opposed') and not opposed:raise ValueError('Завершите бросок через встречную проверку; защитник не может идти на риск.')
        item=next((i for i in owned(room,c['id']) if i['id']==r['item']),None)
        if r['signature']!=signature(c,item) or r['item'] and not item:raise ValueError('Герой или предмет изменился после броска. Форсирование недоступно.')
        if data['action']=='characterAccept':
            r['accepted']=True
            return
        injuries.check_allowed(c)
        if repeat:
            if type(data.get('kinAttempt'))!=int or data['kinAttempt']!=r.get('kinPushes',0):raise ValueError('Повторный риск уже выполнен. Проверьте новые кости перед следующим решением.')
            if rt.get('wp',0)<1:raise ValueError('Для повторного риска дварфу нужна 1 СВ.')
            from risk_rules import can_push
            if not can_push(r):raise ValueError('Нет костей для повторного броска.')
            rt['wp']-=1;r['kinPushes']=r.get('kinPushes',0)+1
        r.setdefault('penalty',[])
        r['held']={key:[v==6 or key not in ('skillDice','penalty') and v==1 for v in r[key]] for key in ('base','skillDice','gear','penalty')}
        r['held']['artifact']=[v>=6 for v in r['artifact']]
        for key in ('base','skillDice','gear','penalty'):
            r[key]=[die() if v!=6 and (key in ('skillDice','penalty') or v!=1) else v for v in r[key]]
        r['artifact']=[die(r['sides']) if v<6 else v for v in r['artifact']]
        for a in r.get('artifacts',[]):
            a['held']=a['value']>=6
            if not a['held']:a['value']=die(a['sides'])
        damage=r['base'].count(1);wear=r['gear'].count(1)
        rt['current'][r['attribute']]=max(0,rt['current'][r['attribute']]-damage)
        if c['kind']=='pc':rt['wp']=min(10,rt.get('wp',0)+damage)
        if item and wear:item['wear']=item.get('wear',0)+wear;item['version']+=1
        r.update(pushed=True,damage=damage,wear=wear)
        r['signature']=signature(c,item)
    r['time']=time.time()
    r['hits']=count(r)
    penalty_hits=r.get('penalty',[]).count(6)
    positive_hits=r['base'].count(6)+r['gear'].count(6)+r['skillDice'].count(6)*(-1 if r['negative'] else 1)+artifact_successes(r)+r.get('kinSuccesses',0)
    result=result_text(positive_hits,penalty_hits) if not r['negative'] else f"Успехов: {r['hits']}."
    f=r['formula'];message=f"{c['name']}: {r['skill']} — {f['base']} + {f['skill']} + мод. {f['modifier']} + предмет {f['gear']}"
    if r.get('injuryModifier'):message+=f" + травмы {r['injuryModifier']}"
    if r['sides']:message+=f" + D{r['sides']}"
    if r.get('artifacts'):message+=' + '+', '.join(f"D{a['sides']} [{a['value']}]" for a in r['artifacts'])
    message+=f". Кости: база {r['base']}, навык {r['skillDice']}, предмет {r['gear']}, штраф {r.get('penalty',[])}, артефакт {r['artifact']}. {result}"
    if r['pushed']:result+=f" Риск: {r['attribute']} −{r['damage']}, износ −{r['wear']}."
    if r['pushed']:message+=f" Форсирование: урон {r['damage']}, износ {r['wear']}."
    if r['note']:message+=' '+r['note']
    extra_push=r['pushed'] and c['kind']=='pc' and c['sheet']['kin']=='dwarf'
    r['diceEvent']=publish(room,c['name'],'Пойти на риск' if r['pushed'] else 'Проверка навыка',pools(r),result,r.get('private',False),message,risk=dict(action='character',character=c['id'],roll=r['id'],attribute=r['attribute']) if not r['pushed'] or extra_push else None)
    if data['action']=='characterRoll':
        injuries.check_pain(room,c,r['skill'])
        r['signature']=signature(c,item)
    room['journey']['gmReady']=False
