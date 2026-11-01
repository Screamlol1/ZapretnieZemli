import json
import unittest
from unittest.mock import patch
import test_server as support
import save_points


class InjuryServerTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown
    make_pc=support.CampaignTests.make_pc
    make_npc=support.CampaignTests.make_npc

    def test_player_treatment_survives_restart_and_blocks_interleaved_changes(self):
        healer=self.make_pc();target=self.make_npc()
        with patch('injuries.die',return_value=2):
            state=self.game.action(self.gs,dict(action='injury',op='assign',character=target['id'],table='slash',result=51))
        injury=next(c for c in state['characters'] if c['id']==target['id'])['runtime']['injuries'][0]
        with patch('injuries.die',return_value=6):
            state=self.game.action(self.ps,dict(action='injury',op='treat',healer=healer['id'],target=target['id'],purpose='save',injury=injury['id'],nearby=True))
        roll=state['treatment']['roll']['id']
        with self.assertRaises(ValueError):self.game.action(self.ps,dict(action='characterRoll',character=healer['id'],skill='heal',revision=state['revision']))
        with self.assertRaises(ValueError):self.game.action(self.gs,dict(action='runtime',id=target['id'],current=target['runtime']['current'],wp=0))
        self.game.db.close();self.game=support.Game(self.path,reference_root=self.path.parent/'local-assets')
        self.assertEqual(self.game.view(self.ps)['treatment']['roll']['id'],roll)
        state=self.game.action(self.ps,dict(action='injury',op='accept',roll=roll))
        self.assertNotIn('treatment',state)
        summary=next(c for c in state['medicalTargets'] if c['id']==target['id'])
        self.assertTrue(summary['injuries'][0]['stabilized'])
        self.assertNotIn('attempts',summary['injuries'][0])
        saved=save_points.apply(self.game,self.gs,dict(operation='create',scope='campaign',label='После лечения'))
        self.assertTrue(next(c for c in saved['document']['state']['characters'] if c['id']==target['id'])['runtime']['injuries'][0]['stabilized'])

    def test_public_health_excludes_hidden_npc_and_private_treatment_details(self):
        healer=self.make_pc();target=self.make_npc(True)
        with patch('injuries.die',return_value=2):
            state=self.game.action(self.gs,dict(action='injury',op='assign',character=target['id'],table='slash',result=51))
        injury=next(c for c in state['characters'] if c['id']==target['id'])['runtime']['injuries'][0]
        with self.assertRaises(PermissionError):self.game.action(self.ps,dict(action='injury',op='treat',healer=healer['id'],target=target['id'],purpose='save',injury=injury['id'],nearby=True))
        with patch('injuries.die',return_value=6):
            state=self.game.action(self.gs,dict(action='injury',op='treat',healer=healer['id'],target=target['id'],purpose='save',injury=injury['id'],nearby=True,visibility='hidden'))
        roll=state['treatment']['roll']['id'];public=self.game.view(self.ps)
        self.assertEqual(public['treatment'],dict(waiting=True))
        self.assertNotIn(target['id'],json.dumps(public,ensure_ascii=False))
        self.game.action(self.gs,dict(action='injury',op='accept',roll=roll))
        public=self.game.view(self.ps)
        self.assertNotIn(target['id'],json.dumps(public,ensure_ascii=False))
        self.assertNotIn('lastTreatment',public['characters'][0]['runtime'])

    def test_attribute_break_requires_gm_injury_resolution_and_persists(self):
        c=self.make_pc();cur=dict(c['runtime']['current']);cur['str']=0
        state=self.game.action(self.gs,dict(action='runtime',id=c['id'],current=cur,wp=1))
        health=next(t for t in state['medicalTargets'] if t['id']==c['id'])
        self.assertEqual(health['broken'],['str']);pending=health['injuries'][0]
        with self.assertRaises(PermissionError):self.game.action(self.ps,dict(action='injury',op='assign',character=c['id'],injury=pending['id'],table='blunt',result=41))
        with patch('injuries.die',return_value=2):
            self.game.action(self.gs,dict(action='injury',op='assign',character=c['id'],injury=pending['id'],table='blunt',result=41))
        self.game.db.close();self.game=support.Game(self.path,reference_root=self.path.parent/'local-assets')
        hero=self.game.view(self.ps)['characters'][0]
        self.assertEqual(hero['runtime']['injuries'][0]['mechanics']['modifiers']['melee'],-2)


if __name__=='__main__':unittest.main()
