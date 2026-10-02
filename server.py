"""Campaign server. Python 3.11+, no third-party dependencies."""
import argparse
import json
import mimetypes
import secrets
import sqlite3
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from campaign_rules import apply as campaign_action, state as journey_state

ROOT = Path(__file__).parent
LOCK = threading.RLock()

class Game:
    def __init__(self, database):
        self.db = sqlite3.connect(database, check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS rooms (id TEXT PRIMARY KEY, data TEXT)')
        self.sessions = {}

    def save(self, room):
        self.db.execute('INSERT OR REPLACE INTO rooms VALUES (?,?)', (room['id'], json.dumps(room)))
        self.db.commit()

    def room(self, code):
        row = self.db.execute('SELECT data FROM rooms WHERE id=?', (code,)).fetchone()
        if not row:
            raise ValueError('Кампания не найдена.')
        return json.loads(row[0])

    def login(self, data, create=False):
        name = str(data.get('name', '')).strip()[:60]
        if not name:
            raise ValueError('Укажите имя участника.')
        if create:
            code = secrets.token_hex(4).upper()
            key = secrets.token_urlsafe(24)
            room = dict(id=code, title=str(data.get('title') or 'Новая экспедиция')[:100],
                        gmKey=key, playerKey=secrets.token_urlsafe(18), revision=0,
                        characters=[], maps={'world': {}, 'battle': {}}, tokens=[], log=[], identities={})
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
        self.save(room)
        for t in [t for t,x in self.sessions.items() if x['room']==room['id'] and x['owner']==owner]:
            del self.sessions[t]
        self.sessions[token] = dict(room=room['id'], role=role, name=name, owner=owner, resume=resume, seen=time.time())
        return dict(token=token, resume=resume, code=room['id'], role=role,
                    gmKey=room['gmKey'] if role=='gm' else None,
                    playerKey=room['playerKey'] if role=='gm' else None)

    def session(self, token):
        s = self.sessions.get(token)
        if not s or time.time()-s['seen']>=45:
            raise PermissionError('Войдите в кампанию.')
        s['seen'] = time.time()
        return s

    def view(self, s):
        room = self.room(s['room'])
        journey_state(room)
        identities=room.get('identities',{})
        room.pop('gmKey'); room.pop('playerKey')
        room.pop('identities',None)
        if s['role']=='gm':
            room['owners']=[dict(owner=x['owner'],name=x.get('name','Участник'),role=x['role']) for x in identities.values()]
        room.pop('combatOwners',None)
        room['characters'] = [c if s['role']=='gm' or c['owner']==s['owner'] and c['kind']=='pc' else
                              {**{k:v for k,v in c.items() if k in ('id','owner','name','kind','visual')},'kin':c.get('sheet',{}).get('kin')} for c in room['characters']
                              if s['role']=='gm' or not c.get('hidden')]
        if s['role']!='gm':
            room['journey']['pendingCount']=len(room['journey']['pending'])
            room['journey']['pending']=[]
            room['journey']['history']=[e for e in room['journey']['history'] if not e.get('private')]
            room['tokens'] = [t for t in room['tokens'] if not t.get('hidden')]
            room['maps'] = {kind:{k:v for k,v in cells.items() if not v.get('hidden')} for kind,cells in room['maps'].items()}
            for u in room.get('combat',{}).get('units',[]):
                if u.get('monster'):u['monster']={}
        room['members'] = [dict(name=x['name'], role=x['role'], owner=x['owner']) for x in self.sessions.values()
                           if x['room']==s['room'] and time.time()-x['seen']<45]
        room['me'] = dict(role=s['role'], owner=s['owner'], name=s['name'])
        return room

    def action(self, s, data):
        room = self.room(s['room'])
        action = data.get('action')
        gm = s['role']=='gm'
        if action in ('paint','event','deleteCharacter','assignCharacter','deleteToken','combatCreate','combatClose','actor','combatManual') and not gm:
            raise PermissionError('Действие доступно только Мастеру.')
        if isinstance(action,str) and (action.startswith('travel') or action.startswith('hold')):
            campaign_action(room,s,data)
        elif action=='character':
            sheet = data.get('sheet')
            if not isinstance(sheet, dict) or sheet.get('game')!='forbidden-lands' or not isinstance(sheet.get('name'),str):
                raise ValueError('Нужен JSON из конструктора персонажей.')
            if len(json.dumps(sheet))>100000:
                raise ValueError('Лист слишком большой.')
            try:
                checked = subprocess.run(['node',str(ROOT/'validate-sheet.mjs')],input=json.dumps(sheet),
                                         text=True,capture_output=True,encoding='utf-8',timeout=8)
            except (OSError,subprocess.TimeoutExpired):
                raise ValueError('Не удалось проверить лист: необходим Node.js.')
            if checked.returncode:
                raise ValueError(checked.stderr.strip()[:300] or 'Некорректный лист.')
            sheet=json.loads(checked.stdout)
            cid = str(data.get('id') or secrets.token_hex(8))
            old = next((c for c in room['characters'] if c['id']==cid),None)
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
            c['runtime']=old.get('runtime',{}) if old else dict(current=sheet['attrs'].copy(),wp=0)
            if old and 'visual' in old:c['visual']=old['visual']
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
            if actor['kind']=='npc':actor['runtime']=dict(current=actor['sheet']['attrs'].copy(),wp=0)
            else:actor['runtime']=dict(current=dict(str=actor['monster']['strength'],agi=actor['monster']['agility'],wit=1,emp=1),wp=0)
            if old and old['kind']==actor['kind']:
                actor['runtime']={**old.get('runtime',{}),**actor['runtime']}
                actor['runtime']['current']={k:min(old.get('runtime',{}).get('current',{}).get(k,v),v) for k,v in actor['runtime']['current'].items()}
            room['characters']=[c for c in room['characters'] if c['id']!=actor['id']]+[actor]
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
            room['characters'] = [c for c in room['characters'] if c['id']!=data.get('id')]
            room['tokens']=[t for t in room['tokens'] if t.get('characterId')!=data.get('id')]
        elif action=='paint':
            kind = data.get('map')
            x,y = data.get('x'),data.get('y')
            if kind not in room['maps'] or type(x)!=int or type(y)!=int or not 0<=x<24 or not 0<=y<16:
                raise ValueError('Клетка вне карты.')
            terrain = data.get('terrain')
            if terrain not in ('plain','forest','darkforest','hills','highmountain','marsh','water','mountain','wall','rough','road','ruin'):
                raise ValueError('Неизвестная местность.')
            room['maps'][kind][f'{x},{y}'] = dict(terrain=terrain,hidden=bool(data.get('hidden')))
        elif action=='token':
            x,y = data.get('x'),data.get('y')
            if type(x)!=int or type(y)!=int or not 0<=x<24 or not 0<=y<16 or data.get('map') not in room['maps']:
                raise ValueError('Клетка вне карты.')
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
                seen.add(c['id']);characters.append(dict(character=c,team=choice['team']));owners[c['id']]=c['owner']
            if len(set(c['team'] for c in characters))!=2:raise ValueError('Нужен хотя бы один боец в каждом отряде.')
            room['combat']=self.engine(dict(create=characters,mapId=data.get('mapId','road')))
            room['combatOwners']=owners;room['combatRevision']=room.get('combatRevision',0)+1
        elif action=='combatAction':
            battle=room.get('combat')
            if not battle:raise ValueError('Бой не подготовлен.')
            if data.get('revision')!=room.get('combatRevision'):raise ValueError('Бой обновился. Повторите действие после синхронизации.')
            cmd=data.get('command',{})
            if not isinstance(cmd,dict):raise ValueError('Некорректная команда.')
            name=cmd.get('action');actor=cmd.get('unit') if name in ('move','defense') else (battle['order'][battle['turn']] if battle['order'] else None)
            if not gm:
                if name in ('start','ai','resolve') or not actor or room.get('combatOwners',{}).get(actor)!=s['owner']:raise PermissionError('Вы управляете только своим бойцом.')
                char=next((c for c in room['characters'] if c['id']==actor),None)
                if not char or char['kind']!='pc':raise PermissionError('ПВ и чудовищами управляет Мастер.')
                if name!='defense' and battle['phase']=='combat' and actor!=battle['order'][battle['turn']]:raise PermissionError('Сейчас ход другого бойца.')
            room['combat']=self.engine(dict(battle=battle,command=cmd))
            before=next((u for u in battle['units'] if u['id']==actor),None)
            hit_ids=[u['id'] for u in room['combat']['units'] if any(u[k]<next(v for v in battle['units'] if v['id']==u['id'])[k] for k in ('str','agi','wits','emp'))]
            room['combat']['event']=dict(id=secrets.token_hex(8),actor=actor,kind='move' if name=='move' else 'cast' if name=='cast' else 'strike' if name in ('slash','stab','shoot','punch','shove','monsterAttack') else 'idle',target=cmd.get('target'),hitIds=hit_ids,origin=dict(q=before['q'],r=before['r']) if before else None,time=time.time())
            room['combatRevision']+=1
            for c in room['characters']:
                u=next((u for u in room['combat']['units'] if u['id']==c['id']),None)
                if u:c['runtime']=dict(current=dict(str=u['str'],agi=u['agi'],wit=u['wits'],emp=u['emp']),wp=u['wp'],gearBonus=u['gear'],armor=u['armor'])
        elif action=='combatManual':
            battle=room.get('combat')
            if not battle or battle['phase']!='combat':raise ValueError('Нет активного боя.')
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
            battle['event']=dict(id=secrets.token_hex(8),actor=actor,target=target,hitIds=[target] if damage else [],kind='cast',time=time.time())
            room['combatRevision']+=1
            for c in room['characters']:
                u=next((u for u in battle['units'] if u['id']==c['id']),None)
                if u:c['runtime']=dict(current=dict(str=u['str'],agi=u['agi'],wit=u['wits'],emp=u['emp']),wp=u['wp'],gearBonus=u['gear'],armor=u['armor'])
        elif action=='combatClose':
            room.pop('combat',None);room.pop('combatOwners',None);room['combatRevision']=room.get('combatRevision',0)+1
        elif action=='event':
            events=['На тропе обнаружены свежие следы большого зверя.', 'Путники просят провести их до ближайшего поселения.',
                    'Над руинами кружат вороны. Изнутри слышен стук.', 'Туман скрывает дорогу; вдали горит одинокий огонь.',
                    'Поток размыл мост. На другом берегу видны следы лагеря.', 'Торговец предлагает обмен, но боится назвать своё имя.']
            room['log'].append(dict(name='Мастер',text=secrets.choice(events)))
        elif action=='chat':
            msg=str(data.get('text','')).strip()[:1000]
            if msg: room['log'].append(dict(name=s['name'],text=msg))
        elif action=='roll':
            pools=[]
            for key in ('base','skill','gear'):
                n=data.get(key,0)
                if type(n)!=int or not 0<=n<=20: raise ValueError('Пул: от 0 до 20 костей.')
                pools.append([secrets.randbelow(6)+1 for _ in range(n)])
            mod=data.get('modifier',0)
            if type(mod)!=int or not -10<=mod<=10: raise ValueError('Модификатор: от −10 до +10.')
            n=data.get('skill',0)+mod
            pools[1]=[secrets.randbelow(6)+1 for _ in range(abs(n))]
            hits=sum(v==6 for v in pools[0]+pools[2])+sum(v==6 for v in pools[1])*(1 if n>=0 else -1)
            room['log'].append(dict(name=s['name'],text=f'Проверка: база {pools[0]}, навык {pools[1]}'+
                                   (' (отрицательные)' if n<0 else '')+f', снаряжение {pools[2]}. Успехов: {max(0,hits)}.'))
        else:
            raise ValueError('Неизвестное действие.')
        room['log']=room['log'][-200:]
        room['revision']+=1
        self.save(room)
        return self.view(s)

    def engine(self, payload):
        try:
            result=subprocess.run(['node',str(ROOT/'combat-engine.mjs')],input=json.dumps(payload),text=True,
                                  encoding='utf-8',capture_output=True,timeout=8)
        except (OSError,subprocess.TimeoutExpired):raise ValueError('Боевой движок недоступен; проверьте Node.js.')
        if result.returncode:raise ValueError(result.stderr.strip()[:500] or 'Ошибка боевого движка.')
        return json.loads(result.stdout)

def make_handler(game):
    class Handler(BaseHTTPRequestHandler):
        def respond(self, status, body):
            raw=json.dumps(body,ensure_ascii=False).encode()
            self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(raw)))
            self.end_headers(); self.wfile.write(raw)

        def do_POST(self):
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=150000: raise ValueError('Некорректный размер запроса.')
                # JSON + same-origin only: browsers cannot submit cross-origin forms to the API.
                if self.headers.get('Content-Type','').split(';')[0]!='application/json':
                    raise ValueError('Ожидается application/json.')
                origin=self.headers.get('Origin')
                if origin and urlparse(origin).netloc!=self.headers.get('Host'): raise PermissionError('Другой origin.')
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict): raise ValueError('Ожидается объект JSON.')
                with LOCK:
                    if self.path in ('/api/create','/api/join'):
                        result=game.login(data,self.path=='/api/create')
                    elif self.path=='/api/action':
                        result=game.action(game.session(self.headers.get('Authorization','')),data)
                    elif self.path=='/api/leave':
                        game.sessions.pop(self.headers.get('Authorization',''),None)
                        result={'ok':True}
                    else:
                        self.respond(404,{'error':'Не найдено'}); return
                self.respond(200,result)
            except PermissionError as e: self.respond(403,{'error':str(e)})
            except (ValueError,TypeError,KeyError) as e: self.respond(400,{'error':str(e)})

        def do_GET(self):
            if urlparse(self.path).path=='/api/state':
                try:
                    with LOCK: result=game.view(game.session(self.headers.get('Authorization','')))
                    self.respond(200,result)
                except PermissionError as e: self.respond(403,{'error':str(e)})
                return
            target=(ROOT/'public'/urlparse(self.path).path.lstrip('/')).resolve()
            if urlparse(self.path).path=='/': target=ROOT/'public/index.html'
            if not target.is_relative_to((ROOT/'public').resolve()) or not target.is_file():
                self.respond(404,{'error':'Не найдено'}); return
            raw=target.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type',mimetypes.guess_type(target)[0] or 'application/octet-stream')
            self.send_header('Content-Length',str(len(raw)))
            self.send_header('X-Content-Type-Options','nosniff')
            self.end_headers(); self.wfile.write(raw)
    return Handler

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--host',default='127.0.0.1'); parser.add_argument('--port',type=int,default=8787)
    args=parser.parse_args()
    game=Game(ROOT/'campaigns.sqlite')
    print(f'Open http://{args.host}:{args.port}',flush=True)
    ThreadingHTTPServer((args.host,args.port),make_handler(game)).serve_forever()
