"""Server-authorized skill growth; creation sheets cannot forge XP or paid levels."""
import copy
import functools
import json
import subprocess
from pathlib import Path
from sheet_validation import validate_sheet

TEXT_FIELDS = {'name','appearance','pride','secret','relationships','notes'}
SKILLS = ('melee','might','craft','endure','sleight','shoot','move','stealth',
          'survive','lore','insight','scout','influence','animal','perform','heal')

NAMES=dict(zip(SKILLS,('Ближний бой','Мощь','Ремесло','Стойкость','Ловкость рук','Меткость','Проворство','Скрытность','Выживание','Знания','Проницательность','Разведка','Влияние','Дрессировка','Исполнение','Лечение')))


@functools.lru_cache(maxsize=1)
def catalog():
    """Use the same catalog as import validation; no second set of talent IDs."""
    result=subprocess.run(['node','--input-type=module','-e',"import {GENERAL,PROFESSIONS,paths} from './public/tools/rules.js';console.log(JSON.stringify({general:GENERAL,paths:Object.fromEntries(Object.keys(PROFESSIONS).flatMap(profession=>['core','bitter'].map(expansion=>[profession+':'+expansion,paths({profession,expansion})])))}));"],cwd=Path(__file__).parent,capture_output=True,text=True,encoding='utf-8',timeout=8)
    if result.returncode:raise ValueError('Не удалось загрузить правила развития.')
    return json.loads(result.stdout)


def initialize(sheet):
    p=sheet.get('progression')
    if not p:
        p=sheet['progression']=dict(version=1,revision=0,baseSkills=copy.deepcopy(sheet['skills']),earned=0,spent=0,restCycle=None,training={})
    if p['version']==1:
        p.update(version=2,baseTalents=copy.deepcopy(sheet['talents']),basePaths={sheet['path']:sheet['pathRank']},purchases=[],talentTraining={},practiceCycle=None)
        sheet['paths']={sheet['path']:sheet['pathRank']}
    return p


def award_character(c,amount):
    """Atomic callers use this for one reviewed session award per character."""
    sheet=validate_sheet(copy.deepcopy(c['sheet']))['sheet']
    p=initialize(sheet)
    if type(amount) is not int or not 0<=amount<=1000 or p['earned']+amount>1000000:raise ValueError('Слишком много опыта.')
    p['earned']+=amount;p['revision']+=1
    c['sheet']=validate_sheet(sheet)['sheet']


def talent_change(sheet,p,t,data,operation):
    kind=data.get('kind');identifier=data.get('talent')
    entries=catalog()['general'] if kind=='talent' else catalog()['paths'].get(sheet['profession']+':'+sheet['expansion'],[]) if kind=='path' else []
    item=next((x for x in entries if x['id']==identifier and (not x.get('expansion') or x['expansion']==sheet['expansion'])),None)
    if not item:raise ValueError('Выберите доступное достоинство или путь своей профессии. Достоинства другого народа не изучаются.')
    pool=sheet['talents'] if kind=='talent' else sheet['paths'];level=pool.get(identifier,0);key=kind+':'+identifier
    if level>=3:raise ValueError('Максимальный ранг достоинства — 3.')
    if operation=='talentTraining':
        method=data.get('method')
        if data.get('confirmed') is not True or method not in ('teacher','practice'):raise ValueError('Подтвердите четверть обучения и способ изучения.')
        if method=='practice':
            if level:raise ValueError('Проверка Разума нужна только при изучении нового достоинства.')
            if p['practiceCycle']==t['cycleId']:raise ValueError('Самостоятельная попытка обучения уже учтена в этой четверти. Следующая — в новой четверти.')
            if type(data.get('success')) is not bool:raise ValueError('Укажите итог проверки Разума.')
            p['practiceCycle']=t['cycleId']
            if not data['success']:return f"{item['name']}: самостоятельная практика не удалась; новая попытка в следующую четверть."
        teacher_rank=data.get('teacherRank',0)
        if method=='teacher' and item.get('magic') and (type(teacher_rank) is not int or not level<teacher_rank<=3):raise ValueError('Магии обучает учитель с более высоким рангом этого пути.')
        if method=='teacher' and not item.get('magic') and (type(teacher_rank) is not int or not 1<=teacher_rank<=3):raise ValueError('У учителя должно быть это достоинство хотя бы ранга 1.')
        p['talentTraining'][key]=dict(rank=level+1,method=method,teacherRank=teacher_rank,session=t['session'],cycle=t['cycleId'])
        return f"{item['name']}: подтверждено обучение для ранга {level+1}. {data['note'].strip()}"
    if p['restCycle']!=t['cycleId']:raise ValueError('Мастер должен подтвердить четверть отдыха/сна для развития.')
    training=p['talentTraining'].get(key,{})
    if level==0 and training.get('rank')!=1:raise ValueError('Мастер должен подтвердить четверть практики и успешный Разум либо обучение у учителя.')
    teacher=training.get('method')=='teacher' and training.get('rank')==level+1
    cost=(level+1)*3*(3 if item.get('magic') and not teacher else 1)
    if p['earned']-p['spent']<cost:raise ValueError(f'Недостаточно опыта: нужно {cost}.')
    pool[identifier]=level+1
    if kind=='path' and identifier==sheet['path']:sheet['pathRank']=level+1
    p['spent']+=cost;p['purchases'].append(dict(kind=kind,id=identifier,rank=level+1,cost=cost,teacher=teacher,method='teacher' if teacher else 'practice' if level==0 else 'advance',session=t['session'],cycle=t['cycleId']))
    p['talentTraining'].pop(key,None)
    return f"{item['name']}: {level} → {level+1}, потрачено {cost} опыта."

