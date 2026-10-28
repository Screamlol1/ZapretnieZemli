import json
import unittest
import test_server as support
from location_maps import generate, settings, KINDS, SIZES
from save_points import capture, apply as checkpoint
from pathlib import Path
from server import Game

class LocationMapTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown

    def create(self,**kwargs):
        return self.game.action(self.gs,dict(action='locationMapGenerate',title='Вороний брод',settings=dict(kind='settlement',seed='test-location'),**kwargs))['locationMaps'][-1]
    def edit(self,m,**kwargs):
        return self.game.action(self.gs,dict(action='locationMapFeature',id=m['id'],version=m['version'],feature=m['features'][0]['id'],label='Тайная комната',note='Видимое описание',gmNote='GM-ONLY-TRAP',secret=True,**kwargs))['locationMaps'][-1]

    def test_templates_deterministic_and_underground_connected(self):
        for kind in KINDS:
            for size in SIZES:
                cfg=settings(dict(kind=kind,size=size,seed='fixed'))
                m=generate(cfg);self.assertEqual(m,generate(cfg));self.assertTrue(m['features'])
                for f in m['features']:
                    self.assertGreaterEqual(f['x'],0);self.assertGreaterEqual(f['y'],0)
                    self.assertLessEqual(f['x']+f['w'],m['width']);self.assertLessEqual(f['y']+f['h'],m['height'])
                if kind in ('dungeon','cave'):
                    reached={m['features'][0]['id']}
                    for _ in m['features']:
                        for p in m['paths']:
                            if reached.intersection(p['refs']):reached.update(p['refs'])
                    self.assertEqual(reached,{f['id'] for f in m['features']})

    def test_private_maps_and_mutations_are_gm_only(self):
        m=self.create();self.assertEqual(self.game.view(self.ps)['locationMaps'],[])
        for action in ('locationMapGenerate','locationMapFeature','locationMapReveal','locationMapDelete'):
            with self.assertRaises(PermissionError):self.game.action(self.ps,dict(action=action,id=m['id'],version=m['version']))
        self.assertNotIn(m['id'],json.dumps(self.game.view(self.ps)))

    def test_public_view_removes_secret_geometry_notes_and_seed(self):
        m=self.game.action(self.gs,dict(action='locationMapGenerate',title='Подземелье',settings=dict(kind='dungeon',seed='SECRET-SEED')))['locationMaps'][-1]
        m=self.edit(m);secret=m['features'][0]['id']
        self.game.action(self.gs,dict(action='locationMapReveal',id=m['id'],version=m['version'],revealed=True))
        public=self.game.view(self.ps)['locationMaps'][0]
        self.assertNotIn(secret,[f['id'] for f in public['features']])
        self.assertFalse(any(secret in p['refs'] for p in public['paths']))
        serialized=json.dumps(public,ensure_ascii=False)
        for value in ('GM-ONLY-TRAP','SECRET-SEED','Тайная комната','settings','gmNote'):self.assertNotIn(value,serialized)

    def test_hex_link_visibility_and_stale_commands(self):
        self.game.action(self.gs,dict(action='mapLocation',x=2,y=3,label='Город',siteType='settlement',siteHidden=True))
        m=self.create(source=dict(kind='hex',x=2,y=3))
        self.assertEqual(self.game.view(self.gs)['maps']['world']['2,3']['locationMapId'],m['id'])
        self.assertNotIn('locationMapId',self.game.view(self.ps)['maps']['world']['2,3'])
        with self.assertRaises(ValueError):self.game.action(self.gs,dict(action='locationMapReveal',id=m['id'],version=m['version'],revealed=True))
        self.game.action(self.gs,dict(action='mapLocation',x=2,y=3,label='Город',siteType='settlement',siteHidden=False))
        self.game.action(self.gs,dict(action='locationMapReveal',id=m['id'],version=m['version'],revealed=True))
        self.assertEqual(len(self.game.view(self.ps)['locationMaps']),1)
        with self.assertRaises(ValueError):self.edit(m)
        self.game.action(self.gs,dict(action='paint',map='world',x=2,y=3,terrain='plain',hidden=True))
        self.assertEqual(self.game.view(self.ps)['locationMaps'],[])

    def test_workshop_map_survives_save_publish_and_library_deletion(self):
        e=self.game.action(self.gs,dict(action='workshopSave',draft=dict(kind='settlement',fields=dict(title='Город'))))['workshop'][-1]
        m=self.create(source=dict(kind='workshop',id=e['id']))
        e=self.game.view(self.gs)['workshop'][-1]
        e=self.game.action(self.gs,dict(action='workshopSave',id=e['id'],version=e['version'],draft=e))['workshop'][-1]
        self.assertEqual(e['locationMapId'],m['id'])
        v=self.game.action(self.gs,dict(action='workshopPublish',id=e['id'],version=e['version'],x=1,y=1))
        self.assertEqual(v['maps']['world']['1,1']['locationMapId'],m['id'])
        self.assertEqual(v['locationMaps'][0]['source'],dict(kind='hex',x=1,y=1))
        e=v['workshop'][-1];self.game.action(self.gs,dict(action='workshopDelete',id=e['id'],version=e['version']))
        self.assertEqual(self.game.view(self.gs)['locationMaps'][0]['id'],m['id'])
        saved=capture(self.game.room(self.gs['room']),'campaign')
        self.assertEqual(saved['locationMaps'][0]['id'],m['id'])

    def test_regeneration_requires_confirmation_resets_visibility_and_delete_unlinks(self):
        m=self.create();m=self.edit(m)
        command=dict(action='locationMapGenerate',id=m['id'],version=m['version'],title='Новый план',settings=dict(kind='camp',seed='new'))
        with self.assertRaises(ValueError):self.game.action(self.gs,command)
        v=self.game.action(self.gs,{**command,'replace':True});m=v['locationMaps'][-1]
        self.assertEqual(m['kind'],'camp');self.assertFalse(m['revealed']);self.assertNotIn('GM-ONLY-TRAP',json.dumps(m))
        with self.assertRaises(ValueError):self.game.action(self.gs,{**command,'replace':True})
        self.game.action(self.gs,dict(action='locationMapDelete',id=m['id'],version=m['version'],confirmed=True))
        self.assertEqual(self.game.view(self.gs)['locationMaps'],[])

    def test_invalid_settings_do_not_change_campaign(self):
        revision=self.game.view(self.gs)['revision']
        for cfg in ({'kind':'unknown'},{'water':'yes'},{'seed':'x'*81},{'size':False}):
            with self.assertRaises(ValueError):self.game.action(self.gs,dict(action='locationMapGenerate',title='Test',settings=cfg))
        self.assertEqual(revision,self.game.view(self.gs)['revision'])

    def test_art_and_metric_dimensions_preserve_center_and_validate_selection(self):
        m=self.create();f=m['features'][0];cx=f['x']+f['w']/2;cy=f['y']+f['h']/2
        data=dict(action='locationMapFeature',id=m['id'],version=m['version'],feature=f['id'],label='Дом',note='',gmNote='',secret=False,art='manor',widthMeters=12,heightMeters=10)
        m=self.game.action(self.gs,data)['locationMaps'][0];f=m['features'][0]
        self.assertEqual(f['art'],'manor');self.assertEqual(f['w'],48);self.assertEqual(f['h'],40)
        self.assertEqual(f['x']+f['w']/2,cx);self.assertEqual(f['y']+f['h']/2,cy)
        for invalid in (dict(art='https://outside/image.png'),dict(widthMeters=float('inf')),dict(heightMeters=-1)):
            with self.assertRaises(ValueError):self.game.action(self.gs,{**data,'version':m['version'],**invalid})

    def test_restart_and_campaign_restore_preserve_maps_and_reject_old_edits(self):
        original=self.create()
        point=checkpoint(self.game,self.gs,dict(operation='create',scope='campaign'))
        changed=self.edit(original)
        self.game.db.close();self.game=Game(self.path,reference_root=Path(self.tmp.name)/'local-assets')
        auth=self.game.reconnect(dict(code=self.gm['code'],resume=self.gm['resume']));self.gs=self.game.session(auth['token'])
        self.assertEqual(self.game.view(self.gs)['locationMaps'][0],changed)
        checkpoint(self.game,self.gs,dict(operation='restore',scope='campaign',id=point['id'],confirmed=True,revision=self.game.view(self.gs)['revision']))
        restored=self.game.view(self.gs)['locationMaps'][0]
        self.assertEqual(restored['features'],original['features']);self.assertGreater(restored['version'],changed['version'])
        with self.assertRaises(ValueError):self.edit(changed)

    def manual(self,m,**data):
        return self.game.action(self.gs,dict(action='locationMapEdit',id=m['id'],version=m['version'],**data))['locationMaps'][0]

    def test_manual_objects_move_delete_and_stale_edits(self):
        m=self.create();n=len(m['features'])
        m=self.manual(m,op='add',art='tavern',widthMeters=12,heightMeters=10,point=[200,200],label='Новая таверна')
        f=m['features'][-1];self.assertEqual((f['w'],f['h']),(48,40));self.assertEqual(len(m['features']),n+1)
        old=m;m=self.manual(m,op='move',kind='feature',target=f['id'],point=[300,320])
        self.assertEqual((m['features'][-1]['x'],m['features'][-1]['y']),(300,320))
        with self.assertRaises(ValueError):self.manual(old,op='remove',kind='feature',target=f['id'])
        with self.assertRaises(PermissionError):self.game.action(self.ps,dict(action='locationMapEdit',id=m['id'],version=m['version'],op='remove',kind='feature',target=f['id']))
        for data in [dict(op='move',kind='feature',target=f['id'],point=[m['width'],20]),dict(op='add',art='unknown',point=[200,200]),dict(op='move',kind='feature',target=f['id'],point=[float('nan'),20]),dict(op='path',style='wall',points=[[1,1],[1,1]]),dict(op='path',style='wall',points=[[0,0],[-1,4]])]:
            with self.assertRaises(ValueError):self.manual(m,**data)
            self.assertEqual(self.game.view(self.gs)['locationMaps'][0],m)
        m=self.manual(m,op='remove',kind='feature',target=f['id']);self.assertEqual(len(m['features']),n)

    def test_manual_corridors_follow_rooms_and_are_removed_with_rooms(self):
        m=self.game.action(self.gs,dict(action='locationMapGenerate',title='Залы',settings=dict(kind='cave',seed='editor')))['locationMaps'][0]
        f=m['features'][0];paths=json.loads(json.dumps(m['paths']));points=json.loads(json.dumps(f['points']))
        m=self.manual(m,op='move',kind='feature',target=f['id'],point=[f['x']+10,f['y']+20])
        self.assertEqual(m['features'][0]['points'],[[x+10,y+20] for x,y in points])
        for old,new in zip(paths,m['paths']):
            if f['id'] in old['refs']:
                i=0 if len(old['refs'])>1 and old['refs'][0]==f['id'] else -1
                self.assertEqual(new['points'][i],[old['points'][i][0]+10,old['points'][i][1]+20])
        m=self.manual(m,op='remove',kind='feature',target=f['id'])
        self.assertFalse(any(f['id'] in p['refs'] for p in m['paths']))

    def test_manual_paths_tokens_privacy_and_restart(self):
        public=support.CampaignTests.make_npc(self)
        hidden=support.CampaignTests.make_npc(self,hidden=True)
        m=self.create()
        for style in ('road','wall','palisade','passage'):
            m=self.manual(m,op='path',style=style,points=[[100,100],[200,100],[200,200]],secret=style=='passage')
        for c,secret in [(public,False),(hidden,False)]:
            m=self.manual(m,op='token',characterId=c['id'],point=[150,150],secret=secret)
        with self.assertRaises(ValueError):self.manual(m,op='token',characterId=public['id'],point=[200,200])
        token=m['tokens'][0];m=self.manual(m,op='move',kind='token',target=token['id'],point=[250,260])
        m=self.game.action(self.gs,dict(action='locationMapReveal',id=m['id'],version=m['version'],revealed=True))['locationMaps'][0]
        safe=self.game.view(self.ps)['locationMaps'][0]
        self.assertEqual([t['characterId'] for t in safe['tokens']],[public['id']]);self.assertEqual(safe['tokens'][0]['x'],250)
        self.assertFalse(any(p.get('secret') or p['style']=='passage' for p in safe['paths']))
        self.assertEqual(capture(self.game.room(self.gs['room']),'campaign')['locationMaps'][0],m)
        self.game.db.close();self.game=Game(self.path,reference_root=Path(self.tmp.name)/'local-assets')
        auth=self.game.reconnect(dict(code=self.gm['code'],resume=self.gm['resume']));self.gs=self.game.session(auth['token'])
        self.assertEqual(self.game.view(self.gs)['locationMaps'][0],m)
        m=self.manual(m,op='remove',kind='token',target=token['id'])
        m=self.manual(m,op='token',characterId=public['id'],point=[100,100],secret=True)
        # Explicitly secret placement stays hidden even for a public character.
        from location_maps import redact
        room=self.game.room(self.gs['room']);redact(room);self.assertEqual(room['locationMaps'][0]['tokens'],[])
        m=self.manual(m,op='remove',kind='path',target=len(m['paths'])-1)
        self.assertFalse(any(p['style']=='passage' for p in m['paths']))
        self.game.action(self.gs,dict(action='deleteCharacter',id=hidden['id']))
        changed=self.game.view(self.gs)['locationMaps'][0]
        self.assertGreater(changed['version'],m['version'])
        self.assertFalse(any(t['characterId']==hidden['id'] for t in changed['tokens']))

    def undo(self,m):
        return self.game.action(self.gs,dict(action='locationMapUndo',id=m['id'],version=m['version']))['locationMaps'][0]

    def test_rotation_bounds_movement_and_undo(self):
        m=self.create();m=self.manual(m,op='add',art='bridge',widthMeters=20,heightMeters=4,point=[300,300],label='Мост')
        f=m['features'][-1];before=m
        m=self.manual(m,op='rotate',kind='feature',target=f['id'],angle=-90)
        self.assertEqual(m['features'][-1]['rotation'],270)
        m=self.manual(m,op='move',kind='feature',target=f['id'],point=[400,400])
        self.assertEqual(m['features'][-1]['rotation'],270)
        m=self.undo(m);self.assertEqual(m['features'][-1]['x'],f['x'])
        m=self.undo(m);self.assertEqual(m['features'],before['features'])
        m=self.manual(m,op='move',kind='feature',target=f['id'],point=[0,0])
        for angle in (90,float('nan'),361,True,'90'):
            with self.assertRaises(ValueError):self.manual(m,op='rotate',kind='feature',target=f['id'],angle=angle)
        m=self.undo(m)
        m=self.manual(m,op='rotate',kind='feature',target=f['id'],angle=45)
        with self.assertRaises(ValueError):self.manual(m,op='move',kind='feature',target=f['id'],point=[0,0])
        m=self.undo(m);m=self.undo(m);self.assertNotIn(f['id'],[f['id'] for f in m['features']])
        self.assertEqual(m['undoCount'],0)
        with self.assertRaises(ValueError):self.undo(m)

    def test_undo_history_is_bounded_private_persistent_and_versioned(self):
        m=self.create();f=m['features'][0]
        for n in range(25):m=self.manual(m,op='rotate',kind='feature',target=f['id'],angle=n+1)
        self.assertEqual(m['undoCount'],20)
        room=self.game.room(self.gs['room']);self.assertEqual(len(room['locationHistory'][m['id']]),20)
        self.assertNotIn('locationHistory',self.game.view(self.gs))
        self.game.action(self.gs,dict(action='locationMapReveal',id=m['id'],version=m['version'],revealed=True))
        public=self.game.view(self.ps);self.assertNotIn('locationHistory',public);self.assertNotIn('undoCount',public['locationMaps'][0])
        with self.assertRaises(PermissionError):self.game.action(self.ps,dict(action='locationMapUndo',id=m['id'],version=m['version']))
        with self.assertRaises(ValueError):self.undo(m)
        self.game.db.close();self.game=Game(self.path,reference_root=Path(self.tmp.name)/'local-assets')
        auth=self.game.reconnect(dict(code=self.gm['code'],resume=self.gm['resume']));self.gs=self.game.session(auth['token'])
        m=self.game.view(self.gs)['locationMaps'][0]
        for n in range(20):m=self.undo(m)
        self.assertEqual(m['features'][0]['rotation'],5);self.assertEqual(m['undoCount'],0);self.assertTrue(m['revealed'])

    def test_undo_restores_deleted_room_corridors_notes_paths_and_tokens(self):
        m=self.game.action(self.gs,dict(action='locationMapGenerate',title='Залы',settings=dict(kind='dungeon',seed='undo')))['locationMaps'][0]
        before=m;m=self.manual(m,op='remove',kind='feature',target=m['features'][0]['id']);m=self.undo(m)
        self.assertEqual(m['features'],before['features']);self.assertEqual(m['paths'],before['paths'])
        m=self.edit(m);m=self.undo(m);self.assertEqual(m['features'],before['features'])
        npc=support.CampaignTests.make_npc(self);m=self.manual(m,op='token',characterId=npc['id'],point=[300,300]);t=m['tokens'][0]
        m=self.manual(m,op='rotate',kind='token',target=t['id'],angle=90);self.assertEqual(m['tokens'][0]['rotation'],90)
        m=self.manual(m,op='remove',kind='token',target=t['id']);m=self.undo(m);self.assertEqual(m['tokens'][0]['rotation'],90)
        m=self.manual(m,op='path',style='wall',points=[[200,200],[300,200]])
        old=m['paths'][-1];m=self.manual(m,op='rotate',kind='path',target=len(m['paths'])-1,angle=90)
        self.assertEqual(m['paths'][-1]['points'],[[250,150],[250,250]])
        m=self.undo(m);self.assertEqual(m['paths'][-1],old)
        self.game.action(self.gs,dict(action='deleteCharacter',id=npc['id']))
        m=self.game.view(self.gs)['locationMaps'][0];self.assertEqual(m['undoCount'],0)
        with self.assertRaises(ValueError):self.undo(m)

    def test_line_rotation_keeps_pivot_and_new_generation_clears_history(self):
        from location_editor import rotate_point
        m=self.create();pts=[[200,200],[300,200],[250,260]]
        m=self.manual(m,op='path',style='road',points=pts);index=len(m['paths'])-1
        m=self.manual(m,op='rotate',kind='path',target=index,angle=45)
        m=self.manual(m,op='rotate',kind='path',target=index,angle=90)
        for actual,original in zip(m['paths'][index]['points'],pts):
            expected=rotate_point(original,[250,230],90)
            self.assertAlmostEqual(actual[0],expected[0],places=2);self.assertAlmostEqual(actual[1],expected[1],places=2)
        self.game.action(self.gs,dict(action='locationMapGenerate',id=m['id'],version=m['version'],replace=True,title='Новый план',settings=dict(kind='camp')))
        m=self.game.view(self.gs)['locationMaps'][0];self.assertFalse(m.get('undoCount'))
        with self.assertRaises(ValueError):self.undo(m)

if __name__=='__main__':unittest.main()
