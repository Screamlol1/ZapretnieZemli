import copy
import json
import math
import unittest
import uuid
import test_server as support
from server import Game
from location_vision import Sight,clear_line,blockers
import adventure_packs


class AdvancedLocationTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown
    make_pc=support.CampaignTests.make_pc

    def setup_map(self):
        self.cid=self.make_pc()['id']
        m=self.game.action(self.gs,dict(action='locationMapGenerate',title='Двор',settings=dict(kind='camp',seed='advance')))['locationMaps'][-1]
        self.mid=m['id'];room=self.game.room(self.gs['room']);m=room['locationMaps'][0]
        m.update(revealed=True,features=[dict(id='left',style='well',art='well',shape='rect',x=80,y=80,w=20,h=20,label='Колодец',note='',gmNote='LEFT-PRIVATE',secret=False),dict(id='right',style='well',art='well',shape='rect',x=280,y=80,w=20,h=20,label='RIGHT-BEHIND-WALL',note='',gmNote='RIGHT-PRIVATE',secret=False)],paths=[dict(id='barrier',style='wall',points=[[200,0],[200,m['height']]],refs=[],secret=False)],tokens=[dict(id='hero-token',characterId=self.cid,x=100,y=120,secret=False)],trees=[],river=[],vision=dict(enabled=True,range=100,personalLight=0))
        self.game.save(room)
    def m(self,mid=None):return next(m for m in self.game.room(self.gs['room'])['locationMaps'] if m['id']==(mid or self.mid))
    def act(self,op,s=None,**d):return self.game.action(s or self.gs,dict(action='locationAdvanced',op=op,map=self.mid,version=self.m()['version'],**d))

    def test_personal_occlusion_server_secrets_and_gm_preview(self):
        self.setup_map();view=self.game.view(self.ps);m=view['locationMaps'][0]
        self.assertEqual([f['id'] for f in m['features']],['left']);self.assertTrue(m['visibility']['cells'])
        for secret in ('RIGHT-BEHIND-WALL','LEFT-PRIVATE','RIGHT-PRIVATE','locationObservers','scenePresets'):self.assertNotIn(secret,json.dumps(view))
        gm=self.game.view(self.gs);preview=gm['locationViews'][self.mid]['visionPreview']
        self.assertEqual(preview['features'],m['features']);self.assertNotIn('gmNote',json.dumps(preview))
        stranger=self.game.login(dict(name='Другой',code=self.gm['code'],key=self.gm['playerKey']));ss=self.game.session(stranger['token'])
        empty=self.game.view(ss)['locationMaps'][0];self.assertEqual(empty['features'],[]);self.assertEqual(empty['tokens'],[])
        with self.assertRaises(PermissionError):self.act('observer',ss,character=self.cid)
        self.act('observer',self.ps,character=self.cid)
        self.game.db.close();self.game=Game(self.path,reference_root=self.path.parent/'local-assets')
        self.assertEqual(self.game.view(self.ps)['locationMaps'][0]['observerId'],self.cid)

    def test_light_expiry_and_door_opening_reveal_only_visible_geometry(self):
        self.setup_map();room=self.game.room(self.gs['room']);m=room['locationMaps'][0]
        m['exploration']=dict(enabled=False,discovered=[],dark=True,doors={},lights=[dict(id='lamp',x=100,y=100,radius=100,name='Лампа',secret=False,expiresAt=10)])
        self.game.save(room)
        self.assertEqual(len(self.game.view(self.ps)['locationMaps'][0]['features']),1)
        v=self.game.action(self.gs,dict(action='exploration',op='door',map=self.mid,version=self.m()['version'],path='barrier',state='open'))
        self.assertEqual(len(self.game.view(self.ps)['locationMaps'][0]['features']),2)
        room=self.game.room(self.gs['room']);room['medicalClock']=11;self.game.save(room)
        self.assertEqual(self.game.view(self.ps)['locationMaps'][0]['features'],[])
        self.act('vision',enabled=True,range=100,personalLight=100)
        self.assertEqual(len(self.game.view(self.ps)['locationMaps'][0]['features']),2)

    def test_thin_rotated_barrier_cannot_leak_between_path_or_polygon_samples(self):
        self.setup_map()
        for degrees in (0,37,90,153):
            angle=math.radians(degrees)
            def rotate(p):return [200+p[0]*math.cos(angle)-p[1]*math.sin(angle),200+p[0]*math.sin(angle)+p[1]*math.cos(angle)]
            room=self.game.room(self.gs['room']);m=room['locationMaps'][0]
            vertices=[rotate(p) for p in ([100,80],[120,80],[120,88],[100,88])]
            left=min(p[0] for p in vertices);top=min(p[1] for p in vertices)
            m.update(width=600,height=600,cellSize=10,metersPerCell=1,vision=dict(enabled=True,range=100,personalLight=0),trees=[],river=[])
            m['tokens'][0].update(x=200,y=200)
            m['features']=[dict(id='narrow-hidden',style='well',art='well',shape='polygon',x=left,y=top,w=max(p[0] for p in vertices)-left,h=max(p[1] for p in vertices)-top,points=vertices,label='BETWEEN-SAMPLES-SECRET',note='',gmNote='',secret=False)]
            m['paths']=[dict(id='slit-wall',style='wall',points=[rotate([50,40.5]),rotate([50,40.7])],refs=[],secret=False),dict(id='hidden-road',style='road',points=[rotate([100,80]),rotate([100,88])],refs=[],secret=False)]
            sight=Sight(m,[200,200])
            # The old endpoints/midpoint test would expose this complete road.
            self.assertTrue(all(sight.sees(rotate(p)) for p in ([100,80],[100,84],[100,88])))
            self.assertTrue(all(sight.sees(p) for p in vertices+[rotate([110,84])]))
            self.assertFalse(sight.segment_visible(rotate([100,80]),rotate([100,88])))
            self.game.save(room);view=self.game.view(self.ps)
            self.assertNotIn('BETWEEN-SAMPLES-SECRET',json.dumps(view))
            from location_geometry import parameter
            hidden=rotate([100,81.2])
            self.assertFalse(any(parameter(hidden,a,b) is not None for p in view['locationMaps'][0]['paths'] if p['style']=='road' for a,b in zip(p['points'],p['points'][1:])))

    def test_narrow_dark_gap_between_lights_and_complexity_budget(self):
        self.setup_map();m=copy.deepcopy(self.m());m.update(paths=[],features=[],cellSize=1,metersPerCell=1,vision=dict(enabled=True,range=100,personalLight=0))
        m['exploration']=dict(dark=True,lights=[dict(x=x,y=0,radius=r) for x,r in ((0,.9),(4,2.7),(8,.1))])
        sight=Sight(m,[0,0]);self.assertTrue(all(sight.sees([x,0]) for x in (0,4,8)))
        self.assertFalse(sight.segment_visible([0,0],[8,0]))
        from location_vision import within_budget
        m.update(width=2000,height=2000,cellSize=100,metersPerCell=1)
        m['paths']=[dict(id=str(i),style='wall',points=[[100+i,100],[100+i,110]],refs=[]) for i in range(100)]
        self.assertFalse(within_budget(m))

    def test_owned_movement_cannot_cross_wall_and_stale_or_foreign_move_is_rejected(self):
        self.setup_map();before=self.m();cmd=dict(action='locationAdvanced',op='move',map=self.mid,version=before['version'],character=self.cid,point=[210,120])
        with self.assertRaises(ValueError):self.game.action(self.ps,cmd)
        self.assertEqual(self.m(),before)
        self.act('move',self.ps,character=self.cid,point=[120,120])
        with self.assertRaises(ValueError):self.game.action(self.ps,{**cmd,'point':[130,120]})
        self.assertEqual(self.m()['tokens'][0]['x'],120)

    def test_other_hero_movement_reuses_geometry_but_updates_visibility_and_version(self):
        from location_vision import _projection
        self.setup_map();npc=support.CampaignTests.make_npc(self)
        room=self.game.room(self.gs['room']);m=room['locationMaps'][0];m['tokens'].append(dict(id='visitor',characterId=npc['id'],x=120,y=120,secret=False));self.game.save(room)
        _projection.cache_clear();before=self.game.view(self.ps)['locationMaps'][0];cached=_projection.cache_info()
        self.assertEqual(len(before['tokens']),2)
        room=self.game.room(self.gs['room']);m=room['locationMaps'][0];m['tokens'][-1]['x']=300;m['version']+=1;self.game.save(room)
        after=self.game.view(self.ps)['locationMaps'][0]
        self.assertEqual(len(after['tokens']),1);self.assertEqual(after['version'],before['version']+1)
        self.assertEqual(_projection.cache_info().misses,cached.misses);self.assertGreater(_projection.cache_info().hits,cached.hits)

    def test_floor_link_travel_identity_state_once_and_unrevealed_target(self):
        self.setup_map();v=self.act('floorCreate',title='Подвал',kind='dungeon');target=v['locationMaps'][-1]
        self.act('stairsLink',targetMap=target['id'],targetVersion=target['version'],point=[100,120],targetPoint=[100,100],name='Лестница',revealed=True)
        stair=self.m()['stairs'][0];target=self.m(target['id']);self.assertEqual(self.game.view(self.ps)['locationMaps'][0]['stairs'],[])
        with self.assertRaises(PermissionError):self.act('stairsTravel',self.ps,character=self.cid,stair=stair['id'],targetVersion=target['version'])
        self.game.action(self.gs,dict(action='locationMapReveal',id=target['id'],version=target['version'],revealed=True))
        preview=self.game.view(self.gs)['locationViews'][self.mid]['visionPreview']
        self.assertEqual(preview['stairs'][0]['targetMap'],target['id'])
        self.act('presetSave',title='Герой у лестницы');preset=self.game.view(self.gs)['scenePresets'][0]
        before=copy.deepcopy(next(c for c in self.game.room(self.gs['room'])['characters'] if c['id']==self.cid))
        command=dict(action='locationAdvanced',op='stairsTravel',map=self.mid,version=self.m()['version'],character=self.cid,stair=stair['id'],targetVersion=self.m(target['id'])['version'],requestId=str(uuid.uuid4()))
        self.game.action(self.ps,command);self.game.action(self.ps,command)
        self.assertEqual(self.m()['tokens'],[]);self.assertEqual(len(self.m(target['id'])['tokens']),1)
        self.assertEqual(next(c for c in self.game.room(self.gs['room'])['characters'] if c['id']==self.cid),before)
        with self.assertRaises(ValueError):self.act('presetApply',preset=preset['id'],presetVersion=preset['version'],confirmed=True)
        self.assertEqual(self.m()['tokens'],[])

    def test_presets_restore_layout_light_sound_not_character_health_and_are_private(self):
        self.setup_map();self.act('presetSave',title='Засада',description='Скрип калитки',gmNote='PRESET-SECRET')
        p=self.game.view(self.gs)['scenePresets'][0]
        self.assertNotIn('PRESET-SECRET',json.dumps(self.game.view(self.ps)))
        self.act('move',character=self.cid,point=[140,120]);room=self.game.room(self.gs['room']);hero=next(c for c in room['characters'] if c['id']==self.cid);hero['runtime']['current']['str']=1;self.game.save(room)
        self.act('presetApply',preset=p['id'],presetVersion=p['version'],confirmed=True)
        self.assertEqual(self.m()['tokens'][0]['x'],100)
        self.assertEqual(next(c for c in self.game.room(self.gs['room'])['characters'] if c['id']==self.cid)['runtime']['current']['str'],1)
        self.act('presetUndo');self.assertEqual(self.m()['tokens'][0]['x'],140)
        self.act('presetApply',preset=p['id'],presetVersion=p['version'],confirmed=True)
        self.act('move',character=self.cid,point=[110,120])
        with self.assertRaises(ValueError):self.act('presetUndo')

    def test_adventure_pack_private_preview_atomic_import_id_remap_and_no_player_heroes(self):
        self.setup_map()
        self.act('packExport',workshop=[]);pack=self.game.view(self.gs)['locationPackExport']
        self.assertEqual(pack['actors'],[]);self.assertEqual(pack['maps'][0]['tokens'],[])
        self.assertNotIn('locationPackExport',self.game.view(self.ps))
        with self.assertRaises(PermissionError):self.act('packPreview',self.ps,pack=pack)
        self.act('packPreview',pack=pack);preview=self.game.view(self.gs)['locationPackPreview']
        broken=copy.deepcopy(pack);broken['maps'][0]['features'][0]['x']=float('nan')
        count=len(self.game.room(self.gs['room'])['locationMaps'])
        with self.assertRaises(ValueError):self.act('packImport',pack=broken,preview=preview['id'],confirmed=True)
        self.assertEqual(len(self.game.room(self.gs['room'])['locationMaps']),count)
        self.act('packImport',pack=pack,preview=preview['id'],confirmed=True)
        imported=self.game.room(self.gs['room'])['locationMaps'][-1]
        self.assertNotEqual(imported['id'],self.mid);self.assertNotEqual(imported['features'][0]['id'],'left');self.assertFalse(imported['revealed'])
        with self.assertRaises(ValueError):self.act('packImport',pack=pack,preview=preview['id'],confirmed=True)

    def test_pack_rejects_dangling_links_unknown_art_and_outside_geometry(self):
        self.setup_map();pack=adventure_packs.export(self.game.room(self.gs['room']),self.mid)
        for change in ('art','geometry','link'):
            bad=copy.deepcopy(pack)
            if change=='art':bad['maps'][0]['features'][0]['art']='https://untrusted.example/image.svg'
            elif change=='geometry':bad['maps'][0]['features'][0]['w']=100000
            else:bad['maps'][0]['paths'][0]['refs']=['missing']
            with self.assertRaises(ValueError):adventure_packs.validate(bad)

    def test_full_pack_roundtrip_floors_population_npc_workshop_and_expired_light(self):
        self.setup_map();v=self.act('floorCreate',title='Подвал',kind='dungeon');target=v['locationMaps'][-1]
        self.act('stairsLink',targetMap=target['id'],targetVersion=target['version'],point=[100,120],targetPoint=[100,100],name='Лестница',revealed=True)
        self.game.action(self.gs,dict(action='locationMapPopulationGenerate',id=self.mid,version=self.m()['version'],count=5,mode='artisans',kin='human',seed='folk',revealed=True))
        monster=dict(kind='monster',name='Страж ворот',hidden=True,monster=dict(strength=8,agility=3,armor=2,notes='MONSTER-SECRET',attacks=[dict(name='Удар',dice=5,damage=1,range=1,type='physical',dodge=True,parry=True,note='') for _ in range(6)]))
        v=self.game.action(self.gs,dict(action='actor',actor=monster));cid=next(c['id'] for c in v['characters'] if c['kind']=='monster')
        visual=dict(body='slim',cloak='#176963',cloth='#a37942',skin='#c79b73',hair='#513120',monster='spider',direction='left')
        self.game.action(self.gs,dict(action='visual',id=cid,visual=visual))
        self.game.action(self.gs,dict(action='locationMapEdit',id=self.mid,version=self.m()['version'],op='token',characterId=cid,point=[110,120],secret=True))
        entry=self.game.action(self.gs,dict(action='workshopSave',draft=dict(kind='event',fields=dict(title='Событие набора',secret='HOOK-SECRET'),tables=dict(problem=dict(name='Встреча',source='Авторская',dice='D6',rows='1-6 | Шорох')))))['workshop'][-1]
        room=self.game.room(self.gs['room']);room['locationMaps'][0]['exploration']=dict(enabled=False,dark=False,doors={},discovered=[],lights=[dict(id='old-lamp',name='Погасший',x=100,y=100,radius=10,expiresAt=0,secret=False)]);self.game.save(room)
        pack=adventure_packs.export(room,self.mid,[entry['id']]);checked,_=adventure_packs.validate(pack)
        imported=adventure_packs.import_pack(room,checked);newmaps=[m for m in room['locationMaps'] if m['id'] in imported['maps']]
        self.assertEqual(len(newmaps),2);self.assertEqual(len(imported['actors']),1)
        self.assertEqual(len(newmaps[0]['population']['residents']),5)
        self.assertEqual(newmaps[0]['population']['residents'][0]['gmNote'],room['locationMaps'][0]['population']['residents'][0]['gmNote'])
        self.assertEqual(newmaps[0]['stairs'][0]['targetMap'],newmaps[1]['id'])
        self.assertNotIn(cid,json.dumps(newmaps));self.assertEqual(room['workshop'][-1]['tables']['problem']['dice'],'D6')
        self.assertEqual(newmaps[0]['exploration']['lights'][0]['expiresAt'],0)
        self.assertEqual(next(c for c in room['characters'] if c['id']==imported['actors'][0])['visual'],visual)

    def test_restore_invalidates_preview_undo_and_preset_commands(self):
        import location_advanced
        old=dict(scenePresets=[dict(id='p',version=2)],scenePresetUndo=dict(map='m'),locationPackPreview=dict(id='nonce'),locationObservers={'owner':'hero'},locationHistory={'map':[]})
        current=dict(scenePresets=[dict(id='p',version=6)])
        location_advanced.restored(old,current)
        self.assertEqual(old,dict(scenePresets=[dict(id='p',version=7)]))


if __name__=='__main__':unittest.main()
