"""PHB 66,111–112: timed cold exposure with explicit GM adjudication of death."""
import copy
import secrets
from dice_events import publish, pools
from dice_pools import skill_counts, result_text
from equipment_rules import owned, bonus, artifact
from risk_rules import push, score, can_push,can_push_character,repeat_push
import injuries


def die(sides=6):return secrets.randbelow(sides)+1
def exposure(c):return c.get('runtime',{}).get('coldExposure')
def protected(c):return any(e.get('kind')=='fireproof' for e in c.get('runtime',{}).get('magicEffects',[]))
def due(room,c):return bool(exposure(c) and not protected(c) and not c.get('runtime',{}).get('dead') and injuries.now(room)>=exposure(c)['nextAt'])
def fatal_due(room,c):return due(room,c) and c['runtime'].get('conditions',{}).get('cold',False) and injuries.current(c)['str']<=0
def overdue(room):return any(due(room,c) for c in room.get('characters',[]) if c['kind']!='monster')
def forest(c):
    sheet=c['sheet'];rank=max(sheet.get('paths',{}).get('forest',0),sheet.get('pathRank',0) if sheet.get('path')=='forest' else 0)
    return c['kind']=='pc' and rank>=2 and c['runtime'].get('wp',0)>=1
def note(data):
    value=data.get('note','')
    if not isinstance(value,str) or not value.strip() or len(value)>500:raise ValueError('Опишите условия или решение Мастера (до 500 символов).')
    return value.strip()
def log(room,c,message):room['log'].append(dict(name='Холод',text=f'{c["name"]}: {message}',private=bool(c.get('hidden'))))


def announce(room,c,p):
    r=p['roll'];positive,negative=score(r)
    r['pushAvailable']=bool(not r['hits'] and can_push_character(c,r))
    p['canForest']=bool(not r['hits'] and forest(c))
    result=result_text(positive,negative)
    if r['pushed']:result+=f' Риск: Телосложение −{r["damage"]}, износ −{r["wear"]}.'
    result+=' Примите результат; последствия холода применяются после решения.'
    p['diceEvent']=publish(room,c['name'],'Стойкость · холод',pools(r),result,p['private'],risk=dict(action='cold',character=c['id'],roll=p['id'],attribute=r['attribute']))


