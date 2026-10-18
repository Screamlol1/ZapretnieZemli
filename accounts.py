"""Persistent accounts, private character library and campaign memberships."""
import hashlib
import json
import re
import secrets
import subprocess
import time
from pathlib import Path

COOKIE = 'zz_account'
LIFETIME = 30 * 86400
ITERATIONS = 600000


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), ITERATIONS).hex()


def password_value(value):
    if not isinstance(value, str) or not 15 <= len(value) <= 128:
        raise ValueError('Пароль: от 15 до 128 символов. Можно использовать длинную фразу.')
    return value


class Accounts:
    def __init__(self, game):
        self.game, self.db = game, game.db
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS accounts (
          id TEXT PRIMARY KEY, login TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
          salt TEXT NOT NULL, password TEXT NOT NULL, recovery TEXT NOT NULL,
          created REAL NOT NULL, failures INTEGER DEFAULT 0, blocked REAL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS account_sessions (
          token TEXT PRIMARY KEY, account TEXT NOT NULL, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS account_memberships (
          account TEXT NOT NULL, room TEXT NOT NULL, owner TEXT NOT NULL,
          resume TEXT NOT NULL, role TEXT NOT NULL, visited REAL NOT NULL,
          PRIMARY KEY(account, room), UNIQUE(room, owner));
        CREATE TABLE IF NOT EXISTS account_characters (
          id TEXT PRIMARY KEY, account TEXT NOT NULL, version INTEGER NOT NULL,
          updated REAL NOT NULL, data TEXT NOT NULL, room TEXT, character TEXT,
          UNIQUE(account, room, character));
        ''')

    def authenticate(self, token):
        row = self.db.execute('SELECT a.id,a.login,a.name,s.token FROM account_sessions s JOIN accounts a ON a.id=s.account WHERE s.token=? AND s.expires>?', (digest(token), time.time())).fetchone()
        if not row:
            raise PermissionError('Войдите в личный кабинет.')
        return dict(id=row[0], login=row[1], name=row[2], session=row[3])

    def valid_session(self, hashed, account):
        return bool(self.db.execute('SELECT 1 FROM account_sessions WHERE token=? AND account=? AND expires>?', (hashed, account, time.time())).fetchone())

    def auth(self, mode, data, old_token=''):
        login = str(data.get('login', '')).strip().lower()
        if not re.fullmatch(r'[a-z0-9_\-.]{3,32}', login):
            raise ValueError('Логин: 3–32 латинские буквы, цифры, точка, дефис или подчёркивание.')
        now = time.time()
        row = self.db.execute('SELECT id,salt,password,recovery,failures,blocked FROM accounts WHERE login=?', (login,)).fetchone()
        recovery = None
        if mode == 'register':
            password = password_value(data.get('password'))
            if row:
                raise ValueError('Этот логин уже занят.')
            name = str(data.get('name') or login).strip()[:60] or login
            aid, salt, recovery = secrets.token_hex(16), secrets.token_hex(16), secrets.token_urlsafe(24)
            self.db.execute('INSERT INTO accounts(id,login,name,salt,password,recovery,created) VALUES(?,?,?,?,?,?,?)', (aid, login, name, salt, password_hash(password, salt), digest(recovery), now))
        else:
            if row and row[5] > now:
                raise PermissionError('Слишком много попыток. Повторите через 15 минут.')
            password = data.get('password', '')
            if not isinstance(password, str) or len(password) > 128:
                raise ValueError('Некорректный пароль.')
            if mode == 'recover':
                good = bool(row and secrets.compare_digest(digest(str(data.get('recovery', ''))), row[3]))
            else:
                hashed = password_hash(password, row[1] if row else '00' * 16)
                good = bool(row and secrets.compare_digest(hashed, row[2]))
            if not good:
                if row:
                    failures = (0 if row[5] and row[5] <= now else row[4]) + 1
                    self.db.execute('UPDATE accounts SET failures=?,blocked=? WHERE id=?', (failures, now + 900 if failures >= 10 else 0, row[0]))
                    self.db.commit()
                raise PermissionError('Неверный логин, пароль или код восстановления.')
            aid = row[0]
            if mode == 'recover':
                password = password_value(password)
                salt, recovery = secrets.token_hex(16), secrets.token_urlsafe(24)
                self.db.execute('UPDATE accounts SET salt=?,password=?,recovery=? WHERE id=?', (salt, password_hash(password, salt), digest(recovery), aid))
                self.db.execute('DELETE FROM account_sessions WHERE account=?', (aid,))
            self.db.execute('UPDATE accounts SET failures=0,blocked=0 WHERE id=?', (aid,))
        token = secrets.token_urlsafe(32)
        self.db.execute('DELETE FROM account_sessions WHERE expires<=? OR token=?', (now, digest(old_token)))
        self.db.execute('INSERT INTO account_sessions VALUES(?,?,?)', (digest(token), aid, now + LIFETIME))
        self.db.commit()
        return token, {'ok': True, **({'recovery': recovery} if recovery else {})}

    def logout(self, token):
        self.db.execute('DELETE FROM account_sessions WHERE token=?', (digest(token),))
        self.db.commit()

    def password(self, account, data):
        row = self.db.execute('SELECT salt,password FROM accounts WHERE id=?', (account['id'],)).fetchone()
        current = data.get('currentPassword', '')
        if not isinstance(current, str) or len(current) > 128 or not secrets.compare_digest(password_hash(current, row[0]), row[1]):
            raise PermissionError('Текущий пароль неверен.')
        salt, recovery = secrets.token_hex(16), secrets.token_urlsafe(24)
        self.db.execute('UPDATE accounts SET salt=?,password=?,recovery=? WHERE id=?', (salt, password_hash(password_value(data.get('password')), salt), digest(recovery), account['id']))
        self.db.execute('DELETE FROM account_sessions WHERE account=? AND token<>?', (account['id'], account['session']))
        self.db.commit()
        return {'ok': True, 'recovery': recovery}

    def membership(self, account, code):
        return self.db.execute('SELECT owner,resume,role FROM account_memberships WHERE account=? AND room=?', (account['id'], code)).fetchone()

    def campaign(self, account, data, create=False):
        code = str(data.get('code', '')).strip().upper()
        member = None if create else self.membership(account, code)
        args = dict(data, name=account['name'], code=code)
        if member:
            room = self.game.room(code)
            args.update(resume=member[1], key=room['gmKey'] if member[2] == 'gm' else room['playerKey'])
        elif not create and args.get('resume'):
            room = self.game.room(code)
            identity = room.get('identities', {}).get(str(args['resume']))
            if identity:
                args['key'] = room['gmKey'] if identity['role'] == 'gm' else room['playerKey']
        result = self.game.login(args, create, account=account)
        s = self.game.sessions[result['token']]
        self.db.execute('INSERT INTO account_memberships VALUES(?,?,?,?,?,?) ON CONFLICT(account,room) DO UPDATE SET visited=excluded.visited', (account['id'], s['room'], s['owner'], s['resume'], s['role'], time.time()))
        self.db.commit()
        return result

    def snapshot(self, room, character):
        # A player's library must never carry GM notes or unrevealed inventory.
        from inventory_rules import public_items
        s = dict(role='player', owner=character['owner'])
        return dict(sheet=character['sheet'], runtime=character.get('runtime', {}),
                    visual=character.get('visual'), equipment=character.get('equipment', {}),
                    items=[i for i in public_items(room, s) if i.get('location') == dict(kind='character', id=character['id'])])

    def sync(self, room):
        for lid, aid, cid, old in self.db.execute('SELECT id,account,character,data FROM account_characters WHERE room=?', (room['id'],)).fetchall():
            member = self.db.execute('SELECT owner FROM account_memberships WHERE account=? AND room=?', (aid, room['id'])).fetchone()
            c = next((c for c in room['characters'] if c['id'] == cid and c['kind'] == 'pc' and member and c['owner'] == member[0]), None)
            if not c:
                self.db.execute('UPDATE account_characters SET room=NULL,character=NULL,version=version+1 WHERE id=?', (lid,))
                continue
            raw = json.dumps(self.snapshot(room, c), sort_keys=True)
            if json.loads(old) != json.loads(raw):
                self.db.execute('UPDATE account_characters SET data=?,version=version+1,updated=? WHERE id=?', (raw, time.time(), lid))

    def dashboard(self, account):
        campaigns = []
        for code, role, visited in self.db.execute('SELECT room,role,visited FROM account_memberships WHERE account=? ORDER BY visited DESC', (account['id'],)).fetchall():
            room = self.game.room(code)
            self.sync(room)
            member = self.membership(account, code)
            campaigns.append(dict(code=code, title=room['title'], role=role, visited=visited, savedAt=room.get('savedAt'),
                characters=[dict(id=c['id'], name=c['name']) for c in room['characters'] if c['kind'] == 'pc' and c['owner'] == member[0]]))
        self.db.commit()
        characters = [dict(id=r[0], version=r[1], updated=r[2], **json.loads(r[3]), campaign=r[4], character=r[5]) for r in self.db.execute('SELECT id,version,updated,data,room,character FROM account_characters WHERE account=? ORDER BY updated DESC', (account['id'],))]
        return dict(profile={k: account[k] for k in ('login', 'name')}, campaigns=campaigns, characters=characters, limit=10)

    def character(self, account, data):
        action, lid = data.get('action'), str(data.get('id', ''))
        row = self.db.execute('SELECT version,data,room,character FROM account_characters WHERE id=? AND account=?', (lid, account['id'])).fetchone() if lid else None
        if lid and not row:
            raise PermissionError('Персонаж не найден в вашем кабинете.')
        if row and data.get('version') != row[0]:
            raise ValueError('Лист изменился в другой вкладке или кампании. Закройте редактор и откройте свежую версию.')
        if action == 'delete':
            if not row: raise ValueError('Выберите персонажа.')
            self.db.execute('DELETE FROM account_characters WHERE id=?', (lid,))
            self.db.commit()
            return {'ok': True}
        if action == 'deploy':
            if not row: raise ValueError('Выберите персонажа.')
            code = str(data.get('code', '')).upper()
            member = self.membership(account, code)
            if not member: raise PermissionError('Сначала подключитесь к кампании.')
            if row[2]:
                if row[2] != code: raise ValueError('Герой уже в другой кампании. Создайте отдельную копию листа.')
                return {'ok': True, 'character': row[3]}
            cid = secrets.token_hex(8)
            self.game.action(dict(room=code, role='player', owner=member[0], name=account['name']), dict(action='character', id=cid, sheet=json.loads(row[1])['sheet']))
            self.db.execute('UPDATE account_characters SET room=?,character=? WHERE id=?', (code, cid, lid))
            self.sync(self.game.room(code)); self.db.commit()
            return {'ok': True, 'character': cid}
        if action == 'capture':
            code = str(data.get('code', '')).upper()
            member = self.membership(account, code)
            if not member: raise PermissionError('Кампания не привязана к аккаунту.')
            room = self.game.room(code)
            c = next((c for c in room['characters'] if c['id'] == data.get('character') and c['owner'] == member[0] and c['kind'] == 'pc'), None)
            if not c: raise PermissionError('Вы можете сохранить только своего героя.')
            existing = self.db.execute('SELECT id FROM account_characters WHERE account=? AND room=? AND character=?', (account['id'], code, c['id'])).fetchone()
            if existing: return {'id': existing[0]}
            payload = self.snapshot(room, c)
            source = (code, c['id'])
        elif action == 'save':
            sheet = data.get('sheet')
            if not isinstance(sheet, dict) or len(json.dumps(sheet)) > 100000:
                raise ValueError('Нужен лист из конструктора персонажей.')
            try:
                checked = subprocess.run(['node', str(Path(__file__).parent/'validate-sheet.mjs')], input=json.dumps(sheet), text=True, capture_output=True, encoding='utf-8', timeout=8)
            except (OSError, subprocess.TimeoutExpired):
                raise ValueError('Не удалось проверить лист. Проверьте Node.js.')
            if checked.returncode: raise ValueError(checked.stderr.strip()[:300] or 'Некорректный лист.')
            sheet = json.loads(checked.stdout)['sheet']
            if row and row[2]:
                member = self.membership(account, row[2])
                room = self.game.room(row[2])
                if not member or not any(c['id'] == row[3] and c['owner'] == member[0] for c in room['characters']):
                    raise PermissionError('Владелец героя изменился. Обновите кабинет.')
                self.game.action(dict(room=row[2], role='player', owner=member[0], name=account['name']), dict(action='character', id=row[3], sheet=sheet))
                return {'id': lid}
            payload = dict(sheet=sheet)
            source = (None, None)
        else:
            raise ValueError('Неизвестное действие с персонажем.')
        if not row and self.db.execute('SELECT count(*) FROM account_characters WHERE account=?', (account['id'],)).fetchone()[0] >= 10:
            raise ValueError('В кабинете уже 10 персонажей. Скачайте и удалите ненужный лист перед созданием нового.')
        lid = lid or secrets.token_hex(16)
        if row:
            self.db.execute('UPDATE account_characters SET data=?,version=version+1,updated=? WHERE id=?', (json.dumps(payload), time.time(), lid))
        else:
            self.db.execute('INSERT INTO account_characters VALUES(?,?,?,?,?,?,?)', (lid, account['id'], 1, time.time(), json.dumps(payload), *source))
        self.db.commit()
        return {'id': lid}
