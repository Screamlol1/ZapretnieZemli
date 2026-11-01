"""Campaign knowledge and recipient-scoped handouts. No public asset URLs."""
import base64
import copy
import hashlib
import secrets
import struct
import time

KINDS=('note','faction','person','place','clue','handout')
STATUSES=('hypothesis','confirmed','refuted')


def ensure(room):
    return room.setdefault('codex',dict(version=0,entries=[],relations=[]))


def text(value,limit,required=False):
    if not isinstance(value,str) or len(value)>limit or required and not value.strip():
        raise ValueError('Проверьте заполнение и длину текста записи.')
    return value.strip()


def visible(entry,s):
    return s['role']=='gm' or entry['visibility']=='all' or entry['visibility']=='owners' and (entry['author']==s['owner'] or s['owner'] in entry.get('recipients',[]))


def writable(entry,s):
    return s['role']=='gm' or visible(entry,s) and entry['author']==s['owner'] and entry['kind'] in ('clue','note')


def image_data(value):
    if not isinstance(value,str) or not value.startswith('data:image/png;base64,') or len(value)>90000:
        raise ValueError('Изображение: PNG до 64 КиБ после подготовки.')
    try:raw=base64.b64decode(value.split(',',1)[1],validate=True)
    except Exception:raise ValueError('Повреждённое изображение.')
    if len(raw)>65536 or len(raw)<33 or raw[:8]!=b'\x89PNG\r\n\x1a\n' or raw[12:16]!=b'IHDR':raise ValueError('Нужен корректный PNG.')
    width,height=struct.unpack('>II',raw[16:24])
    if not 1<=width<=1200 or not 1<=height<=1200:raise ValueError('Размер изображения — до 1200×1200.')
    return value,hashlib.sha256(raw).hexdigest()


def apply(room,s,data):
    current=ensure(room)
    if type(data.get('version'))!=int or data['version']!=current['version']:raise ValueError('Библиотека изменилась. Обновите запись перед сохранением.')
    draft=copy.deepcopy(current);op=data.get('op');gm=s['role']=='gm'
    found=next((e for e in draft['entries'] if e['id']==data.get('id')),None)
    if op=='save':
        raw=data.get('entry')
        if not isinstance(raw,dict):raise ValueError('Нужны поля записи.')
        kind=raw.get('kind',found['kind'] if found else 'note')
        if kind not in KINDS:raise ValueError('Неизвестный вид записи.')
        if not gm and (kind not in ('note','clue') or found and not writable(found,s)):raise PermissionError('Игрок изменяет только свои заметки и улики.')
        if data.get('id') and not found:raise ValueError('Запись удалена.')
        if not found and len(draft['entries'])>=200:raise ValueError('В библиотеке уже 200 записей.')
        visibility=raw.get('visibility','gm' if gm else 'owners')
        if visibility not in ('gm','all','owners') or not gm and visibility=='gm':raise ValueError('Выберите получателей записи.')
        recipients=raw.get('recipients',[])
        owners={i['owner'] for i in room.get('identities',{}).values()}
        if not isinstance(recipients,list) or len(recipients)>11 or any(not isinstance(x,str) or x not in owners for x in recipients):raise ValueError('Получатель не найден в кампании.')
        if visibility!='owners':recipients=[]
        status=raw.get('status','hypothesis')
        if status not in STATUSES:raise ValueError('Неизвестная отметка улики.')
        tags=raw.get('tags',[])
        if not isinstance(tags,list) or len(tags)>8:raise ValueError('До восьми меток.')
        reference=raw.get('reference',{})
        if not isinstance(reference,dict) or reference and (reference.get('kind') not in ('character','location','hex') or not isinstance(reference.get('id'),str) or len(reference['id'])>100):raise ValueError('Некорректная ссылка на объект.')
        entry=dict(id=found['id'] if found else secrets.token_hex(10),author=found['author'] if found else s['owner'],authorName=found['authorName'] if found else s['name'],
                   kind=kind,title=text(raw.get('title',''),100,True),text=text(raw.get('text',''),6000),source=text(raw.get('source',''),200),
                   secret=text(raw.get('secret',''),3000) if gm else found.get('secret','') if found else '',
                   visibility=visibility,recipients=list(dict.fromkeys(recipients)),status=status,tags=[text(t,30,True) for t in tags],reference={k:reference[k] for k in ('kind','id') if k in reference},updated=time.time())
        if found and found.get('imageData') and not raw.get('removeImage'):
            entry.update(imageData=found['imageData'],imageHash=found['imageHash'])
        if raw.get('image'):
            if not gm or kind!='handout':raise PermissionError('Изображения раздаточных материалов добавляет Мастер.')
            entry['imageData'],entry['imageHash']=image_data(raw['image'])
        draft['entries']=[e for e in draft['entries'] if e['id']!=entry['id']]+[entry]
        if sum(len(e.get('imageData','')) for e in draft['entries'])>1800000:raise ValueError('В коллекции уже слишком много изображений. Удалите ненужные.')
    elif op=='delete':
        if not found or not writable(found,s):raise PermissionError('Удаление этой записи недоступно.')
        draft['entries']=[e for e in draft['entries'] if e['id']!=found['id']]
        draft['relations']=[r for r in draft['relations'] if found['id'] not in (r['from'],r['to'])]
    elif op in ('relation','deleteRelation'):
        if not gm:raise PermissionError('Связями мира управляет Мастер.')
        if op=='deleteRelation':
            if not any(r['id']==data.get('id') for r in draft['relations']):raise ValueError('Связь удалена.')
            draft['relations']=[r for r in draft['relations'] if r['id']!=data['id']]
        else:
            ids={e['id'] for e in draft['entries']};a=data.get('from');b=data.get('to')
            if not isinstance(a,str) or not isinstance(b,str) or a not in ids or b not in ids or a==b:raise ValueError('Выберите две разные записи.')
            if len(draft['relations'])>=400:raise ValueError('В графе уже 400 связей.')
            label=text(data.get('label',''),80,True)
            draft['relations'].append(dict(id=secrets.token_hex(10),**{'from':a,'to':b},label=label,secret=data.get('secret') is True))
    else:raise ValueError('Неизвестная операция библиотеки.')
    draft['version']+=1;room['codex']=draft


def project(room,s):
    codex=ensure(room);entries=[]
    characters={c['id'] for c in room.get('characters',[])};locations={m['id'] for m in room.get('locationMaps',[])}
    for original in codex['entries']:
        if not visible(original,s):continue
        entry={k:copy.deepcopy(v) for k,v in original.items() if k!='imageData'}
        entry['canEdit']=writable(original,s);entry['hasImage']=bool(original.get('imageData'))
        if s['role']!='gm':
            entry.pop('secret',None)
            if entry['author']!=s['owner']:entry.pop('recipients',None)
            ref=entry.get('reference',{})
            if ref.get('kind')=='character' and ref.get('id') not in characters or ref.get('kind')=='location' and ref.get('id') not in locations:entry['reference']={}
        entries.append(entry)
    ids={e['id'] for e in entries}
    room['codex']=dict(version=codex['version'],entries=entries,relations=[r for r in codex['relations'] if r['from'] in ids and r['to'] in ids and (s['role']=='gm' or not r.get('secret'))])


def media(room,s,identifier):
    entry=next((e for e in ensure(room)['entries'] if e['id']==identifier),None)
    if not entry or not visible(entry,s) or not entry.get('imageData'):raise PermissionError('Материал недоступен.')
    return dict(image=entry['imageData'],hash=entry['imageHash'])
