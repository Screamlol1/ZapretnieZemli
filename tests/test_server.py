import concurrent.futures
import json
import sys
import tempfile
import time
import threading
import unittest
import urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]))
from server import Game, make_handler, ThreadingHTTPServer

class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'test.sqlite'
        self.game=Game(self.path)
        self.gm=self.game.login({'name':'Мастер'},True)
        self.player=self.game.login({'name':'Игрок','code':self.gm['code'],'key':self.gm['playerKey']})
        self.gs=self.game.session(self.gm['token']); self.ps=self.game.session(self.player['token'])
    def tearDown(self):
        self.game.db.close();self.tmp.cleanup()
    def test_gm_permissions_and_hidden_map(self):
        for action in ['paint','token','event','deleteCharacter']:
            with self.assertRaises(PermissionError):self.game.action(self.ps,{'action':action})
        self.game.action(self.gs,dict(action='paint',map='battle',x=2,y=3,terrain='wall',hidden=True))
        self.game.action(self.gs,dict(action='token',map='battle',x=2,y=3,name='Засада',hidden=True))
        player=self.game.view(self.ps)
        self.assertNotIn('2,3',player['maps']['battle']);self.assertEqual(player['tokens'],[])
        for key in ('gmKey','playerKey','identities'):self.assertNotIn(key,player)
    def test_reconnect_after_restart(self):
        self.game.db.close();self.game=Game(self.path)
        again=self.game.login(dict(name='Игрок',code=self.gm['code'],key=self.gm['playerKey'],resume=self.player['resume']))
        self.assertEqual(self.game.session(again['token'])['owner'],self.ps['owner'])
    def test_capacity(self):
        for n in range(9):self.game.login(dict(name=str(n),code=self.gm['code'],key=self.gm['playerKey']))
        self.assertEqual(len(self.game.view(self.gs)['members']),11)
        with self.assertRaises(ValueError):self.game.login(dict(name='Лишний',code=self.gm['code'],key=self.gm['playerKey']))
        again=self.game.login(dict(name='Игрок',code=self.gm['code'],key=self.gm['playerKey'],resume=self.player['resume']))
        self.assertEqual(len(self.game.view(self.gs)['members']),11)
        self.assertEqual(self.game.session(again['token'])['owner'],self.ps['owner'])
    def test_expired_session_cannot_exceed_capacity(self):
        self.ps['seen']=time.time()-50
        with self.assertRaises(PermissionError):self.game.session(self.player['token'])
        self.assertEqual(len(self.game.view(self.gs)['members']),1)
        with self.assertRaises(ValueError):self.game.login(dict(name='Второй Мастер',code=self.gm['code'],key=self.gm['gmKey']))
    def test_character_ownership_and_validation(self):
        import subprocess
        raw=subprocess.check_output(['node','--input-type=module','-e',"import {blank} from './public/tools/rules.js'; console.log(JSON.stringify({...blank(),name:'Тар'}))"],cwd=Path(__file__).parents[1],text=True,encoding='utf-8')
        sheet=json.loads(raw)
        result=self.game.action(self.ps,dict(action='character',sheet=sheet))
        c=result['characters'][0]
        other=self.game.login(dict(name='Другой',code=self.gm['code'],key=self.gm['playerKey']))
        os=self.game.session(other['token'])
        with self.assertRaises(PermissionError):self.game.action(os,dict(action='character',id=c['id'],sheet=sheet))
        self.assertNotIn('sheet',self.game.view(os)['characters'][0])
        sheet['attrs']['str']=99
        with self.assertRaises(ValueError):self.game.action(self.ps,dict(action='character',sheet=sheet))
    def test_http_parallel_clients(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.game))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url=f'http://127.0.0.1:{server.server_port}'
        def join(n):
            data=json.dumps(dict(name=str(n),code=self.gm['code'],key=self.gm['playerKey'])).encode()
            req=urllib.request.Request(url+'/api/join',data=data,headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req) as response:return json.load(response)
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=9) as pool:people=list(pool.map(join,range(9)))
            self.assertEqual(len(self.game.view(self.gs)['members']),11)
            req=urllib.request.Request(url+'/api/state',headers={'Authorization':people[0]['token']})
            with urllib.request.urlopen(req) as response:self.assertEqual(len(json.load(response)['members']),11)
            with urllib.request.urlopen(url+'/') as response:self.assertIn('Запретные Земли',response.read().decode())
        finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