def guard_sheet(old, new, allow_import=False):
    if old and old.get('progression'):
        if {k:v for k,v in old.items() if k not in TEXT_FIELDS} != {k:v for k,v in new.items() if k not in TEXT_FIELDS}:
            raise ValueError('Развитие или лист изменились. Откройте свежий лист. Навыки и опыт меняются только в разделе «Развитие».')
    elif new.get('progression') and not (old is None and allow_import):
        raise PermissionError('Опытный лист в кампанию импортирует Мастер. Опыт и навыки нельзя назначить через редактор.')


def apply(room, session, data):
    c=next((c for c in room['characters'] if c['id']==data.get('id') and c['kind']=='pc'),None)
    gm=session['role']=='gm'
    if not c or not gm and (c['owner']!=session['owner'] or c.get('hidden')):
        raise PermissionError('Развивать можно только своего героя.')
    t=room['journey']
    if room.get('combat',{}).get('phase') in ('setup','combat') or t['phase']=='resolving':
        raise ValueError('Завершите бой и текущие проверки четверти перед развитием.')
    operation=data.get('operation')
    if operation not in ('award','rest','training','advance','talentTraining','talentAdvance'):raise ValueError('Неизвестное действие развития.')
    if operation not in ('advance','talentAdvance') and not gm:raise PermissionError('Опыт и условия обучения подтверждает Мастер.')
    sheet=copy.deepcopy(c['sheet'])
    p=sheet.get('progression')
    revision=p['revision'] if p else 0
    if type(data.get('revision')) is not int or data['revision']!=revision:
        raise ValueError('Развитие уже изменилось. Обновите окно перед повторным действием.')
    if not p:
        if operation!='award':raise ValueError('Сначала Мастер фиксирует стартовый лист и начисляет опыт.')
        sheet=validate_sheet(sheet)['sheet']
    p=initialize(sheet)
    note=data.get('note','')
    if operation not in ('advance','talentAdvance') and (not isinstance(note,str) or not 3<=len(note.strip())<=300):
        raise ValueError('Укажите основание решения Мастера: 3–300 символов.')
    if operation=='award':
        amount=data.get('amount')
        if type(amount) is not int or not 0<=amount<=1000 or p['earned']+amount>1000000:raise ValueError('Опыт: целое число от 0 до 1000.')
        p['earned']+=amount
        message=f"Начислено {amount} опыта. {note.strip()}"
    elif operation=='rest':
        if data.get('confirmed') is not True:raise ValueError('Подтвердите четверть отдыха или сна.')
        p['restCycle']=t['cycleId'] if data.get('allowed') is True else None
        message=('Развитие разрешено после подтверждённой четверти отдыха/сна. ' if p['restCycle'] else 'Развитие закрыто. ')+note.strip()
    elif operation in ('talentTraining','talentAdvance'):
        message=talent_change(sheet,p,t,data,operation)
    else:
        skill=data.get('skill')
        if skill not in SKILLS:raise ValueError('Выберите навык.')
        level=sheet['skills'][skill]
        if operation=='training':
            if level!=0:raise ValueError('Основание обучения нужно только для нового навыка.')
            if data.get('method') not in ('success','teacher') or data.get('confirmed') is not True:
                raise ValueError('Подтвердите успешное применение в этой сессии или четверть обучения у учителя с навыком 1+.')
            p['training'][skill]=dict(method=data['method'],session=t['session'])
            message=f"Подтверждено основание изучения {NAMES[skill]}: {note.strip()}"
        else:
            if p['restCycle']!=t['cycleId']:raise ValueError('Мастер должен подтвердить четверть отдыха/сна для развития. Разрешение истекает при смене четверти.')
            if level>=5:raise ValueError('Максимальный уровень навыка — 5.')
            training=p['training'].get(skill,{})
            if level==0 and not (training.get('method')=='teacher' or training.get('method')=='success' and training.get('session')==t['session']):
                raise ValueError('Мастер должен подтвердить успешное применение навыка в этой сессии или обучение у учителя.')
            cost=(level+1)*5
            if p['earned']-p['spent']<cost:raise ValueError(f'Недостаточно опыта: нужно {cost}.')
            sheet['skills'][skill]=level+1;p['spent']+=cost;p['training'].pop(skill,None)
            message=f"{NAMES[skill]}: {level} → {level+1}, потрачено {cost} опыта."
    p['revision']+=1
    c['sheet']=validate_sheet(sheet)['sheet']
    room['log'].append(dict(name=session['name'],text=c['name']+': '+message))
    t['gmReady']=False