def apply(room,s,data):
    op=data.get('op');gm=s['role']=='gm'
    c=injuries.character(room,data.get('character'));rt=c['runtime'];cur=injuries.current(c)
    if not injuries.controls(c,s):raise PermissionError('Проверку выполняет владелец персонажа или Мастер.')
    e=exposure(c);p=room.get('coldCheck')
    if op=='configure':
        if not gm:raise PermissionError('Условия холода задаёт Мастер.')
        if p:raise ValueError('Сначала завершите текущую проверку холода.')
        if e and data.get('exposure')!=e['id'] or not e and data.get('exposure'):raise ValueError('Условия холода изменились. Откройте актуальную карточку.')
        if rt.get('dead'):raise ValueError('Умерший персонаж не проходит проверки холода.')
        hours=data.get('intervalHours');modifier=data.get('modifier',0);description=note(data)
        if type(hours)!=int or not 1<=hours<=24 or type(modifier)!=int or not -10<=modifier<=10:raise ValueError('Интервал: 1–24 часа; модификатор: от −10 до +10.')
        item=data.get('item','')
        if item and not any(i['id']==item for i in owned(room,c['id'])):raise ValueError('Защитный предмет должен находиться у персонажа.')
        rt['coldExposure']=dict(id=e['id'] if e else secrets.token_hex(12),intervalMinutes=hours*60,nextAt=e['nextAt'] if e else injuries.now(room),note=description,item=item,modifier=modifier)
        log(room,c,(f'условия уточнены без переноса ближайшей проверки, далее каждые {hours} ч. ' if e else f'назначена первая проверка холода сейчас, далее каждые {hours} ч. ')+description)
        return
    if not e:raise ValueError('Воздействие холода уже завершено.')
    if op in ('warm','confirmDeath'):
        if not gm:raise PermissionError('Согревание и смертельный исход подтверждает Мастер.')
        if p:raise ValueError('Сначала завершите бросок холода.')
        if data.get('exposure')!=e['id'] or data.get('confirmed') is not True:raise ValueError('Подтвердите актуальное решение Мастера.')
        description=note(data)
        if op=='confirmDeath':
            if not fatal_due(room,c):raise ValueError('Смертельный срок холода ещё не наступил.')
            rt['dead']=True;rt.pop('meditation',None)
            result='смерть от холода подтверждена Мастером.'
        else:
            rt.setdefault('conditions',{})['cold']=False
            result='согревание подтверждено; запрет восстановления от холода снят. Характеристики не восстанавливаются автоматически.'
        rt.pop('coldExposure');rt['coldLast']=dict(time=injuries.now(room),result=result,note=description)
        log(room,c,result+' '+description);injuries.sync_battle(room,c)
        from campaign_rules import try_cycle
        try_cycle(room)
        return
    if op=='roll':
        if p:raise ValueError('Сначала завершите предыдущую проверку холода.')
        if data.get('exposure')!=e['id'] or not due(room,c):raise ValueError('Эта проверка холода ещё не наступила или уже выполнена.')
        if fatal_due(room,c):raise ValueError('Телосложение сломлено при переохлаждении: Мастер должен подтвердить смертельный исход или своевременное согревание.')
        if cur['str']<=0:raise ValueError('Телосложение сломлено; разрешите состояние персонажа перед проверкой.')
        if room.get('combat',{}).get('pendingRisk') or room.get('treatment') or room.get('journeyRisk') or room.get('waterCheck'):
            raise ValueError('Сначала завершите текущий бросок боя, лечения или путешествия.')
        if any(i.get('repair',{}).get('status')=='rolled' for i in room.get('items',[])):raise ValueError('Сначала завершите ремонт.')
        tool=next((i for i in owned(room,c['id']) if i['id']==e['item']),None)
        if e['item'] and (not tool or tool.get('quantity')!=1 or tool.get('bonus',0) and not bonus(tool)):raise ValueError('Указанный защитный предмет недоступен или сломан. Мастер должен уточнить условия холода.')
        import kin_checks
        from skill_checks import ATTRS
        skill=kin_checks.adaptation(c,data,'endure');attr=ATTRS[skill]
        count,penalties=skill_counts(c['sheet']['skills'].get(skill,0),e['modifier'],injuries.modifiers(c,skill,attr))
        sides=artifact(tool) if tool else 0
        r=dict(id=secrets.token_hex(12),base=[die() for _ in range(cur[attr])],skillDice=[die() for _ in range(count)],gear=[die() for _ in range(bonus(tool) if tool else 0)],penalty=[die() for _ in range(penalties)],artifacts=[dict(sides=sides,value=die(sides))] if sides else [],pushed=False,skill=skill,originalSkill='endure',attribute=attr)
        p=dict(id=r['id'],character=c['id'],exposure=e['id'],roll=r,private=bool(c.get('hidden')),item=e['item'],signature=injuries.signature(c,tool))
        room['coldCheck']=p;announce(room,c,p)
        return
    if op not in ('push','accept','forest') or not p or p['id']!=data.get('roll') or p['character']!=c['id'] or p['exposure']!=e['id']:
        raise ValueError('Бросок холода уже завершён или изменился.')
    r=p['roll'];tool=next((i for i in owned(room,c['id']) if i['id']==p['item']),None)
    if op in ('push','forest'):
        if p['signature']!=injuries.signature(c,tool) or p['item'] and not tool:raise ValueError('Персонаж или предмет изменился после броска. Примите исходный результат.')
        if op=='forest':
            if r['hits'] or not forest(c):raise ValueError('Нужен провал, Путь леса 2 и 1 СВ героя.')
            rt['wp']-=1;r['hits']=1;r['forest']=True
        else:
            if not r.get('pushAvailable'):raise ValueError('Пойти на риск в этой проверке уже нельзя.')
            repeat_push(c,r,data);damage,wear=push(r,die);cur[r['attribute']]=max(0,cur[r['attribute']]-damage)
            if c['kind']=='pc':rt['wp']=min(10,rt.get('wp',0)+damage)
            if tool and wear:tool['wear']=min(tool['bonus'],tool.get('wear',0)+wear);tool['version']+=1
            p['signature']=injuries.signature(c,tool);announce(room,c,p)
            injuries.sync_battle(room,c)
            return
    from check_abilities import close_request
    close_request(c,r['id'])
    success=r['hits']>0
    if not success:
        rt.setdefault('conditions',{})['cold']=True;cur['str']=max(0,cur['str']-1);cur['wit']=max(0,cur['wit']-1)
    e['nextAt']+=e['intervalMinutes']
    result=('Путь леса: успех за 1 СВ.' if r.get('forest') else 'Проверка холода успешна.') if success else 'Переохлаждение: Телосложение −1, Разум −1.'
    rt['coldLast']=dict(time=injuries.now(room),result=result,hits=r['hits'],diceEvent=p['diceEvent'])
    # Preserve the rolled numbers and final outcome; no second random roll.
    event=next((x for x in room.get('diceRolls',[]) if x['id']==p['diceEvent']),None)
    if event:event['result']+=' '+result;event.pop('risk',None)
    log(room,c,result);room.pop('coldCheck');injuries.sync_battle(room,c)
    from campaign_rules import try_cycle
    try_cycle(room)


def project(room,s):
    targets=[]
    room['coldWaiting']=any(c.get('hidden') and c['kind']!='monster' and due(room,c) for c in room['characters'])
    for c in room['characters']:
        if c['kind']=='monster' or c.get('hidden') and s['role']!='gm':continue
        e=exposure(c)
        if not e:continue
        e['due']=due(room,c);e['fatalDue']=fatal_due(room,c)
        e['protected']=protected(c)
        visible={k:copy.deepcopy(v) for k,v in e.items() if k!='item'}
        targets.append(dict(id=c['id'],name=c['name'],owner=c['owner'],kind=c['kind'],cold=bool(c['runtime'].get('conditions',{}).get('cold')),dead=bool(c['runtime'].get('dead')),exposure=visible))
    room['coldTargets']=targets
    p=room.get('coldCheck')
    if p:
        p.pop('signature',None)
        if p['private'] and s['role']!='gm':room['coldCheck']=dict(waiting=True)
