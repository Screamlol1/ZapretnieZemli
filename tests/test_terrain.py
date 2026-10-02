import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).parents[1]))
from server import Game
from terrain_map import load_reference

class ImportTests(unittest.TestCase):
    def test_rle_rows_preserve_rgb_bytes_and_reject_truncation(self):
        from tools.import_terrain import unpack_row
        self.assertEqual(unpack_row(bytes([2,139,166,105,254,95]),6),bytes([139,166,105,95,95,95]))
        with self.assertRaises(ValueError):unpack_row(bytes([2,139,166]),3)
        with self.assertRaises(ValueError):unpack_row(bytes([254,95]),2)

class TerrainTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.assets=self.root/'assets';self.assets.mkdir()
        self.image=self.assets/'forbidden-lands.jpg';self.image.write_bytes(b'fixture-image')
        self.data=dict(version=1,layout='ravenland',method='psd-hex-v1',imageSha256=hashlib.sha256(self.image.read_bytes()).hexdigest(),
                       cells={'0,0':{'terrain':'plain'},'1,0':{'terrain':'darkforest'},'2,0':{'terrain':'plain'},
                              '3,0':{'terrain':'highmountain'},'4,0':{'terrain':'water'},'5,0':{'terrainUnknown':'mist'}})
        self.write();self.game=Game(self.root/'test.sqlite',reference_root=self.assets)
        self.auth=self.game.login({'name':'GM'},True);self.gm=self.game.session(self.auth['token'])
        p=self.game.login(dict(name='Player',code=self.auth['code'],key=self.auth['playerKey']));self.player=self.game.session(p['token'])
        room=self.game.room(self.gm['room'])
        room['characters']=[dict(id='hero',name='Hero',kind='pc',owner=self.player['owner'],sheet=dict(attrs=dict(str=3,agi=3,wit=3,emp=3),skills=dict(survive=1)),runtime=dict(current=dict(str=3,agi=3,wit=3,emp=3),wp=0))]
        self.game.save(room)

    def write(self):
        (self.assets/'forbidden-lands-terrain.json').write_text(json.dumps(self.data),encoding='utf-8')

    def tearDown(self):
        self.game.db.close();self.tmp.cleanup()

    def act(self,action,**data):
        revision=self.game.view(self.gm)['journey']['revision']
        return self.game.action(self.gm,dict(action=action,revision=revision,**data))

    def test_reference_terrain_reaches_rules_without_becoming_campaign_edits(self):
        v=self.game.view(self.gm)
        self.assertEqual(v['maps']['world']['1,0']['terrain'],'darkforest')
        self.assertNotIn('_worldBase',v)
        raw=json.loads(self.game.db.execute('SELECT data FROM rooms').fetchone()[0])
        self.assertEqual(raw['maps']['world'],{});self.assertNotIn('_worldBase',raw)
        self.act('travelSetup',party=['hero'],x=0,y=0,season='spring')
        self.act('travelPlan',id='hero',job='hike',role='lead')
        with self.assertRaisesRegex(ValueError,'четверть'):self.act('travelAdvance',path=[dict(x=1,y=0),dict(x=2,y=0)])
        with patch('campaign_rules.dice',side_effect=lambda n,sides=6:[6]*n):
            v=self.act('travelAdvance',path=[dict(x=1,y=0)])
        self.assertEqual(v['journey']['position'],dict(x=1,y=0))
        self.assertIn('Тёмный лес',v['journey']['pending'][-1]['source'])

    def test_overrides_restart_notes_and_fog_preserve_privacy(self):
        self.game.action(self.gm,dict(action='mapLocation',x=1,y=0,label='Site',note='Public',gmNote='Secret',siteType='ruin',siteHidden=True))
        v=self.game.view(self.player)
        self.assertEqual(v['maps']['world']['1,0']['terrain'],'darkforest')
        self.assertNotIn('gmNote',v['maps']['world']['1,0']);self.assertNotIn('label',v['maps']['world']['1,0'])
        self.game.action(self.gm,dict(action='paint',map='world',x=1,y=0,terrain='hills',hidden=True))
        self.assertNotIn('1,0',self.game.view(self.player)['maps']['world'])
        self.game.db.close();self.game=Game(self.root/'test.sqlite',reference_root=self.assets)
        v=self.game.view(self.gm)
        self.assertEqual(v['maps']['world']['1,0']['terrain'],'hills')
        self.assertEqual(v['maps']['world']['1,0']['gmNote'],'Secret')
        self.assertEqual(v['maps']['world']['1,0']['terrainOrigin'],'manual')
        self.assertEqual(v['maps']['world']['5,0']['terrainUnknown'],'mist')

    def test_custom_image_and_legacy_grid_do_not_receive_official_terrain(self):
        self.game.action(self.gm,dict(action='worldLayout',layout='legacy'))
        self.assertEqual(self.game.view(self.gm)['maps']['world'],{})
        self.game.action(self.gm,dict(action='worldLayout',layout='ravenland'))
        room=self.game.room(self.gm['room']);room['mapArtwork']={'style':'upload','revision':1};self.game.save(room)
        self.assertEqual(self.game.view(self.gm)['maps']['world'],{})

    def test_source_binding_and_invalid_coordinates_fail_closed(self):
        self.image.write_bytes(b'other-image');self.assertEqual(load_reference(self.assets),{})
        self.image.write_bytes(b'fixture-image');self.data['cells']['39,24']={'terrain':'forest'};self.write()
        self.assertEqual(load_reference(self.assets),{})

    def test_water_blocks_food_collection_and_mountain_blocks_hiking(self):
        self.act('travelSetup',party=['hero'],x=4,y=0,season='spring')
        self.act('travelPlan',id='hero',job='forageFood',role='none')
        with self.assertRaisesRegex(ValueError,'сбор'):self.act('travelAdvance',path=[])
        self.act('travelPlan',id='hero',job='hike',role='lead')
        with self.assertRaisesRegex(ValueError,'перекрыт'):self.act('travelAdvance',path=[dict(x=3,y=0)])
