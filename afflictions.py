"""PHB 113–115: poison resistance, disease onset/daily care and antidotes."""
import copy
import secrets
import injuries
from dice_events import publish,pools,group
from dice_pools import skill_counts
from equipment_rules import owned,bonus,artifact
from risk_rules import score

POISONS={'lethal':('Смертельный яд','str'),'paralytic':('Парализующий яд','agi'),'sleep':('Снотворный яд','wit'),'hallucinogenic':('Галлюциногенный яд','emp')}
ACTIVE=('exposed','incubating','daily','poisoning','sleeping')

def die(sides=6):return secrets.randbelow(sides)+1
def active(c):return [a for a in c.get('runtime',{}).get('afflictions',[]) if a['phase'] in ACTIVE]
def due(room,a):return a.get('nextAt') is not None and injuries.now(room)>=a['nextAt']
def overdue(room):return any(due(room,a) or a.get('deathAt') is not None and injuries.now(room)>=a['deathAt'] for c in room['characters'] if c['kind']!='monster' and not c.get('runtime',{}).get('dead') for a in active(c))
def sick(c):return any(a['kind']=='disease' and a['phase'] in ('incubating','daily') for a in active(c))
def sleeping(c):return any(a['phase']=='sleeping' for a in active(c))
def log(room,c,message):room['log'].append(dict(name='Болезни и яды',text=f'{c["name"]}: {message}',private=bool(c.get('hidden'))))
def note(data):
    value=data.get('note','')
    if not isinstance(value,str) or not value.strip() or len(value)>1000:raise ValueError('Опишите основание решения (до 1000 символов).')
    return value.strip()
def find(c,aid):
    a=next((a for a in active(c) if a['id']==aid),None)
    if not a:raise ValueError('Это воздействие уже завершено или изменилось.')
    return a
def other_pending(room):
    return any(room.get(k) for k in ('coldCheck','waterCheck','treatment','journeyRisk','expeditionCheck')) or bool(room.get('combat',{}).get('pendingRisk')) or any(i.get('repair',{}).get('status')=='rolled' for i in room.get('items',[]))
def mark_sick(c):c['runtime'].setdefault('conditions',{})['sick']=sick(c)
def disease_damage(room,c,a,at):
    cur=injuries.current(c)
    for attr in ('str','agi'):cur[attr]=max(0,cur[attr]-1)
    if cur['str']<=0 and a.get('deathAt') is None:a['deathAt']=round(at+1440,4)
    a['phase']='daily';a['nextAt']=round(at+1440,4)
    return 'Болезнь: Телосложение −1, Ловкость −1.'
def poison_damage(room,c,a,at):
    attr=POISONS[a['type']][1];cur=injuries.current(c);cur[attr]=max(0,cur[attr]-1)
    result=f'{POISONS[a["type"]][0]}: {injuries.NAMES[attr]} −1.'
    if cur[attr]<=0:
        a.update(phase='resolved',nextAt=None)
        if a['type']=='lethal':
            injuries.pending_injury(room,c,'str','other','poison')
            result+=' Телосложение сломлено: определите нетипичную критическую травму.'
        elif a['type']=='sleep':
            duration=die();a.update(phase='sleeping',nextAt=round(at+duration*60,4),sleepHours=duration)
            publish(room,c['name'],'Снотворный яд · сон',[group('table',[duration])],f'Бессознательное состояние: {duration} игровых ч.',bool(c.get('hidden')))
            result+=f' Герой без сознания {duration} ч.; критической травмы нет.'
    else:a.update(phase='poisoning',nextAt=round(at+room.get('medicalRoundSeconds',10)/60,4))
    return result

