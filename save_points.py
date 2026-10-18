"""Durable checkpoints. Player exports never include another hero or GM secrets."""
import copy
import json
import secrets
import time


def init(db):
    db.execute('CREATE TABLE IF NOT EXISTS checkpoints (id TEXT PRIMARY KEY, room TEXT, scope TEXT, subject TEXT, created REAL, label TEXT, data TEXT)')
    db.execute('CREATE INDEX IF NOT EXISTS checkpoints_room ON checkpoints(room, scope, subject, created)')
    db.commit()


def allowed(room,s,scope,subject):
    if scope=='campaign':
        if s['role']!='gm':raise PermissionError('Состояние всей кампании сохраняет и восстанавливает Мастер.')
        return None
    if scope!='character':raise ValueError('Неизвестный вид сохранения.')
    c=next((c for c in room['characters'] if c['id']==subject),None)
    if not c or s['role']!='gm' and (c['owner']!=s['owner'] or c['kind']!='pc' or c.get('hidden')):
        raise PermissionError('Можно сохранять только своего героя.')
    return c


def capture(room,scope,c=None):
    if scope=='campaign':
        return {k:copy.deepcopy(v) for k,v in room.items() if not k.startswith('_') and k not in ('gmKey','playerKey','identities','gmAccount')}
    items=[{k:copy.deepcopy(v) for k,v in i.items() if k not in ('gmNote','maintenanceNote')} for i in room.get('items',[]) if i['location']==dict(kind='character',id=c['id'])]
    return dict(character=copy.deepcopy(c),items=items,
                journey=dict(day=room.get('journey',{}).get('day',1),quarter=room.get('journey',{}).get('quarter',0)),
                combatUnit=next((copy.deepcopy(u) for u in room.get('combat',{}).get('units',[]) if u['id']==c['id']),None))


def insert(db,room,scope,subject,label,payload):
    identifier=secrets.token_hex(16);created=time.time()
    document=dict(format='forbidden-lands-save',version=1,scope=scope,createdAt=created,campaign=room['id'],campaignTitle=room['title'],revision=room['revision'],label=label,state=payload)
    db.execute('INSERT INTO checkpoints VALUES (?,?,?,?,?,?,?)',(identifier,room['id'],scope,subject,created,label,json.dumps(document)))
    db.execute('DELETE FROM checkpoints WHERE room=? AND scope=? AND subject=? AND id NOT IN (SELECT id FROM checkpoints WHERE room=? AND scope=? AND subject=? ORDER BY created DESC, id DESC LIMIT 20)',(room['id'],scope,subject,room['id'],scope,subject))
    return dict(id=identifier,createdAt=created,label=label,document=document)


def apply(game,s,data):
    room=game.room(s['room']);scope=data.get('scope');subject=data.get('character','') if scope=='character' else ''
    c=allowed(room,s,scope,subject);operation=data.get('operation')
    if operation=='list':
        rows=game.db.execute('SELECT id,created,label FROM checkpoints WHERE room=? AND scope=? AND subject=? ORDER BY created DESC,id DESC',(room['id'],scope,subject)).fetchall()
        return dict(saves=[dict(id=i,createdAt=t,label=label) for i,t,label in rows])
    if operation=='create':
        label=data.get('label','').strip() if isinstance(data.get('label',''),str) else ''
        if len(label)>100:raise ValueError('Название сохранения: до 100 символов.')
        with game.db:
            result=insert(game.db,room,scope,subject,label or ('Состояние кампании' if scope=='campaign' else c['name']),capture(room,scope,c))
        return result
    row=game.db.execute('SELECT data FROM checkpoints WHERE id=? AND room=? AND scope=? AND subject=?',(str(data.get('id','')),room['id'],scope,subject)).fetchone()
    if not row:raise ValueError('Сохранение не найдено.')
    document=json.loads(row[0])
    if operation=='get':return dict(document=document)
    if operation!='restore' or scope!='campaign':raise ValueError('Копия героя доступна для просмотра и скачивания. Игру продолжайте с текущим листом кампании; откат всей кампании выполняет Мастер.')
    if data.get('confirmed') is not True:raise ValueError('Подтвердите восстановление всей кампании.')
    if data.get('revision')!=room['revision']:raise ValueError('Кампания уже изменилась. Проверьте новое состояние перед восстановлением.')
    restored=copy.deepcopy(document['state'])
    for key in ('id','gmKey','playerKey','identities'):restored[key]=room[key]
    if room.get('gmAccount'):restored['gmAccount']=room['gmAccount']
    for key in ('revision','combatRevision'):restored[key]=max(room.get(key,0),restored.get(key,0))+1
    for kind,field in (('items','version'),('characters','equipmentVersion'),('workshop','version')):
        current={x['id']:x.get(field,0) for x in room.get(kind,[])}
        for x in restored.get(kind,[]):x[field]=max(x.get(field,0),current.get(x['id'],0))+1
    t=restored.get('journey')
    if t:
        t['revision']=max(t.get('revision',0),room.get('journey',{}).get('revision',0))+1
        t['cycleId']=secrets.token_hex(8)
    art=restored.setdefault('mapArtwork',{})
    art['revision']=max(art.get('revision',0),room.get('mapArtwork',{}).get('revision',0))+1
    restored['log']=(restored.get('log',[])+[dict(name='Мастер',text='Кампания восстановлена из сохранения: '+document['label'])])[-200:]
    restored['savedAt']=time.time()
    with game.db:
        insert(game.db,room,'campaign','','Перед восстановлением',capture(room,'campaign'))
        game.db.execute('INSERT OR REPLACE INTO rooms VALUES (?,?)',(room['id'],json.dumps(restored)))
        game.accounts.sync(restored)
    return dict(state=game.view(s))
