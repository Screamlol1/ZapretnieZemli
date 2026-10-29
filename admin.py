"""Explicit administrator operations. Never returns password hashes or login tokens."""
import json
import secrets
import time
from accounts import digest, password_hash

SUPPORT_COOKIE = 'zz_support'
SUPPORT_SECONDS = 900


class Administration:
    def __init__(self, game):
        self.game, self.db, self.accounts = game, game.db, game.accounts

    def require(self, account):
        # Read current privileges; a previously authenticated Python dict is not authority.
        row=self.db.execute('SELECT admin,disabled FROM accounts WHERE id=?',(account['id'],)).fetchone()
        if not row or not row[0] or row[1] or account.get('actor') or not self.accounts.valid_session(account['session'],account['id']):
            raise PermissionError('Требуются права администратора.')

    def audit(self, actor, target, action, reason, details=None):
        self.db.execute('INSERT INTO admin_audit(created,actor,target,action,reason,details) VALUES(?,?,?,?,?,?)',
                        (time.time(),actor,target,action,str(reason)[:500],json.dumps(details or {},ensure_ascii=False)))
        self.db.commit()

    def overview(self, account):
        self.require(account)
        users=[]
        for r in self.db.execute('''SELECT a.id,a.login,a.name,a.admin,a.disabled,a.created,a.blocked,
          (SELECT COUNT(*) FROM account_characters c WHERE c.account=a.id),
          (SELECT COUNT(*) FROM account_memberships m WHERE m.account=a.id),
          (SELECT COUNT(*) FROM account_sessions s WHERE s.account=a.id AND s.expires>?)
          FROM accounts a ORDER BY a.created DESC''',(time.time(),)):
            users.append(dict(zip(('id','login','name','admin','disabled','created','blocked','characters','campaigns','sessions'),r)))
        campaigns=[]
        for raw, in self.db.execute('SELECT data FROM rooms'):
            room=json.loads(raw);journey=room.get('journey',{})
            campaigns.append(dict(code=room['id'],title=room['title'],characters=len(room.get('characters',[])),savedAt=room.get('savedAt'),day=journey.get('day',1),quarter=journey.get('quarter',0)))
        audit=[dict(id=r[0],created=r[1],actor=r[2],target=r[3],action=r[4],reason=r[5],details=json.loads(r[6])) for r in self.db.execute('SELECT id,created,actor,target,action,reason,details FROM admin_audit ORDER BY id DESC LIMIT 200')]
        return dict(accounts=users,campaigns=campaigns,audit=audit,self=account['id'],supportMinutes=15)

    def detail(self, account, target):
        self.require(account)
        row=self.db.execute('SELECT id,login,name,admin,disabled FROM accounts WHERE id=?',(target,)).fetchone()
        if not row:raise ValueError('Аккаунт не найден.')
        subject=dict(id=row[0],login=row[1],name=row[2],admin=bool(row[3]))
        result=self.accounts.dashboard(subject)
        self.audit(account['id'],target,'inspect','Просмотр кабинета администратором')
        return dict(**result,disabled=bool(row[4]))

    def action(self, account, data):
        self.require(account)
        target=str(data.get('target',''))
        operation=data.get('operation')
        if operation=='inspect':return self.detail(account,target)
        if operation not in ('block','unblock','unlock','revoke','resetPassword','grantAdmin','revokeAdmin','support'):
            raise ValueError('Неизвестная операция администратора.')
        reason=str(data.get('reason','')).strip()
        if len(reason)<5 or len(reason)>500:raise ValueError('Укажите причину: от 5 до 500 символов.')
        subject=self.db.execute('SELECT id,login,admin,disabled FROM accounts WHERE id=?',(target,)).fetchone()
        if not subject:raise ValueError('Аккаунт не найден.')
        if target==account['id']:raise ValueError('Для своего аккаунта используйте настройки кабинета. Самоблокировка и снятие своих прав запрещены.')
        result={'ok':True}
        with self.db:
            if operation in ('block','revokeAdmin') and subject[2] and not subject[3] and self.db.execute('SELECT COUNT(*) FROM accounts WHERE admin=1 AND disabled=0').fetchone()[0]<=1:
                raise ValueError('Нельзя отключить последнего администратора.')
            if operation=='block':self.db.execute('UPDATE accounts SET disabled=1 WHERE id=?',(target,))
            elif operation=='unblock':self.db.execute('UPDATE accounts SET disabled=0,failures=0,blocked=0 WHERE id=?',(target,))
            elif operation=='unlock':self.db.execute('UPDATE accounts SET failures=0,blocked=0 WHERE id=?',(target,))
            elif operation in ('grantAdmin','revokeAdmin'):self.db.execute('UPDATE accounts SET admin=? WHERE id=?',(int(operation=='grantAdmin'),target))
            elif operation=='resetPassword':
                new_password=secrets.token_urlsafe(24);recovery=secrets.token_urlsafe(24);salt=secrets.token_hex(16)
                self.db.execute('UPDATE accounts SET salt=?,password=?,recovery=?,failures=0,blocked=0 WHERE id=?',(salt,password_hash(new_password,salt),digest(recovery),target))
                result.update(password=new_password,recovery=recovery,login=subject[1])
            elif operation=='support':
                if subject[2] or subject[3]:raise ValueError('Вход поддержки доступен только в активный обычный аккаунт.')
                token=secrets.token_urlsafe(32)
                self.db.execute('INSERT INTO account_sessions(token,account,expires,actor,parent) VALUES(?,?,?,?,?)',(digest(token),target,time.time()+SUPPORT_SECONDS,account['id'],account['session']))
                result['_supportToken']=token
            if operation in ('block','revoke','resetPassword','revokeAdmin'):
                self.db.execute('DELETE FROM account_sessions WHERE account=? OR actor=?',(target,target))
            self.db.execute('INSERT INTO admin_audit(created,actor,target,action,reason,details) VALUES(?,?,?,?,?,?)',(time.time(),account['id'],target,operation,reason,'{}'))
        return result