def apply(room,s,data):
    op=data.get('op');gm=s['role']=='gm';c=injuries.character(room,data.get('character'));rt=c['runtime']
    if c.get('hidden') and not gm:raise PermissionError('Этот персонаж недоступен.')
    p=room.get('afflictionCheck')
    if op=='configure':
        if not gm:raise PermissionError('Воздействие назначает Мастер.')
        if p or other_pending(room):raise ValueError('Сначала завершите текущую проверку.')
        kind=data.get('kind');typ=data.get('type','lethal');power=data.get('potency',3);description=note(data)
        if kind not in ('poison','disease') or kind=='poison' and typ not in POISONS or type(power)!=int or not 1<=power<=30:raise ValueError('Укажите вид воздействия и силу от 1 до 30.')
        if rt.get('dead'):raise ValueError('Умершему не назначают новую проверку.')
        name=data.get('name') or (POISONS[typ][0] if kind=='poison' else 'Болезнь')
        if not isinstance(name,str) or len(name)>100:raise ValueError('Название: до 100 символов.')
        a=dict(id=secrets.token_hex(12),kind=kind,type=typ if kind=='poison' else '',name=name,potency=power,note=description,phase='exposed',nextAt=injuries.now(room),created=injuries.now(room))
        rt.setdefault('afflictions',[]).append(a);log(room,c,f'{name}: требуется проверка сопротивления (сила {power}).');return
    a=find(c,data.get('affliction')) if op not in ('accept','push') else None
    if op in ('antidote','cure','confirmDeath','tick','advance'):
        if not gm:raise PermissionError('Последствия и помощь подтверждает Мастер.')
        if p or other_pending(room):raise ValueError('Сначала завершите текущую проверку.')
        if op in ('tick','advance'):
            if data.get('nextAt')!=a.get('nextAt'):raise ValueError('Этот срок уже изменился.')
            if op=='advance':
                if room.get('combat',{}).get('phase') in ('setup','combat'):raise ValueError('В бою время идёт при смене раунда.')
                future=[x[key] for who in room['characters'] if who['kind']!='monster' and not who.get('runtime',{}).get('dead') for x in active(who) for key in ('nextAt','deathAt') if x.get(key) is not None]
                for who in room['characters']:
                    for key in ('coldExposure','waterExposure'):
                        if who.get('runtime',{}).get(key):future.append(who['runtime'][key]['nextAt'])
                target=min(future)
                if target<=injuries.now(room):raise ValueError('Сначала разрешите уже наступивший срок.')
                injuries.advance(room,target-injuries.now(room));return
            if not due(room,a):raise ValueError('Срок последствий ещё не наступил.')
            if a.get('deathAt') is not None and injuries.now(room)>=a['deathAt']:raise ValueError('Смертельный срок истёк: Мастер должен разрешить исход или помощь.')
            if a['phase']=='incubating':result=disease_damage(room,c,a,a['nextAt'])
            elif a['phase']=='poisoning':result=poison_damage(room,c,a,a['nextAt'])
            elif a['phase']=='sleeping':a.update(phase='resolved',nextAt=None);result='Срок сна от яда завершён. Характеристики восстанавливаются отдельно.'
            else:raise ValueError('На этом этапе нужна проверка сопротивления.')
        else:
            if data.get('confirmed') is not True:raise ValueError('Подтвердите помощь или необратимый исход.')
            reason=note(data)
            if op=='confirmDeath':
                if a.get('deathAt') is None or injuries.now(room)<a['deathAt']:raise ValueError('Смертельный срок ещё не наступил.')
                rt['dead']=True;result='Гибель от болезни подтверждена Мастером. '+reason
            elif op=='antidote':
                if a['kind']!='poison':raise ValueError('Противоядие останавливает яд, а не болезнь.')
                result='Противоядие остановило воздействие; повреждения и критическая травма сохраняются. '+reason
            else:result='Излечение подтверждено Мастером; потерянные характеристики восстанавливаются отдельно. '+reason
            a.update(phase='resolved',nextAt=None,ended=injuries.now(room))
        a['lastResult']=result;mark_sick(c);log(room,c,result);injuries.sync_battle(room,c);return
    if op=='roll':
        if p or other_pending(room):raise ValueError('Сначала завершите предыдущую проверку.')
        if not due(room,a) or a['phase'] not in ('exposed','daily'):raise ValueError('Сначала разрешите наступление болезни или последствия яда.')
        if a.get('deathAt') is not None and injuries.now(room)>=a['deathAt']:raise ValueError('Смертельный срок требует решения Мастера.')
        caregiver=data.get('caregiver');actor=injuries.character(room,caregiver) if caregiver else c
        if not injuries.controls(actor,s):raise PermissionError('Проверку выполняет владелец бросающего персонажа или Мастер.')
        if caregiver and (a['kind']!='disease' or data.get('careConfirmed') is not True):raise ValueError('Целитель должен ухаживать за больным; подтвердите уход.')
        if caregiver:injuries.check_allowed(actor)
        skill='heal' if caregiver else 'endure';attr='emp' if caregiver else 'str'
        if not caregiver and injuries.current(c)['str']<=0:raise ValueError('Больному со сломленным Телосложением нужен ухаживающий целитель.')
        import kin_checks
        from skill_checks import ATTRS
        original=skill;skill=kin_checks.adaptation(actor,data,skill);attr=ATTRS[skill]
        item=next((i for i in owned(room,actor['id']) if i['id']==data.get('item')),None)
        if data.get('item') and (not item or item.get('quantity')!=1 or item.get('bonus',0) and not bonus(item)):raise ValueError('Предмет недоступен или сломан.')
        mod=data.get('modifier',0)
        if type(mod)!=int or not -10<=mod<=10 or mod and not gm:raise ValueError('Модификатор от −10 до +10 задаёт Мастер.')
        n,pen=skill_counts(actor['sheet']['skills'].get(skill,0),mod,injuries.modifiers(actor,skill,attr));sides=artifact(item) if item else 0
        r=dict(id=secrets.token_hex(12),base=[die() for _ in range(injuries.current(actor)[attr])],skillDice=[die() for _ in range(n)],gear=[die() for _ in range(bonus(item) if item else 0)],penalty=[die() for _ in range(pen)],artifacts=[dict(sides=sides,value=die(sides))] if sides else [],pushed=False,skill=skill,originalSkill=original,attribute=attr,pushAvailable=False,pushReason='Это защита во встречной проверке: защищающийся не идёт на риск.')
        score(r);enemy=[die() for _ in range(a['potency'])];opponent=enemy.count(6)
        p=dict(id=r['id'],character=actor['id'],target=c['id'],affliction=a['id'],roll=r,enemyDice=enemy,enemyHits=opponent,private=bool(c.get('hidden') or actor.get('hidden')),item=item['id'] if item else '',signature=injuries.signature(actor,item),owner=actor['owner'])
        room['afflictionCheck']=p;announce(room,actor,p,a);return
    if op=='push':raise ValueError('Защищающийся не идёт на риск во встречной проверке сопротивления.')
    if op!='accept' or not p or p['id']!=data.get('roll'):raise ValueError('Бросок сопротивления уже завершён.')
    actor=injuries.character(room,p['character'])
    if not injuries.controls(actor,s) or p['private'] and not gm:raise PermissionError('Результат принимает владелец бросавшего персонажа или Мастер.')
    c=injuries.character(room,p['target']);a=find(c,p['affliction']);r=p['roll'];success=r['hits']>=p['enemyHits'];at=a['nextAt']
    from check_abilities import close_request
    close_request(actor,r['id'])
    if a['kind']=='disease':
        if success:a.update(phase='resolved',nextAt=None,ended=injuries.now(room));result='Болезнь преодолена. Обычное восстановление снова доступно.'
        elif a['phase']=='exposed':
            a.update(phase='incubating',nextAt=round(at+1440,4));result='Заражение: болезнь проявится через сутки; Телосложение и Ловкость не восстанавливаются обычным способом.'
            if injuries.current(c)['str']<=0:a['deathAt']=round(at+1440,4)
        else:result=disease_damage(room,c,a,at)
    elif success:
        attr=POISONS[a['type']][1];cur=injuries.current(c);cur[attr]=max(0,cur[attr]-1);a.update(phase='resolved',nextAt=None)
        result=f'Ограниченное действие яда: {injuries.NAMES[attr]} −1.'
        if cur[attr]<=0 and a['type']=='lethal':injuries.pending_injury(room,c,'str','other','poison')
    else:result=poison_damage(room,c,a,at)
    a['lastResult']=result;a['lastRoll']=dict(hits=r['hits'],enemyHits=p['enemyHits'],event=p['diceEvent']);mark_sick(c)
    event=next((e for e in room['diceRolls'] if e['id']==p['diceEvent']),None)
    if event:event['result']+=' '+result;event.pop('risk',None)
    room.pop('afflictionCheck');log(room,c,result);injuries.sync_battle(room,c)

