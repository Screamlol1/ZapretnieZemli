from opposed_checks import apply as opposed_action
from free_risk import apply as free_risk_action
"""Campaign server. Python 3.11+, no third-party dependencies."""
from journal import stamp_entries
from location_maps import apply as location_map_action, redact as redact_location_maps
from dice_pools import skill_counts, result_text, artifact_sides
from dice_events import publish as publish_dice, group as dice_group, visibility as dice_visibility, redact as redact_dice
import argparse
import base64
import binascii
import json
import gzip
import hashlib
import mimetypes
import secrets
import sqlite3
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from campaign_rules import apply as campaign_action, state as journey_state, coordinate, participants

from terrain_map import load_reference, effective_world
from inventory_rules import apply as inventory_action, public_items, ensure as ensure_inventory
from equipment_rules import combat_gear, sync_wear, load as inventory_load
from skill_checks import apply as character_check
from save_points import init as init_saves, apply as checkpoint_action
from workshop import apply as workshop_action, entry as workshop_entry
from sheet_validation import validate_sheet
from progression import apply as progression_action, guard_sheet
from accounts import Accounts, COOKIE, LIFETIME
from admin import Administration, SUPPORT_COOKIE, SUPPORT_SECONDS
from http.cookies import SimpleCookie

ROOT = Path(__file__).parent
LOCK = threading.RLock()

class RequestLimits:
    """Bounded per-address request windows for the public test server."""
    def __init__(self,limits=None):
        self.limits={'auth':(30,60),'write':(240,60),'read':(1800,60),'static':(6000,60),**(limits or {})}
        self.windows={};self.lock=threading.Lock();self.cleaned=0

    def retry_after(self,address,group):
        now=time.monotonic();maximum,period=self.limits[group]
        with self.lock:
            if now-self.cleaned>=60:
                self.windows={k:v for k,v in self.windows.items() if now-v[0]<self.limits[k[1]][1]}
                self.cleaned=now
            key=(address,group);start,count=self.windows.get(key,(now,0))
            if now-start>=period:start,count=now,0
            if count>=maximum or key not in self.windows and len(self.windows)>=8192:
                return max(1,int(period-(now-start))+1)
            self.windows[key]=(start,count+1)
        return 0

