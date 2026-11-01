import json
import subprocess
import tempfile
import threading
import time
import unittest
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
sys.path.insert(0, str(Path(__file__).parents[1]))
from server import Game, make_handler, ThreadingHTTPServer, RequestLimits
from accounts import COOKIE
from save_points import apply as saves

PASSWORD = 'long password for testing 42'


class AccountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parents[1]
        cls.sheet = json.loads(subprocess.check_output(['node', '--input-type=module', '-e', "import {blank} from './public/tools/rules.js';console.log(JSON.stringify({...blank(),name:'Личный герой'}))"], cwd=root, text=True, encoding='utf-8'))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'account.sqlite'
        self.game = Game(self.path)
        self.a = self.game.accounts
        self.token, self.registration = self.a.auth('register', dict(login='player.one', name='Игрок', password=PASSWORD))
        self.account = self.a.authenticate(self.token)
        self.http = None

    def tearDown(self):
        if self.http:
            self.http.shutdown(); self.http.server_close(); self.thread.join()
        self.game.db.close(); self.tmp.cleanup()

    def other(self):
        token, _ = self.a.auth('register', dict(login='other', password=PASSWORD))
        return self.a.authenticate(token)

    def hero(self):
        return self.a.character(self.account, dict(action='save', sheet=self.sheet))['id']

    def entry(self, lid):
        return next(c for c in self.a.dashboard(self.account)['characters'] if c['id'] == lid)

    def campaign(self):
        return self.a.campaign(self.account, dict(title='Аккаунт'), True)

    def test_normalized_login_hashes_and_recovery(self):
        with self.assertRaises(ValueError): self.a.auth('register', dict(login='PLAYER.ONE', password=PASSWORD))
        stored = self.game.db.execute('SELECT password,recovery FROM accounts').fetchone()
        self.assertNotIn(PASSWORD, stored)
        self.assertNotIn(self.registration['recovery'], stored)
        token, _ = self.a.auth('login', dict(login=' PLAYER.ONE ', password=PASSWORD))
        self.assertEqual(self.a.authenticate(token)['id'], self.account['id'])
        with self.assertRaises(PermissionError): self.a.auth('login', dict(login='player.one', password='bad'))
        token, info = self.a.auth('recover', dict(login='player.one', recovery=self.registration['recovery'], password=PASSWORD+'new'))
        self.assertTrue(self.a.authenticate(token))
        self.assertNotEqual(info['recovery'], self.registration['recovery'])
        with self.assertRaises(PermissionError): self.a.authenticate(self.token)
        with self.assertRaises(PermissionError): self.a.auth('recover', dict(login='player.one', recovery=self.registration['recovery'], password=PASSWORD))

    def test_password_change_revokes_other_sessions_and_logout_revokes_game(self):
        token2, _ = self.a.auth('login', dict(login='player.one', password=PASSWORD))
        campaign = self.campaign()
        self.a.password(self.account, dict(currentPassword=PASSWORD, password=PASSWORD+'new'))
        with self.assertRaises(PermissionError): self.a.authenticate(token2)
        self.assertTrue(self.a.authenticate(self.token))
        self.a.logout(self.token)
        with self.assertRaises(PermissionError): self.game.session(campaign['token'])

    def test_sessions_and_membership_survive_restart(self):
        campaign = self.campaign()
        owner = self.game.session(campaign['token'])['owner']
        self.game.db.close(); self.game = Game(self.path); self.a = self.game.accounts
        account = self.a.authenticate(self.token)
        again = self.a.campaign(account, dict(code=campaign['code']))
        self.assertEqual(self.game.session(again['token'])['owner'], owner)
        self.assertEqual(again['role'], 'gm')
        self.assertEqual(self.a.dashboard(account)['campaigns'][0]['code'], campaign['code'])
        self.game.db.execute('UPDATE account_sessions SET expires=0'); self.game.db.commit()
        with self.assertRaises(PermissionError): self.a.authenticate(self.token)
        with self.assertRaises(PermissionError): self.game.session(again['token'])

    def test_account_bound_identity_and_gm_key_cannot_be_claimed(self):
        campaign = self.campaign(); other = self.other()
        for account in (None, other):
            with self.assertRaises(PermissionError): self.game.reconnect(dict(code=campaign['code'], resume=campaign['resume']), account)
            with self.assertRaises(PermissionError): self.game.login(dict(name='Thief',code=campaign['code'],key=campaign['gmKey']), account=account)
        joined = self.a.campaign(other, dict(code=campaign['code'], key=campaign['playerKey'], role='gm'))
        self.assertEqual(joined['role'], 'player')
        self.assertIsNone(joined['gmKey'])
        serialized = json.dumps(self.a.dashboard(other))
        self.assertNotIn(campaign['gmKey'], serialized)
        self.assertNotIn(campaign['resume'], serialized)
        self.assertNotIn('gmAccount', self.game.view(self.game.session(joined['token'])))

    def test_legacy_claim_keeps_owner_and_characters(self):
        guest = self.game.login(dict(name='Legacy'), True)
        s = self.game.session(guest['token'])
        self.game.action(s, dict(action='character', sheet=self.sheet))
        claimed = self.a.campaign(self.account, dict(code=guest['code'], resume=guest['resume']))
        self.assertEqual(self.game.session(claimed['token'])['owner'], s['owner'])
        c = self.a.dashboard(self.account)['campaigns'][0]['characters'][0]
        self.a.character(self.account, dict(action='capture', code=guest['code'], character=c['id']))
        self.assertEqual(len(self.a.dashboard(self.account)['characters']), 1)
        with self.assertRaises(PermissionError): self.game.session(guest['token'])

    def test_limit_edit_delete_and_cross_account_isolation(self):
        ids = [self.hero() for _ in range(10)]
        with self.assertRaisesRegex(ValueError, '10 персонажей'): self.hero()
        first = self.entry(ids[0])
        self.a.character(self.account, dict(action='save',id=first['id'],version=first['version'],sheet={**self.sheet,'name':'Обновлён'}))
        with self.assertRaisesRegex(ValueError, 'другой вкладке'): self.a.character(self.account, dict(action='save',id=first['id'],version=first['version'],sheet=self.sheet))
        other = self.other()
        for action in ('save','delete','deploy'):
            with self.assertRaises(PermissionError): self.a.character(other, dict(action=action,id=first['id'],version=first['version'],sheet=self.sheet))
        self.assertEqual(self.a.dashboard(other)['characters'], [])
        latest = self.entry(first['id'])
        self.a.character(self.account, dict(action='delete',id=latest['id'],version=latest['version']))
        self.hero()
        self.assertEqual(len(self.a.dashboard(self.account)['characters']), 10)

    def test_linked_hero_sync_inventory_private_data_and_safe_edit(self):
        campaign = self.campaign(); lid = self.hero(); c = self.entry(lid)
        added = self.a.character(self.account, dict(action='deploy',id=lid,version=c['version'],code=campaign['code']))
        cid = added['character']; room = self.game.room(campaign['code']); hero = room['characters'][0]
        hero['runtime']['current']['str'] = 1; hero['runtime']['wp'] = 3
        room['items'] = [dict(id='private-item',name='Амулет',quantity=1,location=dict(kind='character',id=cid),gmNote='SECRET',maintenanceNote='SECRET2')]
        self.game.save(room)
        c = self.entry(lid)
        self.assertEqual(c['runtime']['current']['str'], 1)
        self.assertEqual(c['items'][0]['name'], 'Амулет')
        self.assertNotIn('SECRET', json.dumps(c))
        self.a.character(self.account, dict(action='save',id=lid,version=c['version'],sheet={**self.sheet,'notes':'Запись после встречи'}))
        c = self.entry(lid)
        self.assertEqual(c['runtime']['current']['str'], 1)
        self.assertEqual(c['runtime']['wp'], 3)
        self.assertEqual(c['sheet']['notes'], 'Запись после встречи')
        self.a.character(self.account, dict(action='deploy',id=lid,version=c['version'],code=campaign['code']))
        self.assertEqual(len(self.game.room(campaign['code'])['characters']), 1)
        other = self.other()
        self.a.campaign(other, dict(code=campaign['code'],key=campaign['playerKey']))
        with self.assertRaises(PermissionError): self.a.character(other, dict(action='capture',code=campaign['code'],character=cid))
        self.a.character(self.account, dict(action='delete',id=lid,version=c['version']))
        self.assertEqual(len(self.game.room(campaign['code'])['characters']), 1)

    def test_restore_keeps_account_binding_and_updates_library(self):
        campaign=self.campaign(); lid=self.hero(); c=self.entry(lid)
        self.a.character(self.account,dict(action='deploy',id=lid,version=c['version'],code=campaign['code']))
        s=self.game.session(campaign['token'])
        saved=saves(self.game,s,dict(scope='campaign',operation='create'))
        self.assertNotIn('gmAccount',saved['document']['state'])
        room=self.game.room(campaign['code']);room['characters'][0]['runtime']['wp']=5;self.game.save(room)
        version=self.entry(lid)['version']
        saves(self.game,s,dict(scope='campaign',operation='restore',id=saved['id'],confirmed=True,revision=room['revision']))
        self.assertEqual(self.game.room(campaign['code'])['gmAccount'],self.account['id'])
        self.assertEqual(self.entry(lid)['runtime']['wp'],0)
        self.assertGreater(self.entry(lid)['version'],version)

    def serve(self):
        self.http=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.game))
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.http.server_port}'

    def request(self,path,data=None,**headers):
        if data is not None: headers['Content-Type']='application/json'
        req=Request(self.url+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
        try: response=urlopen(req,timeout=10)
        except HTTPError as e: response=e
        with response:
            raw=response.read()
            return response.status,dict(response.headers),json.loads(raw) if response.headers.get('Content-Type','').startswith('application/json') else raw

    def test_http_cookie_csrf_login_logout_and_authenticated_reconnect(self):
        self.serve()
        status,headers,body=self.request('/api/account/login',dict(login='player.one',password=PASSWORD))
        self.assertEqual(status,200)
        cookie=headers['Set-Cookie'];self.assertIn('HttpOnly',cookie);self.assertIn('SameSite=Strict',cookie)
        cookie=cookie.split(';')[0]
        self.assertEqual(self.request('/api/account',Cookie=cookie)[0],200)
        self.assertEqual(self.request('/api/account')[0],403)
        self.assertEqual(self.request('/api/account/create',{},Cookie=cookie,Origin='https://evil.example')[0],403)
        self.assertEqual(self.request('/api/account/create',{},Cookie=cookie,**{'Sec-Fetch-Site':'cross-site'})[0],403)
        _,_,campaign=self.request('/api/account/create',dict(title='HTTP'),Cookie=cookie)
        self.game.sessions.clear()
        _,_,resumed=self.request('/api/resume',dict(code=campaign['code'],resume=campaign['resume']),Cookie=cookie)
        self.assertEqual(resumed['role'],'gm')
        self.assertEqual(self.request('/api/resume',dict(code=campaign['code'],resume=campaign['resume']))[0],403)
        self.assertEqual(self.request('/api/account/logout',{},Cookie=cookie)[0],200)
        self.assertEqual(self.request('/api/state',Authorization=resumed['token'])[0],403)
        self.assertIn(b'account.js',self.request('/')[2])

    def test_blocked_password_attempts(self):
        for _ in range(10):
            with self.assertRaises(PermissionError): self.a.auth('login',dict(login='player.one',password='wrong'))
        with self.assertRaisesRegex(PermissionError,'15 минут'): self.a.auth('login',dict(login='player.one',password=PASSWORD))
        self.game.db.execute('UPDATE accounts SET blocked=?',(time.time()-1,));self.game.db.commit()
        self.assertTrue(self.a.auth('login',dict(login='player.one',password=PASSWORD))[0])


if __name__=='__main__':unittest.main()