def announce(room,c,p,a):
    r=p['roll'];score(r);enemy=dict(kind='base',label='Сила яда' if a['kind']=='poison' else 'Заразность',sides=6,values=p['enemyDice'],negative=False)
    result=f'Сопротивление {r["hits"]} против {p["enemyHits"]}. Ничья в пользу сопротивления. Примите результат.'
    p['diceEvent']=publish(room,c['name'],a['name']+' · сопротивление',pools(r)+[enemy],result,p['private'],risk=dict(action='affliction',character=c['id'],roll=p['id'],attribute=r['attribute']))

def observe(room,before,data):
    for c in room['characters']:
        if c['kind']=='monster':continue
        for a in active(c):
            if a['kind']=='disease' and a['phase'] in ('incubating','daily') and injuries.current(c)['str']<=0 and a.get('deathAt') is None:
                a['deathAt']=round(injuries.now(room)+1440,4)

def project(room,s):
    targets=[];room['afflictionWaiting']=any(c.get('hidden') and due(room,a) for c in room['characters'] if c['kind']!='monster' for a in active(c))
    for c in room['characters']:
        if c['kind']=='monster' or c.get('hidden') and s['role']!='gm':continue
        for a in active(c):
            a['due']=due(room,a);a['fatalDue']=a.get('deathAt') is not None and injuries.now(room)>=a['deathAt']
            targets.append(dict(character=c['id'],name=c['name'],owner=c['owner'],kind=c['kind'],affliction=copy.deepcopy(a)))
    room['afflictionTargets']=targets
    if room.get('afflictionCheck'):
        room['afflictionCheck'].pop('signature',None)
        if room['afflictionCheck']['private'] and s['role']!='gm':room['afflictionCheck']=dict(waiting=True)
