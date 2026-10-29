"""Reviewed session XP, private self-reports and an immutable shared recap."""
import copy
import secrets
import time
from progression import award_character
from skill_checks import signature

QUESTIONS=('attendance','exploration','site','monster','treasure','stronghold','pride','secret','sacrifice','extraordinary')


def text(value,limit):
    if not isinstance(value,str) or len(value)>limit:raise ValueError(f'Текст должен быть не длиннее {limit} символов.')
    return value.strip()


def safe_to_finish(room):
    if room.get('combat',{}).get('phase') in ('setup','combat') or room['journey']['phase']=='resolving':raise ValueError('Перед итогами завершите бой и проверки текущей четверти.')
    if room.get('journeyRisk') or any(i.get('repair',{}).get('status')=='rolled' for i in room.get('items',[])) or any(not x.get('done') for x in room.get('opposedChecks',[])):
        raise ValueError('Сначала завершите ожидающие решения по броскам и встречные проверки.')
    for c in room['characters']:
        for check in (c.get('runtime',{}).get('lastCheck'),room.get('gmChecks',{}).get(c['id'])):
            if not check or check.get('pushed') or check.get('accepted'):continue
            item=next((i for i in room.get('items',[]) if i['id']==check.get('item') and i.get('location')==dict(kind='character',id=c['id'])),None)
            if check.get('item') and not item:continue
            if check.get('signature')==signature(c,item):raise ValueError(f"{c['name']}: завершите проверку в инвентаре — примите результат или пойдите на риск.")


def apply(room,s,data):
    op=data.get('operation');gm=s['role']=='gm';current=room.get('sessionRecap');t=room['journey']
    if op=='open':
        if not gm:raise PermissionError('Итоги встречи открывает Мастер.')
        safe_to_finish(room)
        if current and current['status']=='draft':raise ValueError('Обсуждение итогов уже открыто.')
        if any(r['session']==t['session'] for r in room.get('sessionHistory',[])):raise ValueError('Опыт за эту встречу уже начислен.')
        selected=data.get('characters')
        eligible={c['id']:c for c in room['characters'] if c['kind']=='pc' and not c.get('hidden')}
        if not isinstance(selected,list) or not selected or len(selected)>100 or any(not isinstance(cid,str) or cid not in eligible for cid in selected) or len(set(selected))!=len(selected):raise ValueError('Выберите участвовавших героев.')
        room['sessionRecap']=dict(id=secrets.token_hex(12),version=1,session=t['session'],status='draft',openedAt=time.time(),characters=[dict(id=cid,name=eligible[cid]['name'],owner=eligible[cid]['owner']) for cid in selected],answers={},summary='',loot='',next='',gmNote='',awards={})
        room['log'].append(dict(name=s['name'],text=f"Открыто обсуждение итогов встречи {t['session']}. Игроки отмечают достижения своих героев."))
        return
    if not current or current['status']!='draft' or data.get('recap')!=current['id']:raise ValueError('Это обсуждение уже завершено или заменено. Обновите итоги встречи.')
    if op!='cancel' and current['session']!=t['session']:raise ValueError('Номер встречи изменился. Мастер должен отменить устаревшее обсуждение.')
    if op=='answer':
        cid=data.get('character');entry=next((x for x in current['characters'] if x['id']==cid),None)
        c=next((x for x in room['characters'] if x['id']==cid),None)
        if not entry or not c or c.get('hidden') or not gm and c['owner']!=s['owner']:raise PermissionError('Отвечать можно только за своего героя.')
        old=current['answers'].get(cid,{})
        if type(data.get('version')) is not int or data['version']!=old.get('version',0):raise ValueError('Ответы героя уже изменились. Обновите окно.')
        answers=data.get('answers')
        if not isinstance(answers,dict) or set(answers)!=set(QUESTIONS) or any(type(v) is not bool for v in answers.values()):raise ValueError('Отметьте ответы на все вопросы итогов.')
        current['answers'][cid]=dict(answers=answers,note=text(data.get('note',''),2000),version=old.get('version',0)+1,by=s['owner'])
    else:
        if not gm:raise PermissionError('Общие итоги и начисления подтверждает Мастер.')
        if type(data.get('version')) is not int or data['version']!=current['version']:raise ValueError('Итоги изменились. Проверьте свежие ответы перед подтверждением.')
        if op=='cancel':
            room['sessionRecap']=None
            room['log'].append(dict(name=s['name'],text='Обсуждение итогов отменено; опыт не начислялся.'))
            return
        if op not in ('edit','finish'):raise ValueError('Неизвестное действие итогов.')
        for key,limit in (('summary',4000),('loot',2000),('next',2000),('gmNote',4000)):
            if key in data:current[key]=text(data[key],limit)
        if op=='finish':
            safe_to_finish(room)
            if data.get('confirmed') is not True:raise ValueError('Подтвердите начисление опыта и завершение встречи.')
            awards=data.get('awards')
            if not isinstance(awards,dict) or set(awards)!={x['id'] for x in current['characters']}:raise ValueError('Проверьте начисление каждому участнику.')
            staged=[];reviewed={}
            for entry in current['characters']:
                cid=entry['id'];row=awards[cid];answer=current['answers'].get(cid)
                if not isinstance(row,dict) or type(row.get('amount')) is not int or not 0<=row['amount']<=10:raise ValueError('За встречу начисляется от 0 до 10 опыта по десяти вопросам.')
                note=text(row.get('note',''),500)
                if (not answer or row['amount']!=sum(answer['answers'].values())) and len(note)<3:raise ValueError(f"{entry['name']}: поясните решение Мастера, если нет ответов или количество опыта изменено.")
                c=next((c for c in room['characters'] if c['id']==cid and c['kind']=='pc'),None)
                if not c:raise ValueError(f"{entry['name']}: персонаж больше недоступен; отмените итоги и выберите участников заново.")
                clone=copy.deepcopy(c);award_character(clone,row['amount']);staged.append((c,clone['sheet']))
                reviewed[cid]=dict(amount=row['amount'],note=note)
            for c,sheet in staged:c['sheet']=sheet
            current.update(status='finished',finishedAt=time.time(),awards=reviewed)
            t['session']+=1;t['gmReady']=False
            room['log'].append(dict(name=s['name'],text=f"Встреча {current['session']} завершена. Опыт: "+', '.join(f"{x['name']} +{reviewed[x['id']]['amount']}" for x in current['characters'])+f". Началась встреча {t['session']}."))
            # Root action saves a checkpoint in the same database transaction as the campaign.
            room['_sessionCheckpoint']=f"Итоги встречи {current['session']}"
    current['version']+=1
    if current['status']=='finished':room.setdefault('sessionHistory',[]).append(copy.deepcopy(current));room['sessionHistory']=room['sessionHistory'][-50:]


def public(room,s):
    """Only own answer details are public; GM notes and others' secrets stay private."""
    owners={c['id']:c['owner'] for c in room['characters']}
    current=room.get('sessionRecap')
    if current and current['status']=='draft':
        for c in current['characters']:c['owner']=owners.get(c['id'],c['owner'])
    if s['role']=='gm':return
    for recap in [room.get('sessionRecap'),*room.get('sessionHistory',[])]:
        if not recap:continue
        own={c['id'] for c in recap['characters'] if owners.get(c['id'],c['owner'])==s['owner']}
        recap.pop('gmNote',None)
        recap['submitted']=list(recap['answers'])
        recap['answers']={cid:answer for cid,answer in recap['answers'].items() if cid in own}
        recap['awards']={cid:({**award} if cid in own else dict(amount=award['amount'])) for cid,award in recap['awards'].items()}
