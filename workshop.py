"""Private GM preparation library; publishing is an explicit versioned action."""
import re
import secrets
from campaign_rules import coordinate, pending, participants

FIELDS={
    'event':('title','terrain','description','problem','secret'),
    'settlement':('title','size','age','ruler','institutions','description','problem','secret'),
    'monster':('title','strength','agility','armor','dice','damage',*[f'attack{i}' for i in range(1,7)],'description','secret'),
    'ruin':('title','origin','description','problem','secret')}
LABELS=dict(title='Название',terrain='Местность',description='Описание',problem='Осложнение',secret='Секрет Мастера',size='Размер и население',age='Возраст',ruler='Правитель',institutions='Заведения',origin='Прошлое места')


def text(value,limit):
    if not isinstance(value,str) or len(value)>limit:raise ValueError('Проверьте длину текста заготовки.')
    return value.strip()


def table(raw):
    if not isinstance(raw,dict) or raw.get('dice') not in ('D6','D66'):raise ValueError('Таблица: D6 или D66.')
    result={k:text(raw.get(k,''),limit) for k,limit in (('name',100),('source',300),('rows',5000))};result['dice']=raw['dice']
    faces=set(range(1,7)) if raw['dice']=='D6' else {10*a+b for a in range(1,7) for b in range(1,7)};used=set()
    for line in result['rows'].splitlines():
        if not line.strip():continue
        m=re.fullmatch(r'\s*(\d+)(?:\s*[-–]\s*(\d+))?\s*\|\s*(.+?)\s*',line)
        if not m:raise ValueError('Строка таблицы: 1-2 | результат.')
        low=int(m[1]);high=int(m[2] or m[1]);selected={v for v in faces if low<=v<=high}
        if low not in faces or high not in faces or low>high or selected&used:raise ValueError('Некорректные или пересекающиеся диапазоны.')
        used|=selected
    if used!=faces:raise ValueError('В таблице пропущены результаты.')
    return result


def entry(room,data):
    found=next((e for e in room.get('workshop',[]) if e['id']==data.get('id')),None)
    if not found or found['version']!=data.get('version'):raise ValueError('Заготовка изменена. Откройте её снова.')
    return found


def apply(room,s,data):
    if s['role']!='gm':raise PermissionError('Мастерская доступна только ведущему.')
    entries=room.setdefault('workshop',[])
    if data['action']=='workshopSave':
        old=entry(room,data) if data.get('id') else None
        if old and old.get('published'):raise ValueError('Заготовка уже применена. Создайте новую копию для другой ситуации.')
        if not old and len(entries)>=100:raise ValueError('В мастерской уже 100 заготовок. Удалите ненужные.')
        raw=data.get('draft',{})
        if not isinstance(raw,dict):raise ValueError('Нужна заготовка.')
        kind=raw.get('kind')
        if kind not in FIELDS:raise ValueError('Выберите вид заготовки.')
        fields=raw.get('fields',{});locked=raw.get('locked',[]);tables=raw.get('tables',{});trace=raw.get('trace',{})
        if not isinstance(fields,dict) or not isinstance(locked,list) or not isinstance(tables,dict) or not isinstance(trace,dict):raise ValueError('Некорректная заготовка.')
        if any(not isinstance(k,str) for k in locked):raise ValueError('Некорректное закрепление полей.')
        keys=set(FIELDS[kind])
        if (set(fields)|set(locked)|set(tables)|set(trace))-keys:raise ValueError('Неизвестный параметр заготовки.')
        values={k:text(fields.get(k,''),60 if k=='title' else 1200) for k in keys}
        if not values['title']:raise ValueError('Укажите название.')
        saved=dict(id=old['id'] if old else secrets.token_hex(12),version=old['version']+1 if old else 1,kind=kind,fields=values,locked=locked,tables={k:table(t) for k,t in tables.items()},trace={k:text(v,6000) for k,v in trace.items()})
        room['workshop']=[e for e in entries if e['id']!=saved['id']]+[saved]
        return
    e=entry(room,data)
    if data['action']=='workshopDelete':
        room['workshop']=[x for x in entries if x['id']!=e['id']];return
    if data['action']!='workshopPublish':raise ValueError('Неизвестное действие мастерской.')
    if e.get('published'):raise ValueError('Эта заготовка уже применена.')
    fields=e['fields'];details='\n'.join(f'{LABELS.get(k,k)}: {fields[k]}' for k in FIELDS[e['kind']] if fields.get(k))
    if e['kind']=='event':
        t=room['journey']
        if len(t['pending'])>=100:raise ValueError('Сначала разрешите накопившиеся события.')
        item=pending(room,fields['title'],'Мастерская ведущего: таблицы и ручное редактирование.')
        item['note']=details;e['published']=dict(kind='event',id=item['id'])
        t['gmReady']=False;t['completed']={}
        for who in participants(room):t['completionVersions'][who]=t['completionVersions'].get(who,0)+1
        t['revision']+=1
    elif e['kind'] in ('settlement','ruin'):
        p=coordinate(data,room);key=f"{p['x']},{p['y']}";cell=room['maps']['world'].setdefault(key,{})
        if cell.get('label') or cell.get('siteType') not in (None,'none'):raise ValueError('В гексе уже есть место. Выберите свободный гекс.')
        cell.update(label=fields['title'],note=fields.get('description',''),gmNote=details,siteType='settlement' if e['kind']=='settlement' else 'ruin',siteHidden=True)
        e['published']=dict(kind='place',**p)
    else:raise ValueError('Чудовище добавляется через редактор параметров.')
    e['version']+=1
