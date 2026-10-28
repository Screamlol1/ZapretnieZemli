import json
import time
import unittest
import test_accounts as support
PASSWORD=support.PASSWORD
from accounts import digest


class AdminTests(unittest.TestCase):
    setUp=support.AccountTests.setUp
    tearDown=support.AccountTests.tearDown
    serve=support.AccountTests.serve
    request=support.AccountTests.request
    other=support.AccountTests.other

    def administrator(self):
        self.game.db.execute('UPDATE accounts SET admin=1 WHERE id=?',(self.account['id'],));self.game.db.commit()
        self.account=self.a.authenticate(self.token)
        return self.account

    def command(self, operation, target, **data):
        return self.game.admin.action(self.account,dict(dict(operation=operation,target=target['id'],reason='Проверка функции администратора'),**data))

    def test_signup_cannot_self_promote_and_all_admin_endpoints_check_role(self):
        token,_=self.a.auth('register',dict(login='pretender',password=PASSWORD,admin=True,role='admin'))
        user=self.a.authenticate(token)
        self.assertFalse(user['admin'])
        with self.assertRaises(PermissionError):self.game.admin.overview(user)
        with self.assertRaises(PermissionError):self.game.admin.action(user,dict(operation='inspect',target=self.account['id']))
        self.serve()
        self.assertEqual(self.request('/api/admin',Cookie='zz_account='+token)[0],403)
        self.assertEqual(self.request('/api/admin')[0],403)
        self.assertEqual(self.request('/api/admin',dict(operation='block',target=self.account['id']),Cookie='zz_account='+token)[0],403)

    def test_list_inspect_never_return_credentials_and_actions_need_only_active_admin_session(self):
        self.administrator();other=self.other()
        snapshot=self.game.admin.overview(self.account)
        self.assertEqual(len(snapshot['accounts']),2)
        serialized=json.dumps(snapshot)
        for marker in ('salt','password','recovery',self.token):self.assertNotIn(marker,serialized)
        self.assertEqual(self.command('inspect',other)['profile']['login'],other['login'])
        self.command('block',other)
        self.assertEqual(self.game.db.execute('SELECT disabled FROM accounts WHERE id=?',(other['id'],)).fetchone()[0],1)
        self.command('unblock',other)
        with self.assertRaises(ValueError):self.command('block',self.account)
        self.a.logout(self.token)
        with self.assertRaises(PermissionError):self.command('block',other)

    def test_block_revoke_reset_and_audit(self):
        self.administrator();other=self.other()
        campaign=self.a.campaign(other,dict(title='Админ-тест'),True)
        self.command('block',other)
        with self.assertRaises(PermissionError):self.game.session(campaign['token'])
        with self.assertRaises(PermissionError):self.a.auth('login',dict(login=other['login'],password=PASSWORD))
        self.command('unblock',other)
        self.a.auth('login',dict(login=other['login'],password=PASSWORD))
        reset=self.command('resetPassword',other)
        with self.assertRaises(PermissionError):self.a.auth('login',dict(login=other['login'],password=PASSWORD))
        token,_=self.a.auth('login',dict(login=other['login'],password=reset['password']))
        self.assertTrue(self.a.authenticate(token))
        self.command('revoke',other)
        with self.assertRaises(PermissionError):self.a.authenticate(token)
        audit=json.dumps(self.game.admin.overview(self.account)['audit'])
        self.assertNotIn(reset['password'],audit);self.assertNotIn(reset['recovery'],audit)
        self.assertIn('resetPassword',audit)

    def test_support_has_target_permissions_expiry_and_parent_revocation(self):
        self.administrator();other=self.other()
        token=self.command('support',other)['_supportToken'];support=self.a.authenticate(token)
        self.assertEqual(support['id'],other['id']);self.assertEqual(support['actor'],self.account['id'])
        self.assertFalse(support['admin'])
        with self.assertRaises(PermissionError):self.game.admin.overview(support)
        with self.assertRaises(PermissionError):self.a.password(support,dict(currentPassword=PASSWORD,password=PASSWORD+'new'))
        self.game.db.execute('UPDATE account_sessions SET expires=? WHERE token=?',(time.time()-1,digest(token)));self.game.db.commit()
        with self.assertRaises(PermissionError):self.a.authenticate(token)
        token=self.command('support',other)['_supportToken']
        self.a.logout(self.token)
        with self.assertRaises(PermissionError):self.a.authenticate(token)

    def test_role_changes_do_not_allow_support_into_admin_or_self_demotion(self):
        self.administrator();other=self.other()
        self.command('grantAdmin',other)
        with self.assertRaises(ValueError):self.command('support',other)
        with self.assertRaises(ValueError):self.command('revokeAdmin',self.account)
        self.command('revokeAdmin',other)
        self.assertEqual(self.game.db.execute('SELECT admin FROM accounts WHERE id=?',(other['id'],)).fetchone()[0],0)

    def test_http_support_cookie_return_and_logout(self):
        self.administrator();other=self.other();self.serve()
        primary='zz_account='+self.token
        status,headers,body=self.request('/api/admin',dict(operation='support',target=other['id'],password=PASSWORD,reason='Проверка кабинета'),Cookie=primary)
        self.assertEqual(status,200);self.assertNotIn('_supportToken',body)
        support=headers['Set-Cookie'].split(';')[0]
        self.assertIn('HttpOnly',headers['Set-Cookie']);cookies=primary+'; '+support
        account=self.request('/api/account',Cookie=cookies)[2]
        self.assertEqual(account['profile']['login'],other['login']);self.assertTrue(account['support']['active'])
        status,_,campaign=self.request('/api/account/create',dict(title='Поддержка: проверка журнала'),Cookie=cookies)
        self.assertEqual(status,200)
        self.assertEqual(self.request('/api/saves',dict(scope='campaign',operation='create',label='Проверка поддержки'),Authorization=campaign['token'])[0],200)
        audit=self.game.admin.overview(self.account)['audit']
        saved=next(a for a in audit if a['details'].get('path')=='/api/saves')
        self.assertEqual(saved['actor'],self.account['id']);self.assertEqual(saved['target'],other['id'])
        self.assertEqual(saved['details']['action'],'create')
        self.assertEqual(self.request('/api/account/end-support',{},Cookie=cookies)[0],200)
        self.assertEqual(self.request('/api/saves',dict(scope='campaign',operation='create',label='Истёкшая поддержка'),Authorization=campaign['token'])[0],403)
        self.assertEqual(self.request('/api/account',Cookie=cookies)[2]['profile']['login'],self.account['login'])
        self.assertEqual(self.request('/api/account/logout',{},Cookie=primary)[0],200)
        self.assertEqual(self.request('/api/admin',Cookie=primary)[0],403)


if __name__=='__main__':unittest.main()
