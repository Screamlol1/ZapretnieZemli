"""Server-authorized skill growth; creation sheets cannot forge XP or paid levels."""
import copy
from sheet_validation import validate_sheet

TEXT_FIELDS = {'name','appearance','pride','secret','relationships','notes'}
SKILLS = ('melee','might','craft','endure','sleight','shoot','move','stealth',
          'survive','lore','insight','scout','influence','animal','perform','heal')

NAMES=dict(zip(SKILLS,('Ближний бой','Мощь','Ремесло','Стойкость','Ловкость рук','Меткость','Проворство','Скрытность','Выживание','Знания','Проницательность','Разведка','Влияние','Дрессировка','Исполнение','Лечение')))

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
    if room.get('combat',{}).get('phase')=='combat' or t['phase']=='resolving':
        raise ValueError('Завершите бой и текущие проверки четверти перед развитием.')
    operation=data.get('operation')
    if operation not in ('award','rest','training','advance'):raise ValueError('Неизвестное действие развития.')
    if operation!='advance' and not gm:raise PermissionError('Опыт и условия обучения подтверждает Мастер.')
    sheet=copy.deepcopy(c['sheet'])
    p=sheet.get('progression')
    revision=p['revision'] if p else 0
    if type(data.get('revision')) is not int or data['revision']!=revision:
        raise ValueError('Развитие уже изменилось. Обновите окно перед повторным действием.')
    if not p:
        if operation!='award':raise ValueError('Сначала Мастер фиксирует стартовый лист и начисляет опыт.')
        sheet=validate_sheet(sheet)['sheet']
        p=sheet['progression']=dict(version=1,revision=0,baseSkills=copy.deepcopy(sheet['skills']),earned=0,spent=0,restCycle=None,training={})
    note=data.get('note','')
    if operation!='advance' and (not isinstance(note,str) or not 3<=len(note.strip())<=300):
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
