"""Server-owned skill pools and one optional push, PH chapter 3."""
import json
import secrets
from inventory_rules import character, editable, ensure, number, text
from equipment_rules import owned, bonus, artifact

ATTRS=dict(melee='str',might='str',craft='str',endure='str',sleight='agi',shoot='agi',move='agi',stealth='agi',survive='wit',lore='wit',insight='wit',scout='wit',influence='emp',animal='emp',perform='emp',heal='emp')
def die(sides=6):return secrets.randbelow(sides)+1
def successes(value):return max(0,value//2-2) if value>=6 else 0
def signature(c,item):return json.dumps([c['sheet'],c['runtime']['current'],c['runtime'].get('wp',0),item.get('version') if item else None],sort_keys=True)
def count(r):return max(0,r['base'].count(6)+r['gear'].count(6)+r['skillDice'].count(6)*(-1 if r['negative'] else 1)+sum(successes(v) for v in r['artifact']))

def apply(room,s,data):
    c=character(room,data.get('character'));editable(room,dict(kind='character',id=c['id']),s);ensure(room,c['id'])
    rt=c['runtime']
    if data['action']=='characterRoll':
        if data.get('revision')!=room['revision']:raise ValueError('Состояние изменилось. Проверьте состав броска и повторите.')
        skill=data.get('skill');mod=data.get('modifier',0)
        if skill not in ATTRS or type(mod)!=int or not -10<=mod<=10:raise ValueError('Проверьте навык и модификатор.')
        iid=data.get('item','');item=next((i for i in owned(room,c['id']) if i['id']==iid),None)
        if iid and (not item or item['version']!=data.get('itemVersion')):raise ValueError('Предмет недоступен или изменён.')
        if item and item['bonus']>0 and bonus(item)==0:raise ValueError('Предмет сломан. Сначала нужен ремонт.')
        note=text(data.get('note',''),300)
        attr=ATTRS[skill];base=rt['current'][attr];skill_value=c['sheet']['skills'].get(skill,0);adjusted=skill_value+mod
        if base<=0:raise ValueError('Персонаж сломлен по этой характеристике.')
        gear=bonus(item) if item else 0;sides=artifact(item) if item else 0
        r=dict(id=secrets.token_hex(8),skill=skill,attribute=attr,note=note,item=iid,itemName=item['name'] if item else '',base=[die() for _ in range(base)],skillDice=[die() for _ in range(abs(adjusted))],gear=[die() for _ in range(gear)],negative=adjusted<0,artifact=[die(sides)] if sides else [],sides=sides,pushed=False,formula=dict(base=base,skill=skill_value,modifier=mod,gear=gear))
        r['signature']=signature(c,item);rt['lastCheck']=r
    else:
        r=rt.get('lastCheck')
        if not r or r['id']!=data.get('roll') or r['pushed']:raise ValueError('Этот бросок уже форсирован или устарел.')
        item=next((i for i in owned(room,c['id']) if i['id']==r['item']),None)
        if r['signature']!=signature(c,item) or r['item'] and not item:raise ValueError('Герой или предмет изменился после броска. Форсирование недоступно.')
        for key in ('base','skillDice','gear'):
            r[key]=[die() if v!=6 and (key=='skillDice' or v!=1) else v for v in r[key]]
        r['artifact']=[die(r['sides']) if v<6 else v for v in r['artifact']]
        damage=r['base'].count(1);wear=r['gear'].count(1)
        rt['current'][r['attribute']]=max(0,rt['current'][r['attribute']]-damage)
        if c['kind']=='pc':rt['wp']=min(10,rt.get('wp',0)+damage)
        if item and wear:item['wear']=item.get('wear',0)+wear;item['version']+=1
        r.update(pushed=True,damage=damage,wear=wear)
    r['hits']=count(r)
    f=r['formula'];message=f"{c['name']}: {r['skill']} — {f['base']} + {f['skill']} + мод. {f['modifier']} + предмет {f['gear']}"
    if r['sides']:message+=f" + D{r['sides']}"
    message+=f". Кости: база {r['base']}, навык {r['skillDice']}, предмет {r['gear']}, артефакт {r['artifact']}. Успехов: {r['hits']}."
    if r['pushed']:message+=f" Форсирование: урон {r['damage']}, износ {r['wear']}."
    if r['note']:message+=' '+r['note']
    if not c.get('hidden'):room['log'].append(dict(name=s['name'],text=message))
    room['journey']['gmReady']=False
