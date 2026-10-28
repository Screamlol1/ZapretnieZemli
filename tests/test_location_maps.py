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

if __name__=='__main__':unittest.main()
