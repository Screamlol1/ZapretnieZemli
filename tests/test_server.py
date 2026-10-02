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
        room=self.game.room(self.gm['code']);room['worldLayout']='legacy';self.game.save(room)
        self.player=self.game.login({'name':'Игрок','code':self.gm['code'],'key':self.gm['playerKey']})
        self.gs=self.game.session(self.gm['token']); self.ps=self.game.session(self.player['token'])
    def tearDown(self):
        self.game.db.close();self.tmp.cleanup()
    def test_gm_permissions_and_hidden_map(self):
        for action in ['paint','event','deleteCharacter','actor','combatCreate']:
            with self.assertRaises(PermissionError):self.game.action(self.ps,{'action':action})
        with self.assertRaises(PermissionError):self.game.action(self.ps,dict(action='token',map='battle',x=1,y=1))
        self.game.action(self.gs,dict(action='paint',map='battle',x=2,y=3,terrain='wall',hidden=True))
        self.game.action(self.gs,dict(action='token',map='battle',x=2,y=3,name='Засада',hidden=True))
        player=self.game.view(self.ps)
        self.assertNotIn('2,3',player['maps']['battle']);self.assertEqual(player['tokens'],[])
        for key in ('gmKey','playerKey','identities'):self.assertNotIn(key,player)
    def test_regional_grid_permissions_boundaries_and_safe_layout_change(self):
        from campaign_rules import adjacent, coordinate
        with self.assertRaises(PermissionError):self.game.action(self.ps,dict(action='worldLayout',layout='ravenland'))
        self.game.action(self.gs,dict(action='worldLayout',layout='ravenland'))
        room=self.game.room(self.gs['room'])
        self.assertTrue(adjacent(dict(x=0,y=0),dict(x=1,y=0),room))
        self.assertTrue(adjacent(dict(x=0,y=1),dict(x=1,y=0),room))
        self.assertFalse(adjacent(dict(x=0,y=0),dict(x=2,y=0),room))
        self.game.action(self.gs,dict(action='paint',map='world',x=40,y=24,terrain='forest',hidden=False))
        with self.assertRaises(ValueError):coordinate(dict(x=39,y=24),room)
        with self.assertRaises(ValueError):self.game.action(self.gs,dict(action='token',map='world',x=41,y=0))
        with self.assertRaises(ValueError):self.game.action(self.gs,dict(action='paint',map='battle',x=24,y=0,terrain='forest'))
        with self.assertRaises(ValueError):self.game.action(self.gs,dict(action='worldLayout',layout='legacy'))
        self.assertIn('40,24',self.game.view(self.gs)['maps']['world'])
        # Old rooms without a layout stay on their original coordinate system.
        room.pop('worldLayout');self.game.save(room)
        with self.assertRaises(ValueError):self.game.action(self.gs,dict(action='mapLocation',x=30,y=20))

    def test_reconnect_after_restart(self):
        self.game.db.close();self.game=Game(self.path)
        again=self.game.login(dict(name='Игрок',code=self.gm['code'],key=self.gm['playerKey'],resume=self.player['resume']))
        self.assertEqual(self.game.session(again['token'])['owner'],self.ps['owner'])

    def test_map_locations_preserve_metadata_and_secrets(self):
        data=dict(action='mapLocation',x=3,y=4,label='Башня',note='Вход на юге',gmNote='Тайный проход',siteType='castle',siteHidden=True)
        with self.assertRaises(PermissionError):self.game.action(self.ps,data)
        self.game.action(self.gs,data)
        self.game.action(self.gs,dict(action='paint',map='world',x=3,y=4,terrain='forest',hidden=False))
        cell=self.game.view(self.gs)['maps']['world']['3,4']
        self.assertEqual(cell['label'],'Башня');self.assertEqual(cell['terrain'],'forest')
        public=self.game.view(self.ps)['maps']['world']['3,4']
        for k in ('label','note','gmNote','siteType','siteHidden'):self.assertNotIn(k,public)
        data['siteHidden']=False;self.game.action(self.gs,data)
        public=self.game.view(self.ps)['maps']['world']['3,4']
        self.assertEqual(public['note'],'Вход на юге');self.assertNotIn('gmNote',public)
        self.game.action(self.gs,dict(action='paint',map='world',x=3,y=4,terrain='forest',hidden=True))
        self.assertNotIn('3,4',self.game.view(self.ps)['maps']['world'])
        self.assertIn('3,4',self.game.view(self.ps)['mapFog']['world'])

    def test_map_upload_permissions_versions_and_private_storage(self):
        import base64
        png='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aC1cAAAAASUVORK5CYII='
        with self.assertRaises(PermissionError):self.game.upload_map(self.ps,dict(image=png,revision=0))
        with self.assertRaises(ValueError):self.game.upload_map(self.gs,dict(image='broken',revision=0))
        result=self.game.upload_map(self.gs,dict(image=png,revision=0))
        self.assertEqual(result['mapArtwork']['style'],'upload');self.assertNotIn('file',result['mapArtwork'])
        self.assertEqual(self.game.map_image(self.ps),(base64.b64decode(png),'image/png'))
        with self.assertRaises(ValueError):self.game.upload_map(self.gs,dict(image=png,revision=0))
        with self.assertRaises(PermissionError):self.game.action(self.ps,dict(action='mapArtwork',style='terrain',revision=1))
        self.game.action(self.gs,dict(action='mapArtwork',style='terrain',revision=1))
        with self.assertRaises(ValueError):self.game.map_image(self.ps)
        self.game.action(self.gs,dict(action='mapArtwork',style='upload',revision=2))
        self.assertEqual(self.game.map_image(self.ps)[1],'image/png')
        self.game.db.close();self.game=Game(self.path)
        self.assertEqual(self.game.map_image(self.ps)[0],base64.b64decode(png))
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

    def make_pc(self):
        import subprocess
        raw=subprocess.check_output(['node','--input-type=module','-e',"import {blank} from './public/tools/rules.js'; console.log(JSON.stringify({...blank(),name:'Герой'}))"],cwd=Path(__file__).parents[1],text=True,encoding='utf-8')
        result=self.game.action(self.ps,dict(action='character',sheet=json.loads(raw)))
        return next(c for c in result['characters'] if c.get('kind')=='pc' and c['owner']==self.ps['owner'])

    def make_npc(self,hidden=False):
        data=dict(kind='npc',name='Орк',hidden=hidden,kin='orc',profession='fighter',attrs=dict(str=5,agi=3,wit=3,emp=2),skills={k:0 for k in ['melee','might','craft','endure','sleight','shoot','move','stealth','survive','lore','insight','scout','influence','animal','perform','heal']},gear=['broadsword'])
        return self.game.action(self.gs,dict(action='actor',actor=data))['characters'][-1]

    def test_owned_tokens_and_assignment(self):
        pc=self.make_pc()
        result=self.game.action(self.gs,dict(action='token',map='world',x=1,y=1,characterId=pc['id']))
        token=result['tokens'][0]
        moved=self.game.action(self.ps,dict(action='token',id=token['id'],map='world',x=2,y=1,name='Подмена',hidden=True))['tokens'][0]
        self.assertEqual(moved['name'],pc['name']);self.assertFalse(moved['hidden'])
        self.game.action(self.gs,dict(action='assignCharacter',id=pc['id'],owner=self.gs['owner']))
        with self.assertRaises(PermissionError):self.game.action(self.ps,dict(action='token',id=token['id'],map='world',x=3,y=1))
        with self.assertRaises(PermissionError):self.game.action(self.ps,dict(action='character',id=pc['id'],sheet=pc['sheet']))

    def test_visual_permissions_and_validation(self):
        pc=self.make_pc();v=dict(body='broad',cloak='#123456',cloth='#bbaa77',skin='#cc9977',hair='#221100',monster='beast')
        self.game.action(self.ps,dict(action='visual',id=pc['id'],visual=v))
        npc=self.make_npc()
        with self.assertRaises(PermissionError):self.game.action(self.ps,dict(action='visual',id=npc['id'],visual=v))
        v['cloak']='url(evil)'
        with self.assertRaises(ValueError):self.game.action(self.ps,dict(action='visual',id=pc['id'],visual=v))

    def test_monster_schema_and_hidden_notes(self):
        monster=dict(kind='monster',name='Сторож',hidden=True,monster=dict(strength=16,agility=3,armor=2,notes='Тайная слабость',attacks=[dict(name='Удар',dice=8,damage=1,range=1,type='physical',parry=False,dodge=True,note='') for _ in range(6)]))
        c=self.game.action(self.gs,dict(action='actor',actor=monster))['characters'][-1]
        self.assertNotIn(c['id'],[c['id'] for c in self.game.view(self.ps)['characters']])
        monster['hidden']=False
        self.game.action(self.gs,dict(action='actor',id=c['id'],actor=monster))
        public=next(x for x in self.game.view(self.ps)['characters'] if x['id']==c['id'])
        self.assertNotIn('monster',public)
        pc=self.make_pc()
        self.game.action(self.gs,dict(action='combatCreate',units=[dict(id=pc['id'],team='A'),dict(id=c['id'],team='B')]))
        exposed=next(u for u in self.game.view(self.ps)['combat']['units'] if u['id']==c['id'])
        self.assertEqual(exposed['monster'],{})
        monster['monster']['attacks'][0]['dice']=999
        with self.assertRaises(ValueError):self.game.action(self.gs,dict(action='actor',actor=monster))

    def test_combat_turn_ownership_and_stale_command(self):
        pc=self.make_pc();npc=self.make_npc()
        view=self.game.action(self.gs,dict(action='combatCreate',units=[dict(id=pc['id'],team='A'),dict(id=npc['id'],team='B')],mapId='road'))
        rev=view['combatRevision']
        with self.assertRaises(PermissionError):self.game.action(self.ps,dict(action='combatAction',revision=rev,command=dict(action='start')))
        view=self.game.action(self.gs,dict(action='combatAction',revision=rev,command=dict(action='start')))
        rev=view['combatRevision'];active=view['combat']['order'][0]
        with self.assertRaises(ValueError):self.game.action(self.gs,dict(action='combatAction',revision=rev-1,command=dict(action='end')))
        if active!=pc['id']:
            with self.assertRaises(PermissionError):self.game.action(self.ps,dict(action='combatAction',revision=rev,command=dict(action='end')))
            view=self.game.action(self.gs,dict(action='combatAction',revision=rev,command=dict(action='end')));rev=view['combatRevision']
        view=self.game.action(self.ps,dict(action='combatAction',revision=rev,command=dict(action='end')))
        self.assertEqual(view['combat']['order'][view['combat']['turn']],npc['id'])
        with self.assertRaises(ValueError):self.game.action(self.ps,dict(action='character',id=pc['id'],sheet=pc['sheet']))
        with self.assertRaises(PermissionError):self.game.action(self.ps,dict(action='combatManual',note='Подмена'))

    def test_npc_runtime_and_non_hero_creation(self):
        npc=self.make_npc()
        self.assertEqual(npc['sheet']['attrs']['str'],5)
        self.assertEqual(npc['sheet']['kin'],'orc')
        with self.assertRaises(ValueError):self.game.action(self.gs,dict(action='runtime',id=npc['id'],current=npc['sheet']['attrs'],wp=1))

if __name__=='__main__':unittest.main()
