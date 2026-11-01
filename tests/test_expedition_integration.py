import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]))
from server import Game
from campaign_rules import state
import test_expedition

class ExpeditionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.db=Path(self.temp.name)/'test.sqlite';self.game=Game(self.db,reference_root=Path(self.temp.name)/'assets')
        login=self.game.login({'name':'Мастер'},True);self.gm=self.game.session(login['token'])
        player=self.game.login({'name':'Игрок','code':login['code'],'key':login['playerKey']});self.player=self.game.session(player['token'])
        fixture=test_expedition.ExpeditionTests();fixture.setUp();room=self.game.room(self.gm['room']);room['worldLayout']='legacy';c=deepcopy(fixture.c);c['owner']=self.player['owner'];c['sheet']['pride']='Я никогда не теряю добычу';room['characters']=[c];room['items']=[fixture.bow];state(room).update(party=['hero'],automatic=False,encounterDay=1);self.game.save(room)
    def tearDown(self):self.game.db.close();self.temp.cleanup()
    def act(self,action,s=None,**data):
        t=state(self.game.room(self.gm['room']));return self.game.action(s or self.gm,dict(action=action,revision=t['revision'],**data))
    def hunt(self):
        self.act('travelPlan',id='hero',job='hunt',role='none',equipped=True)
        with patch('campaign_rules.dice',side_effect=lambda n,sides=6:[6]*n):return self.act('travelAdvance',path=[])['hunts'][-1]
    def test_player_completes_hunt_and_persistence_survives_reload(self):
        h=self.hunt();self.assertEqual(self.game.view(self.player)['hunts'][-1]['id'],h['id'])
        with patch('campaign_rules.dice',side_effect=lambda n,sides=6:[6]*n):v=self.act('expedition',self.player,op='huntRoll',hunt=h['id'],huntRevision=h['revision'],choice=0,method='weapon',item='bow')
        p=v['expeditionCheck'];self.assertEqual(p['roll']['id'],p['id'])
        with self.assertRaisesRegex(ValueError,'экспедиции'):self.act('travelComplete',self.player,complete=True)
        v=self.act('expedition',self.player,op='accept',roll=p['id'],diceEvent=p['diceEvent']);self.assertEqual(v['journey']['finds']['meat'],5)
        self.game.db.close();self.game=Game(self.db,reference_root=Path(self.temp.name)/'assets')
        self.assertEqual(self.game.view(self.player)['hunts'][-1]['stage'],'done');self.assertEqual(self.game.view(self.player)['journey']['finds']['pelts'],3)
    def test_abandoned_hunt_rejects_repeated_command_without_duplicate_changes(self):
        h=self.hunt();self.act('expedition',self.player,op='huntAbandon',hunt=h['id'],huntRevision=h['revision']);before=self.game.room(self.gm['room'])
        with self.assertRaises(ValueError):self.act('expedition',self.player,op='huntRoll',hunt=h['id'],huntRevision=0,choice=0,method='weapon',item='bow')
        after=self.game.room(self.gm['room']);self.assertEqual(before['hunts'],after['hunts']);self.assertEqual(before['characters'],after['characters'])
    def test_hunt_pride_after_gm_approval_changes_pending_result_then_accepts(self):
        h=self.hunt()
        with patch('campaign_rules.dice',side_effect=lambda n,sides=6:[2]*n):v=self.act('expedition',self.player,op='huntRoll',hunt=h['id'],huntRevision=0,choice=0,method='weapon',item='bow')
        p=v['expeditionCheck'];self.assertEqual(p['roll']['hits'],0)
        v=self.act('characterPride',self.player,op='request',character='hero',roll=p['id'],note='Я никогда не теряю добычу.')
        request=v['characters'][0]['runtime']['prideRequest']['id']
        self.act('characterPride',op='approve',character='hero',roll=p['id'],request=request)
        with patch('pride.die',return_value=12):v=self.act('characterPride',self.player,op='roll',character='hero',roll=p['id'],request=request)
        p=v['expeditionCheck'];self.assertEqual(p['roll']['hits'],4);self.assertFalse(p['roll']['pushAvailable'])
        v=self.act('expedition',self.player,op='accept',roll=p['id'],diceEvent=p['diceEvent']);self.assertEqual(v['journey']['finds']['meat'],5)
    def test_hidden_expedition_check_never_leaks_roll_or_signature(self):
        room=self.game.room(self.gm['room']);room['characters'][0]['hidden']=True
        import expedition
        with patch('campaign_rules.dice',side_effect=lambda n,sides=6:[2]*n):expedition.roll_check(room,room['characters'][0],'craft',0,None,dict(kind='repair',vessel='not-used',label='Секретный ремонт'))
        self.game.save(room);v=self.game.view(self.player);self.assertEqual(v['expeditionCheck'],{'waiting':True,'private':True});self.assertFalse(v['diceRolls'])
    def test_vessel_registry_and_catalog_are_saved_and_player_cannot_edit(self):
        v=self.act('expedition',op='vesselCreate',name='Зарница',kind='Лодка',capacity=6,cargoLimit=50);boat=v['vessels'][0]
        self.assertIn('mill',v['expeditionCatalog']['functions']);self.assertEqual(len(v['expeditionCatalog']['prey']),6)
        with self.assertRaises(PermissionError):self.act('expedition',self.player,op='vesselCargo',vessel=boat['id'],vesselRevision=0,cargo=50)
        v=self.act('expedition',op='vesselBoard',vessel=boat['id'],vesselRevision=0,aboard=True);self.assertEqual(v['journey']['vessel'],boat['id'])

if __name__=='__main__':unittest.main()