class Game:
    def __init__(self, database, reference_root=None):
        self.reference_root=Path(reference_root) if reference_root is not None else ROOT/'local-assets'
        self.reference_terrain=load_reference(self.reference_root)
        self.image_root = Path(database).parent/'map-images'
        self.db = sqlite3.connect(database, check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS rooms (id TEXT PRIMARY KEY, data TEXT)')
        init_saves(self.db)
        self.sessions = {}
        self.accounts = Accounts(self)
        self.admin = Administration(self)

    def save(self, room):
        room['savedAt']=time.time()
        self.db.execute('INSERT OR REPLACE INTO rooms VALUES (?,?)', (room['id'], json.dumps({k:v for k,v in room.items() if not k.startswith('_')})))
        self.accounts.sync(room)
        self.db.commit()

    def room(self, code):
        row = self.db.execute('SELECT data FROM rooms WHERE id=?', (code,)).fetchone()
        if not row:
            raise ValueError('Кампания не найдена.')
        room=json.loads(row[0])
        art=room.get('mapArtwork',{})
        if room.get('worldLayout')=='ravenland' and art.get('style','reference')!='upload':room['_worldBase']=self.reference_terrain
        return room

    def login(self, data, create=False, account=None):
        name = str(data.get('name', '')).strip()[:60]
        if not name:
            raise ValueError('Укажите имя участника.')
        if create:
            code = secrets.token_hex(4).upper()
            key = secrets.token_urlsafe(24)
            room = dict(id=code, title=str(data.get('title') or 'Новая экспедиция')[:100],
                        gmKey=key, playerKey=secrets.token_urlsafe(18), revision=0,
                        worldLayout='ravenland', characters=[], maps={'world': {}, 'battle': {}}, tokens=[], log=[], identities={})
            self.save(room)
            role = 'gm'
        else:
            room = self.room(str(data.get('code', '')).upper())
            key = data.get('key', '')
            if secrets.compare_digest(str(key), room['gmKey']):
                role = 'gm'
            elif secrets.compare_digest(str(key), room['playerKey']):
                role = 'player'
            else:
                raise PermissionError('Неверный ключ приглашения.')
        resume = str(data.get('resume', ''))
        identity = room.get('identities',{}).get(resume)
        if identity and identity['role']!=role:
            identity=None
        account_id = account['id'] if account else None
        if identity and identity.get('account') and identity['account'] != account_id:
            raise PermissionError('Этот участник привязан к аккаунту. Войдите в его личный кабинет.')
        if role == 'gm' and room.get('gmAccount') and room['gmAccount'] != account_id:
            raise PermissionError('Кампания принадлежит другому аккаунту Мастера.')
        if account and role == 'gm': room['gmAccount'] = account_id
        active = [s for s in self.sessions.values() if s['room'] == room['id'] and time.time()-s['seen'] < 45
                  and (not identity or s['owner']!=identity['owner'])]
        if role == 'gm' and any(s['role'] == 'gm' for s in active):
            raise ValueError('Мастер уже подключён.')
        if len(active) >= 11 or role == 'player' and sum(s['role']=='player' for s in active) >= 10:
            raise ValueError('Все места заняты: один Мастер и десять игроков.')
        token = secrets.token_urlsafe(32)
        # Stable owner identity across reconnects, private reconnect key issued separately.
        owner = identity['owner'] if identity else secrets.token_hex(12)
        resume = resume if identity else secrets.token_urlsafe(32)
        if len(room.get('identities',{}))>=500 and not identity:
            raise ValueError('Предел участников кампании достигнут.')
        room.setdefault('identities',{})[resume]=dict(owner=owner,role=role,name=name)
        if account: room['identities'][resume]['account'] = account_id
        self.save(room)
        for t in [t for t,x in self.sessions.items() if x['room']==room['id'] and x['owner']==owner]:
            del self.sessions[t]
        self.sessions[token] = dict(room=room['id'], role=role, name=name, owner=owner, resume=resume, seen=time.time())
        if account: self.sessions[token].update(account=account_id, accountSession=account['session'])
        return dict(token=token, resume=resume, code=room['id'], role=role,
                    account=bool(account),
                    gmKey=room['gmKey'] if role=='gm' else None,
                    playerKey=room['playerKey'] if role=='gm' else None)

    def session(self, token):
        s = self.sessions.get(token)
        if not s or time.time()-s['seen']>=45:
            raise PermissionError('Войдите в кампанию.')
        if s.get('account') and not self.accounts.valid_session(s['accountSession'], s['account']):
            raise PermissionError('Войдите в личный кабинет.')
        s['seen'] = time.time()
        return s

    def reconnect(self, data, account=None):
        room=self.room(str(data.get('code','')).upper())
        identity=room.get('identities',{}).get(str(data.get('resume','')))
        if not identity:raise PermissionError('Не удалось восстановить вход. Используйте приглашение.')
        return self.login(dict(code=room['id'],resume=data['resume'],name=identity['name'],
                               key=room['gmKey'] if identity['role']=='gm' else room['playerKey']), account=account)

    def view(self, s):
        room = self.room(s['room'])
        journey_state(room)
        room['maps']['world']=effective_world(room)
        room['mapTerrain']={'referenceCount':len(room.get('_worldBase',{}))}
        room.pop('_worldBase',None)
        identities=room.get('identities',{})
        # Public identity metadata stays stable after a participant disconnects.
        # Resume keys and account references never leave the server.
        room['participantDirectory']=list({i['owner']:dict(owner=i['owner'],name=i.get('name','Участник'),role=i['role']) for i in identities.values()}.values())
        t=room['journey']
        t['cycleParticipants']=[dict(owner=owner,name='Мастер' if owner=='gm' else next((i.get('name','Игрок') for i in identities.values() if i['owner']==owner), 'Игрок'),
            declared=t['gmReady'] if owner=='gm' else all(c['id'] in t['plans'] for c in room['characters'] if c['id'] in t['party'] and c['kind']=='pc' and c['owner']==owner),
            complete=bool(t['completed'].get(owner))) for owner in participants(room)] if t['party'] else []
        room.pop('gmKey'); room.pop('playerKey')
        room.pop('identities',None)
        room.pop('gmAccount',None)
        if s['role']=='gm':
            room['owners']=[dict(owner=x['owner'],name=x.get('name','Участник'),role=x['role']) for x in identities.values()]
        room.pop('combatOwners',None)
        if room.get('combat',{}).get('pendingRisk'):
            risk=room['combat']['pendingRisk'];risk.pop('replay',None)
            if risk.get('private') and s['role']!='gm':room['combat']['pendingRisk']={'waiting':True}
        if room.get('combat',{}).get('initiativeDraw'):room['combat']['initiativeDraw'].pop('deck',None)
        free=room.pop('freeChecks',{}).get(s['owner'])
        if free and not free.get('done'):room['freeRisk']={'roll':free['id']}
        room.pop('journeyResolution',None)
        if room.get('journeyRisk',{}).get('private') and s['role']!='gm':room['journeyRisk']={'waiting':True}
        room.pop('locationHistory',None)
        artwork=room.get('mapArtwork',{})
        room['mapArtwork']={k:v for k,v in artwork.items() if k in ('style','revision')}
        room['mapArtwork']['referenceAvailable']=(self.reference_root/'forbidden-lands.jpg').is_file()
        room['mapArtwork']['uploadAvailable']=bool(artwork.get('file'))
        room['mapFog']={kind:[k for k,v in cells.items() if v.get('hidden')] for kind,cells in room['maps'].items()}
        room['items']=public_items(room,s)
        for c in room['characters']:
            if c.get('inventoryInitialized') and c.get('sheet'):c['load']=inventory_load(room,c)
        room['characters'] = [c if s['role']=='gm' or c['owner']==s['owner'] and c['kind']=='pc' else
                              {**{k:v for k,v in c.items() if k in ('id','owner','name','kind','visual')},'kin':c.get('sheet',{}).get('kin')} for c in room['characters']
                              if s['role']=='gm' or not c.get('hidden')]
        if s['role']!='gm':
            redact_dice(room)
            room['opposedChecks']=[p for p in room.get('opposedChecks',[]) if not p['private']]
            redact_location_maps(room)
            room.pop('workshop',None)
            room['journey']['pendingCount']=len(room['journey']['pending'])
            room['journey']['pending']=[]
            room['journey']['history']=[e for e in room['journey']['history'] if not e.get('private')]
            own_ids={c['id'] for c in room['characters'] if c['kind']=='pc' and c['owner']==s['owner']}
            for entry in room['journey']['history']:
                if 'rolls' in entry:entry['rolls']=[r for r in entry['rolls'] if r['character'] in own_ids and r['skill']!='scout']
            room['tokens'] = [t for t in room['tokens'] if not t.get('hidden')]
            room['maps'] = {kind:{k:v for k,v in cells.items() if not v.get('hidden')} for kind,cells in room['maps'].items()}
            for cells in room['maps'].values():
                for cell in cells.values():
                    cell.pop('gmNote',None)
                    if cell.pop('siteHidden',False):
                        for k in ('label','note','siteType'):cell.pop(k,None)
            for u in room.get('combat',{}).get('units',[]):
                if u.get('monster'):u['monster']={}
        room['members'] = [dict(name=x['name'], role=x['role'], owner=x['owner']) for x in self.sessions.values()
                           if x['room']==s['room'] and time.time()-x['seen']<45]
        room['me'] = dict(role=s['role'], owner=s['owner'], name=s['name'])
        if s.get('account'):
            support=self.db.execute('SELECT actor FROM account_sessions WHERE token=?',(s['accountSession'],)).fetchone()
            if support and support[0]:room['me']['support']=True
        return room

    def action(self, s, data):
        room = self.room(s['room'])
        previous_logs={id(entry) for entry in room['log']}
        action = data.get('action')
        gm = s['role']=='gm'
        if room.get('journeyRisk') and action not in ('travelRisk','chat','roll','freePush','freeAccept'):raise ValueError('Сначала завершите проверку путешествия: примите результат или пойдите на риск.')
        if room.get('combat',{}).get('pendingRisk') and action in ('character','actor','assignCharacter','runtime','deleteCharacter','combatCreate','combatManual','combatClose'):raise ValueError('Сначала завершите текущий боевой бросок.')
        t=journey_state(room)
        repairing={i['repair']['character'] for i in room.get('items',[]) if i.get('repair',{}).get('status')=='rolled'}
        target=data.get('id') if isinstance(data.get('id'),str) else None
        mutation=action in ('character','actor','assignCharacter','runtime','deleteCharacter','characterProgression') and target in repairing
        choices=data.get('units') if isinstance(data.get('units'),list) else []
        battle=action=='combatCreate' and any(isinstance(u,dict) and isinstance(u.get('id'),str) and u['id'] in repairing for u in choices)
        party={cid for cid in data.get('party',[]) if isinstance(cid,str)} if isinstance(data.get('party'),list) else set()
        travel=isinstance(action,str) and action.startswith('travel') and (repairing.intersection(t['party']) or target in repairing or repairing.intersection(party))
        if mutation or battle or travel:raise ValueError('Сначала завершите бросок ремонта: примите результат или пойдите на риск.')
        if t['phase']=='resolving' and action in ('character','actor','deleteCharacter','assignCharacter','runtime') and data.get('id') in t['party']:
            raise ValueError('Персонаж выполняет занятие. Завершите текущую четверть перед изменением листа или владельца.')
        if action in ('paint','mapLocation','mapArtwork','worldLayout','event','deleteCharacter','assignCharacter','deleteToken','combatCreate','combatClose','actor','combatManual') and not gm:
            raise PermissionError('Действие доступно только Мастеру.')
        if action in ('inventoryOpen','itemCreate','itemEdit','itemTransfer','itemWear','equipment','inventoryCoins','inventoryResource','itemAppearance','itemSplit','itemConsume','itemMerge','inventoryRepair'):
            inventory_action(room,s,data)
            if action!='inventoryOpen':room['journey']['gmReady']=False
        elif action in ('opposedCreate','opposedRoll','opposedPush','opposedAccept','opposedCancel'):
            opposed_action(room,s,data)
        elif action in ('characterRoll','characterPush','characterAccept'):
            character_check(room,s,data)
        elif isinstance(action,str) and action.startswith('locationMap'):
            location_map_action(room,s,data)
        elif isinstance(action,str) and action.startswith('workshop'):
            workshop_action(room,s,data)
        elif isinstance(action,str) and (action.startswith('travel') or action.startswith('hold')):
            if action in ('travelSetup','travelParty','travelPlan','travelReady','travelAdvance'):
                ids=data.get('party',t['party'])
                if isinstance(ids,list):
                    for c in room['characters']:
                        if c['id'] in ids and c['kind']!='monster' and c.get('sheet',{}).get('game')=='forbidden-lands':
                            ensure_inventory(room,c['id'])
            campaign_action(room,s,data)
        elif action=='characterProgression':
            progression_action(room,s,data)
        elif action=='character':
            validated=validate_sheet(data.get('sheet'))
            sheet=validated['sheet']
            cid = str(data.get('id') or secrets.token_hex(8))
            old = next((c for c in room['characters'] if c['id']==cid),None)
            guard_sheet(old['sheet'] if old else None,sheet,allow_import=gm)
            if old and old['owner']!=s['owner'] and not gm:
                raise PermissionError('Нельзя изменять чужого персонажа.')
            if old and room.get('combat',{}).get('phase')=='combat' and cid in room.get('combatOwners',{}):
                raise ValueError('Во время боя лист занят. Завершите бой перед изменением.')
            if len(room['characters'])>=100 and not old:
                raise ValueError('Предел: 100 персонажей.')
            if not gm and not old and sum(c['owner']==s['owner'] for c in room['characters'])>=5:
                raise ValueError('Предел: пять персонажей игрока.')
            c = dict(id=cid,owner=old['owner'] if old else s['owner'],name=sheet['name'][:60],
                     kind=old['kind'] if old else ('npc' if gm and data.get('npc') else 'pc'),
                     hidden=old.get('hidden',False) if old else bool(gm and data.get('hidden')),sheet=sheet)
            if old and old['kind']!='pc':raise ValueError('ПВ и чудовища изменяются в редакторе Мастера.')
            c['runtime']=old.get('runtime',{}) if old else dict(current=sheet['attrs'].copy(),wp=0,resources=validated['resources'])
            if old and 'visual' in old:c['visual']=old['visual']
            if old and old.get('inventoryInitialized'):
                c['inventoryInitialized']=True
                for k in ('equipment','equipmentVersion'):
                    if k in old:c[k]=old[k]
            c['runtime']['current']={k:min(c['runtime'].get('current',{}).get(k,v),v) for k,v in sheet['attrs'].items()}
            room['characters'] = [x for x in room['characters'] if x['id']!=cid]+[c]
        elif action=='assignCharacter':
            c=next((c for c in room['characters'] if c['id']==data.get('id')),None)
            if not c: raise ValueError('Персонаж не найден.')
            if room.get('combat',{}).get('phase')=='combat': raise ValueError('Назначение владельца доступно вне боя.')
            owner=data.get('owner')
            if not any(x['owner']==owner for x in room.get('identities',{}).values()): raise ValueError('Участник не найден.')
            c['owner']=owner
            for t in room['tokens']:
                if t.get('characterId')==c['id']:t['owner']=owner
        elif action=='visual':
            c=next((c for c in room['characters'] if c['id']==data.get('id')),None)
            if not c or not gm and c['owner']!=s['owner']:raise PermissionError('Это не ваш персонаж.')
            v=data.get('visual')
            if not isinstance(v,dict) or set(v)!={'body','cloak','cloth','skin','hair','monster'} or v['body'] not in ('slim','broad') or v['monster'] not in ('spider','reptile','beast','horned'):
                raise ValueError('Некорректная внешность.')
            for k in ('cloak','cloth','skin','hair'):
                color=v[k]
                if not isinstance(color,str) or len(color)!=7 or color[0]!='#' or any(ch not in '0123456789abcdefABCDEF' for ch in color[1:]):raise ValueError('Некорректный цвет.')
            c['visual']=v
            for u in room.get('combat',{}).get('units',[]):
                if u['id']==c['id']:u['visual']=v
        elif action=='actor':
            source=None
            if data.get('workshopId'):
                source=workshop_entry(room,dict(id=data['workshopId'],version=data.get('workshopVersion')))
                if source.get('published') or source['kind']!='monster' or data.get('id') or data.get('actor',{}).get('kind')!='monster':raise ValueError('Заготовка чудовища уже применена или недоступна.')
            old=next((c for c in room['characters'] if c['id']==data.get('id')),None)
            if old and old['kind']=='pc':raise ValueError('Герой редактируется в конструкторе.')
            if room.get('combat',{}).get('phase')=='combat':raise ValueError('Редактор параметров доступен вне активного боя.')
            try:checked=subprocess.run(['node',str(ROOT/'validate-actor.mjs')],input=json.dumps(data.get('actor')),text=True,encoding='utf-8',capture_output=True,timeout=8)
            except (OSError,subprocess.TimeoutExpired):raise ValueError('Редактор недоступен: проверьте Node.js.')
            if checked.returncode:raise ValueError(checked.stderr.strip()[:500])
            actor=json.loads(checked.stdout);actor['id']=old['id'] if old else secrets.token_hex(8)
            actor['owner']=old['owner'] if old else s['owner']
            if len(room['characters'])>=100 and not old:raise ValueError('Предел: 100 персонажей.')
            if old and 'visual' in old:actor['visual']=old['visual']
            if old and old.get('inventoryInitialized'):
                actor['inventoryInitialized']=True
                for k in ('equipment','equipmentVersion'):
                    if k in old:actor[k]=old[k]
            if actor['kind']=='npc':actor['runtime']=dict(current=actor['sheet']['attrs'].copy(),wp=0)
            else:actor['runtime']=dict(current=dict(str=actor['monster']['strength'],agi=actor['monster']['agility'],wit=1,emp=1),wp=0)
            if old and old['kind']==actor['kind']:
                actor['runtime']={**old.get('runtime',{}),**actor['runtime']}
                actor['runtime']['current']={k:min(old.get('runtime',{}).get('current',{}).get(k,v),v) for k,v in actor['runtime']['current'].items()}
            room['characters']=[c for c in room['characters'] if c['id']!=actor['id']]+[actor]
            if source:source.update(published=dict(kind='monster',id=actor['id']),version=source['version']+1)
        elif action=='runtime':
            c=next((c for c in room['characters'] if c['id']==data.get('id')),None)
            if not c or not gm:raise PermissionError('Текущее состояние изменяет Мастер.')
            if room.get('combat',{}).get('phase')=='combat':raise ValueError('Во время боя параметры изменяет боевой движок.')
            current=data.get('current',{});wp=data.get('wp')
            maximum=c['sheet']['attrs'] if c['kind']!='monster' else dict(str=c['monster']['strength'],agi=c['monster']['agility'],wit=1,emp=1)
            if not isinstance(current,dict) or set(current)!=set(maximum) or any(type(v)!=int or not 0<=v<=maximum[k] for k,v in current.items()) or type(wp)!=int or not 0<=wp<=10 or c['kind']!='pc' and wp!=0:
                raise ValueError('Некорректное текущее состояние.')
            c['runtime']={**c.get('runtime',{}),'current':current,'wp':wp}
        elif action=='deleteCharacter':
            if room.get('combat',{}).get('phase')=='combat' and data.get('id') in room.get('combatOwners',{}):raise ValueError('Участник активного боя не удаляется.')
            for item in room.get('items',[]):
                if item['location']==dict(kind='character',id=data.get('id')):
                    item['location']=dict(kind='treasury',id='');item['version']+=1
            room['characters'] = [c for c in room['characters'] if c['id']!=data.get('id')]
            room['tokens']=[t for t in room['tokens'] if t.get('characterId')!=data.get('id')]
            for plan in room.get('locationMaps',[]):
                kept=[t for t in plan.get('tokens',[]) if t.get('characterId')!=data.get('id')]
                history=room.get('locationHistory',{}).get(plan['id'],[])
                referenced=any(t.get('characterId')==data.get('id') for change in history for t in change.get('tokens',[]))
                if referenced or len(kept)!=len(plan.get('tokens',[])):
                    plan['tokens']=kept;plan['version']+=1
                    room.get('locationHistory',{}).pop(plan['id'],None);plan['undoCount']=0
        elif action=='worldLayout':
            layout=data.get('layout')
            if layout not in ('legacy','ravenland'):raise ValueError('Неизвестная сетка.')
            if layout!=room.get('worldLayout','legacy'):
                if room['maps']['world'] or any(t['map']=='world' for t in room['tokens']) or room.get('strongholds') or journey_state(room)['party']:raise ValueError('Создайте новую кампанию: в этой уже размещены места, жетоны или отряд. Смена сетки изменила бы их координаты.')
                room['worldLayout']=layout
                room['journey']['position']={'x':0,'y':0};room['journey']['visited']=[]
                room['journey']['revision']+=1
        elif action=='mapArtwork':
            artwork=room.setdefault('mapArtwork',{'revision':0})
            if data.get('revision')!=artwork['revision']:raise ValueError('Карта изменена другим действием. Повторите выбор.')
            style=data.get('style')
            if style not in ('terrain','reference','upload'):raise ValueError('Неизвестный фон карты.')
            if style=='reference' and not (self.reference_root/'forbidden-lands.jpg').is_file():raise ValueError('Карта Запретных Земель не установлена на сервере.')
            if style=='upload' and not artwork.get('file'):raise ValueError('Сначала загрузите карту кампании.')
            artwork.update(style=style,revision=artwork['revision']+1)
        elif action=='mapLocation':
            x,y=data.get('x'),data.get('y')
            coordinate(data,room)
            site=data.get('siteType')
            if site not in ('landmark','settlement','ruin','castle','cave','none'):raise ValueError('Неизвестный тип места.')
            cell=room['maps']['world'].setdefault(f'{x},{y}',dict(hidden=False))
            cell.update(label=str(data.get('label','')).strip()[:80],note=str(data.get('note',''))[:1500],gmNote=str(data.get('gmNote',''))[:1500],siteType=site,siteHidden=data.get('siteHidden') is True)
        elif action=='paint':
            kind = data.get('map')
            x,y = data.get('x'),data.get('y')
            if kind not in room['maps']:
                raise ValueError('Клетка вне карты.')
            coordinate(data,room if kind=='world' else None)
            terrain = data.get('terrain')
            if terrain not in ('plain','forest','darkforest','hills','highmountain','marsh','water','mountain','wall','rough','road','ruin'):
                raise ValueError('Неизвестная местность.')
            cell=room['maps'][kind].setdefault(f'{x},{y}',{})
            cell.update(terrain=terrain,hidden=data.get('hidden') is True)
        elif action=='token':
            x,y = data.get('x'),data.get('y')
            if data.get('map') not in room['maps']:
                raise ValueError('Клетка вне карты.')
            coordinate(data,room if data.get('map')=='world' else None)
            tid = str(data.get('id') or secrets.token_hex(8))
            old=next((t for t in room['tokens'] if t['id']==tid),None)
            if not gm:
                if not old or old.get('owner')!=s['owner'] or old.get('hidden'):raise PermissionError('Можно двигать только свой видимый жетон.')
                if data['map']!=old['map']:raise PermissionError('Игрок не переносит жетоны между картами.')
                if room['maps'][data['map']].get(f'{x},{y}',{}).get('hidden'):raise ValueError('Клетка ещё не открыта.')
                if data['map']=='battle' and room.get('combat',{}).get('phase')=='combat':raise ValueError('В бою двигайтесь на гексовой карте боя.')
            character=next((c for c in room['characters'] if c['id']==data.get('characterId')),None)
            if gm and data.get('characterId') and not character:raise ValueError('Персонаж не найден.')
            if len(room['tokens'])>=100 and not any(t['id']==tid for t in room['tokens']):
                raise ValueError('Предел: 100 жетонов.')
            room['tokens'] = [t for t in room['tokens'] if t['id']!=tid]+[dict(id=tid,x=x,y=y,map=data['map'],
                                    name=old['name'] if not gm else str(data.get('name') or character and character['name'] or 'Отряд')[:40],
                                    hidden=old.get('hidden',False) if not gm else bool(data.get('hidden')),
                                    characterId=character['id'] if character else old.get('characterId') if old else None,
                                    owner=character['owner'] if character else old.get('owner') if old else s['owner'])]
        elif action=='deleteToken':
            room['tokens']=[t for t in room['tokens'] if t['id']!=data.get('id')]
        elif action=='combatCreate':
            if room.get('combat',{}).get('phase')=='combat':raise ValueError('Сначала завершите текущий бой.')
            choices=data.get('units')
            if not isinstance(choices,list) or not 2<=len(choices)<=10:raise ValueError('Выберите 2–10 бойцов.')
            characters=[];owners={};seen=set()
            for choice in choices:
                if not isinstance(choice,dict):raise ValueError('Некорректный отряд.')
                c=next((c for c in room['characters'] if c['id']==choice.get('id')),None)
                if not c or c.get('hidden') or c['id'] in seen or choice.get('team') not in ('A','B'):raise ValueError('Нужны разные открытые персонажи и отряды A/B.')
                equipped=None
                if c['kind']!='monster':ensure_inventory(room,c['id']);equipped=combat_gear(room,c)
                seen.add(c['id']);characters.append(dict(character=c,team=choice['team'],equipment=equipped));owners[c['id']]=c['owner']
            if len(set(c['team'] for c in characters))!=2:raise ValueError('Нужен хотя бы один боец в каждом отряде.')
            room['combat']=self.engine(dict(create=characters,mapId=data.get('mapId','road')))
            room['combatOwners']=owners;room['combatRevision']=room.get('combatRevision',0)+1
        elif action=='combatAction':
            battle=room.get('combat')
            if not battle:raise ValueError('Бой не подготовлен.')
            if data.get('revision')!=room.get('combatRevision'):raise ValueError('Бой обновился. Повторите действие после синхронизации.')
            cmd=data.get('command',{})
            if not isinstance(cmd,dict):raise ValueError('Некорректная команда.')
            name=cmd.get('action');actor=cmd.get('unit') if name in ('move','defense','initiativeChoose','initiativeOffer','initiativeAccept','initiativeSurprise') else (battle['order'][battle['turn']] if battle['order'] else None)
            pending=battle.get('pendingRisk')
            if pending:
                if name!='risk' or cmd.get('roll')!=pending['id']:raise ValueError('Сначала примите результат броска или пойдите на риск.')
                actor=pending['actor']
                if pending.get('private') and not gm:raise PermissionError('Скрытый бросок завершает Мастер.')
            if not gm:
                if name in ('start','ai','resolve','initiativeSurprise') or not actor or room.get('combatOwners',{}).get(actor)!=s['owner']:raise PermissionError('Вы управляете только своим бойцом.')
                char=next((c for c in room['characters'] if c['id']==actor),None)
                if not char or char['kind']!='pc':raise PermissionError('ПВ и чудовищами управляет Мастер.')
                if name not in ('defense','risk','initiativeChoose','initiativeOffer','initiativeAccept') and battle['phase']=='combat' and actor!=battle['order'][battle['turn']]:raise PermissionError('Сейчас ход другого бойца.')
            private=pending.get('private',False) if pending else dice_visibility(s,data)
            room['combat']=self.engine(dict(battle=battle,command=cmd))
            updated=room['combat']
            if updated.get('pendingRisk'):updated['pendingRisk']['private']=private
            new_logs=updated.pop('commandLog',[])
            updated['publicLog']=(battle.get('publicLog',battle['log'])+([] if private else new_logs))[-300:]
            for roll in updated.pop('diceEvents',[]):
                publish_dice(room,roll['name'],roll['label'],roll['groups'],roll['result'],private,risk=roll.get('risk'))
            sync_wear(room,room['combat'])
            before=next((u for u in battle['units'] if u['id']==actor),None)
            hit_ids=[u['id'] for u in room['combat']['units'] if any(u[k]<next(v for v in battle['units'] if v['id']==u['id'])[k] for k in ('str','agi','wits','emp'))]
            room['combat']['event']=dict(id=secrets.token_hex(8),actor=actor,kind='move' if name=='move' else 'cast' if name=='cast' else 'strike' if name in ('slash','stab','shoot','punch','shove','monsterAttack') else 'idle',target=cmd.get('target'),hitIds=hit_ids,origin=dict(q=before['q'],r=before['r']) if before else None,time=time.time())
            room['combatRevision']+=1
            for c in room['characters']:
                u=next((u for u in room['combat']['units'] if u['id']==c['id']),None)
                if u:c['runtime']={**c.get('runtime',{}),**dict(current=dict(str=u['str'],agi=u['agi'],wit=u['wits'],emp=u['emp']),wp=u['wp'],gearBonus=u['gear'],armor=u['armor'])}
        elif action=='combatManual':
            battle=room.get('combat')
            if not battle or battle['phase']!='combat':raise ValueError('Нет активного боя.')
            if battle.get('pendingRisk'):raise ValueError('Сначала завершите текущий бросок.')
            if data.get('revision')!=room.get('combatRevision'):raise ValueError('Бой обновился. Повторите действие.')
            note=data.get('note');actor=data.get('actor');target=data.get('target');attribute=data.get('attribute');damage=data.get('damage')
            caster=next((u for u in battle['units'] if u['id']==actor),None);victim=next((u for u in battle['units'] if u['id']==target),None)
            if not caster or not victim or not isinstance(note,str) or not note.strip() or len(note)>500 or attribute not in ('str','agi','wits','emp') or type(damage)!=int or not 0<=damage<=100:raise ValueError('Некорректное решение Мастера.')
            if victim.get('monster') and attribute in ('wits','emp'):raise ValueError('Чудовище невосприимчиво к страху и урону Разума/Эмпатии.')
            if data.get('slow',True):
                if battle['order'][battle['turn']]!=actor or caster['slow']<1:raise ValueError('Нет медленного действия у активного бойца.')
                caster['slow']-=1
            wp=data.get('wp',0)
            if type(wp)!=int or wp<0 or wp>caster['wp']:raise ValueError('Недостаточно силы воли.')
            caster['wp']-=wp;victim[attribute]=max(0,victim[attribute]-damage)
            battle['log']=(battle['log']+[f'Мастер: {note.strip()}. {victim["name"]}: {attribute} −{damage}.'])[-300:]
            battle['publicLog']=(battle.get('publicLog',battle['log'][:-1])+[battle['log'][-1]])[-300:]
            battle['event']=dict(id=secrets.token_hex(8),actor=actor,target=target,hitIds=[target] if damage else [],kind='cast',time=time.time())
            room['combatRevision']+=1
            for c in room['characters']:
                u=next((u for u in battle['units'] if u['id']==c['id']),None)
                if u:c['runtime']={**c.get('runtime',{}),**dict(current=dict(str=u['str'],agi=u['agi'],wit=u['wits'],emp=u['emp']),wp=u['wp'],gearBonus=u['gear'],armor=u['armor'])}
        elif action=='combatClose':
            if room.get('combat',{}).get('pendingRisk'):raise ValueError('Сначала завершите текущий бросок.')
            room.pop('combat',None);room.pop('combatOwners',None);room['combatRevision']=room.get('combatRevision',0)+1
        elif action=='event':
            events=['На тропе обнаружены свежие следы большого зверя.', 'Путники просят провести их до ближайшего поселения.',
                    'Над руинами кружат вороны. Изнутри слышен стук.', 'Туман скрывает дорогу; вдали горит одинокий огонь.',
                    'Поток размыл мост. На другом берегу видны следы лагеря.', 'Торговец предлагает обмен, но боится назвать своё имя.']
            room['log'].append(dict(name='Мастер',text=secrets.choice(events)))
        elif action=='chat':
            msg=str(data.get('text','')).strip()[:1000]
            if msg: room['log'].append(dict(name=s['name'],text=msg))
        elif action in ('freePush','freeAccept'):
            free_risk_action(room,s,data)
        elif action=='roll':
            private=dice_visibility(s,data)
            counts=[]
            for key in ('base','skill','gear'):
                n=data.get(key,0)
                if type(n)!=int or not 0<=n<=20:raise ValueError('Пул: от 0 до 20 костей.')
                counts.append(n)
            mod=data.get('modifier',0);artifact_pool=artifact_sides(data)
            if type(mod)!=int or not -10<=mod<=10:raise ValueError('Модификатор: от −10 до +10.')
            counts[1],penalty_count=skill_counts(counts[1],mod)
            pools=[[secrets.randbelow(6)+1 for _ in range(count)] for count in counts]
            penalties=[secrets.randbelow(6)+1 for _ in range(penalty_count)]
            art=[dict(sides=sides,value=secrets.randbelow(sides)+1) for sides in artifact_pool]
            hits=sum(v==6 for v in pools[0]+pools[2])+sum(v==6 for v in pools[1])+sum(max(0,a['value']//2-2) for a in art)
            groups=[dice_group('base',pools[0]),dice_group('skill',pools[1]),dice_group('gear',pools[2]),dice_group('penalty',penalties,negative=True)]
            for sides in (8,10,12):
                values=[a['value'] for a in art if a['sides']==sides]
                if values:groups.append(dice_group('artifact',values,sides))
            roll_id=secrets.token_hex(12)
            r=dict(id=roll_id,private=private,base=pools[0],skillDice=pools[1],gear=pools[2],penalty=penalties,artifacts=art)
            room.setdefault('freeChecks',{})[s['owner']]=r
            publish_dice(room,s['name'],'Свободная проверка',groups,result_text(hits,penalties.count(6)),private,risk=dict(action='free',roll=roll_id,owner=s['owner']))
        else:
            raise ValueError('Неизвестное действие.')
        stamp_entries(room,previous_logs,action)
        room['log']=room['log'][-200:]
        room['revision']+=1
        if action in ('paint','mapArtwork','worldLayout','character','actor','deleteCharacter','assignCharacter','runtime') and room['journey']['phase']=='planning':
            room['journey']['gmReady']=False
        self.save(room)
        return self.view(s)

    def upload_map(self, s, data):
        if s['role']!='gm':raise PermissionError('Карту загружает Мастер.')
        room=self.room(s['room']);art=room.setdefault('mapArtwork',{'revision':0})
        if data.get('revision')!=art['revision']:raise ValueError('Фон уже изменился. Повторите загрузку.')
        try:raw=base64.b64decode(data.get('image',''),validate=True)
        except (ValueError,TypeError,binascii.Error):raise ValueError('Нужен PNG.')
        if not 33<=len(raw)<=4000000 or raw[:8]!=b'\x89PNG\r\n\x1a\n' or raw[12:16]!=b'IHDR':raise ValueError('Нужен PNG до 4 МБ.')
        width,height=int.from_bytes(raw[16:20],'big'),int.from_bytes(raw[20:24],'big')
        if not 1<=width<=3000 or not 1<=height<=3000 or width*height>6000000:raise ValueError('Карта: до 3000 px по стороне и 6 мегапикселей.')
        self.image_root.mkdir(parents=True,exist_ok=True)
        filename=room['id']+'-'+secrets.token_hex(12)+'.png'
        (self.image_root/filename).write_bytes(raw)
        art.update(file=filename,style='upload',revision=art['revision']+1)
        room['revision']+=1;self.save(room)
        return self.view(s)

    def map_image(self, s):
        art=self.room(s['room']).get('mapArtwork',{})
        if art.get('style')=='upload':
            filename=art.get('file','')
            if not filename.startswith(s['room']+'-') or Path(filename).name!=filename:raise ValueError('Карта недоступна.')
            path=self.image_root/filename
        elif art.get('style','reference' if (self.reference_root/'forbidden-lands.jpg').is_file() else 'terrain')=='reference':path=self.reference_root/'forbidden-lands.jpg'
        else:raise ValueError('Фон карты не выбран.')
        if not path.is_file():raise ValueError('Изображение карты недоступно.')
        return path.read_bytes(), 'image/png' if path.suffix=='.png' else 'image/jpeg'

    def engine(self, payload):
        try:
            result=subprocess.run(['node',str(ROOT/'combat-engine.mjs')],input=json.dumps(payload),text=True,
                                  encoding='utf-8',capture_output=True,timeout=8)
        except (OSError,subprocess.TimeoutExpired):raise ValueError('Боевой движок недоступен; проверьте Node.js.')
        if result.returncode:raise ValueError(result.stderr.strip()[:500] or 'Ошибка боевого движка.')
        return json.loads(result.stdout)

def make_handler(game,public_test=False,max_rooms=50,limits=None):
    limiter=limits if limits is not None else RequestLimits()
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup();self.connection.settimeout(15)

        def respond(self, status, body, retry_after=None, conditional=False, cookie=None):
            raw=json.dumps(body,ensure_ascii=False,separators=(',',':')).encode()
            # Hash the authenticated view, including presence and permissions.
            etag='W/"'+hashlib.sha256(raw).hexdigest()+'"' if conditional else None
            if etag and self.headers.get('If-None-Match')==etag:
                self.send_response(304);self.send_header('ETag',etag)
                self.send_header('Cache-Control','private, no-cache');self.send_header('Vary','Authorization, Accept-Encoding')
                self.end_headers();return
            compressed=False
            for encoding in self.headers.get('Accept-Encoding','').split(','):
                parts=encoding.strip().lower().split(';')
                if parts[0]!='gzip':continue
                try:quality=float(next((p.strip()[2:] for p in parts[1:] if p.strip().startswith('q=')),'1'))
                except ValueError:quality=0
                if quality>0 and len(raw)>=1024:
                    raw=gzip.compress(raw,compresslevel=4,mtime=0);compressed=True
                break
            self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(raw)))
            self.send_header('Vary','Authorization, Accept-Encoding')
            if etag:self.send_header('ETag',etag)
            if compressed:self.send_header('Content-Encoding','gzip')
            self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
            if retry_after:self.send_header('Retry-After',str(retry_after))
            if cookie is not None:
                for value in cookie if isinstance(cookie,list) else [cookie]:self.send_header('Set-Cookie',value)
            self.end_headers(); self.wfile.write(raw)

        def account_token(self, name=COOKIE):
            cookies=SimpleCookie()
            try:cookies.load(self.headers.get('Cookie',''))
            except Exception:return ''
            return cookies[name].value if name in cookies else ''

        def account_cookie(self, token, name=COOKIE):
            host=urlparse('http://'+self.headers.get('Host','')).hostname
            secure='' if host in ('127.0.0.1','localhost','::1') else '; Secure'
            age=(SUPPORT_SECONDS if name==SUPPORT_COOKIE else LIFETIME) if token else 0
            return f'{name}={token}; Path=/api; HttpOnly; SameSite=Strict; Max-Age={age}'+secure

        def account_context(self):
            account=game.accounts.authenticate(self.account_token())
            if self.account_token(SUPPORT_COOKIE):
                try:support=game.accounts.authenticate(self.account_token(SUPPORT_COOKIE))
                except PermissionError:return account
                if support.get('actor')==account['id'] and support.get('parent')==account['session']:return support
            return account

        def record_support(self, account, data):
            if account.get('actor'):
                game.admin.audit(account['actor'],account['id'],'supportWrite','Действие в кабинете пользователя',
                                 dict(path=self.path,operation=data.get('action') or data.get('operation'),code=data.get('code'),id=data.get('id')))

        def record_campaign_support(self, session, data):
            if not session.get('account'):return
            row=game.db.execute('SELECT actor FROM account_sessions WHERE token=?',(session['accountSession'],)).fetchone()
            if row and row[0]:
                game.admin.audit(row[0],session['account'],'supportGameAction','Действие в кампании от имени пользователя',
                                 dict(path=self.path,code=session['room'],action=data.get('action') or data.get('operation'),scope=data.get('scope'),id=data.get('id')))

        def limited(self,group):
            if limiter is None:return False
            address=self.client_address[0]
            # This opt-in server sits behind cloudflared; Cloudflare sets this header.
            if public_test and address in ('127.0.0.1','::1'):
                address=self.headers.get('CF-Connecting-IP',address)[:100]
            retry=limiter.retry_after(address,group)
            if retry:self.respond(429,{'error':'Слишком много запросов. Подождите немного и повторите.'},retry)
            return bool(retry)

        def do_POST(self):
            if self.limited('auth' if self.path in ('/api/create','/api/join','/api/resume','/api/account/register','/api/account/login','/api/account/recover','/api/account/password','/api/admin') else 'write'):return
            try:
                cookie=None
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=(5500000 if self.path=='/api/map-image' else 150000): raise ValueError('Некорректный размер запроса.')
                # JSON + same-origin only: browsers cannot submit cross-origin forms to the API.
                if self.headers.get('Content-Type','').split(';')[0]!='application/json':
                    raise ValueError('Ожидается application/json.')
                raw=self.rfile.read(length)
                origin=self.headers.get('Origin')
                if origin and urlparse(origin).netloc!=self.headers.get('Host'): raise PermissionError('Другой origin.')
                if self.headers.get('Sec-Fetch-Site')=='cross-site':raise PermissionError('Другой origin.')
                data=json.loads(raw)
                if not isinstance(data,dict): raise ValueError('Ожидается объект JSON.')
                with LOCK:
                    if self.path in ('/api/account/register','/api/account/login','/api/account/recover'):
                        token,result=game.accounts.auth(self.path.rsplit('/',1)[1],data,self.account_token())
                        game.accounts.logout(self.account_token(SUPPORT_COOKIE))
                        cookie=[self.account_cookie(token),self.account_cookie('',SUPPORT_COOKIE)]
                    elif self.path=='/api/account/logout':
                        game.accounts.logout(self.account_token(SUPPORT_COOKIE))
                        game.accounts.logout(self.account_token());result={'ok':True};cookie=[self.account_cookie(''),self.account_cookie('',SUPPORT_COOKIE)]
                    elif self.path=='/api/account/end-support':
                        account=game.accounts.authenticate(self.account_token())
                        game.admin.require(account)
                        game.accounts.logout(self.account_token(SUPPORT_COOKIE));result={'ok':True};cookie=self.account_cookie('',SUPPORT_COOKIE)
                        game.admin.audit(account['id'],None,'endSupport','Возврат в аккаунт администратора')
                    elif self.path=='/api/admin':
                        account=game.accounts.authenticate(self.account_token())
                        result=game.admin.action(account,data)
                        support_token=result.pop('_supportToken',None)
                        if support_token:
                            game.accounts.logout(self.account_token(SUPPORT_COOKIE))
                            cookie=self.account_cookie(support_token,SUPPORT_COOKIE)
                    elif self.path.startswith('/api/account/'):
                        account=self.account_context()
                        if self.path=='/api/account/password':result=game.accounts.password(account,data)
                        elif self.path=='/api/account/character':result=game.accounts.character(account,data)
                        elif self.path in ('/api/account/create','/api/account/connect'):
                            create=self.path=='/api/account/create'
                            if public_test and create and game.db.execute('SELECT COUNT(*) FROM rooms').fetchone()[0]>=max_rooms:
                                raise ValueError('Тестовый сервер достиг лимита кампаний. Обратитесь к владельцу сервера.')
                            result=game.accounts.campaign(account,data,create)
                        else:raise ValueError('Неизвестное действие кабинета.')
                        self.record_support(account,data)
                    elif self.path in ('/api/create','/api/join'):
                        if public_test and self.path=='/api/create' and game.db.execute('SELECT COUNT(*) FROM rooms').fetchone()[0]>=max_rooms:
                            raise ValueError('Тестовый сервер достиг лимита кампаний. Обратитесь к владельцу сервера.')
                        result=game.login(data,self.path=='/api/create')
                    elif self.path=='/api/resume':
                        account=self.account_context() if self.account_token() else None
                        result=game.accounts.campaign(account,data) if account else game.reconnect(data)
                    elif self.path=='/api/action':
                        session=game.session(self.headers.get('Authorization',''))
                        result=game.action(session,data)
                        self.record_campaign_support(session,data)
                    elif self.path=='/api/saves':
                        session=game.session(self.headers.get('Authorization',''))
                        result=checkpoint_action(game,session,data)
                        self.record_campaign_support(session,data)
                    elif self.path=='/api/map-image':
                        session=game.session(self.headers.get('Authorization',''))
                        result=game.upload_map(session,data)
                        self.record_campaign_support(session,data)
                    elif self.path=='/api/leave':
                        game.sessions.pop(self.headers.get('Authorization',''),None)
                        result={'ok':True}
                    else:
                        self.respond(404,{'error':'Не найдено'}); return
                self.respond(200,result,cookie=cookie)
            except PermissionError as e: self.respond(403,{'error':str(e)})
            except (ValueError,TypeError,KeyError) as e: self.respond(400,{'error':str(e)})

        def do_GET(self):
            # Asset requests from eleven clients must not exhaust campaign polling.
            if self.limited('read' if urlparse(self.path).path.startswith('/api/') else 'static'):return
            if urlparse(self.path).path=='/api/account':
                try:
                    with LOCK:result=game.accounts.dashboard(self.account_context())
                    self.respond(200,result)
                except PermissionError as e:self.respond(403,{'error':str(e)})
                return
            if urlparse(self.path).path=='/api/admin':
                try:
                    with LOCK:result=game.admin.overview(game.accounts.authenticate(self.account_token()))
                    self.respond(200,result)
                except PermissionError as e:self.respond(403,{'error':str(e)})
                return
            if urlparse(self.path).path=='/api/health':
                self.respond(200,{'ok':True,'publicTest':public_test});return
            if urlparse(self.path).path=='/api/map-image':
                try:
                    with LOCK:raw,mime=game.map_image(game.session(self.headers.get('Authorization','')))
                    self.send_response(200);self.send_header('Content-Type',mime)
                    self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
                    self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
                except PermissionError as e:self.respond(403,{'error':str(e)})
                except ValueError as e:self.respond(404,{'error':str(e)})
                return
            if urlparse(self.path).path=='/api/state':
                try:
                    with LOCK: result=game.view(game.session(self.headers.get('Authorization','')))
                    self.respond(200,result,conditional=True)
                except PermissionError as e: self.respond(403,{'error':str(e)})
                return
            target=(ROOT/'public'/urlparse(self.path).path.lstrip('/')).resolve()
            if urlparse(self.path).path=='/': target=ROOT/'public/account.html'
            if not target.is_relative_to((ROOT/'public').resolve()) or not target.is_file():
                self.respond(404,{'error':'Не найдено'}); return
            raw=target.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type',mimetypes.guess_type(target)[0] or 'application/octet-stream')
            self.send_header('Content-Length',str(len(raw)))
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Cache-Control','no-cache');self.send_header('Referrer-Policy','no-referrer')
            self.end_headers(); self.wfile.write(raw)
    return Handler

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--host',default='127.0.0.1'); parser.add_argument('--port',type=int,default=8787)
    parser.add_argument('--database',type=Path,default=ROOT/'campaigns.sqlite')
    parser.add_argument('--reference-root',type=Path,default=ROOT/'local-assets',help='Private reference map directory, outside the application release.')
    parser.add_argument('--public-test',action='store_true',help='Enable request limits and a 50-campaign cap for a test deployment.')
    args=parser.parse_args()
    args.database.parent.mkdir(parents=True,exist_ok=True)
    game=Game(args.database,reference_root=args.reference_root)
    print(f'Open http://{args.host}:{args.port}',flush=True)
    ThreadingHTTPServer((args.host,args.port),make_handler(game,public_test=args.public_test)).serve_forever()
