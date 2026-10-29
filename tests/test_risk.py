import json
import unittest
from unittest.mock import patch
import test_server as support

class RiskTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown
    make_pc=support.CampaignTests.make_pc
    make_npc=support.CampaignTests.make_npc

    def test_free_push_once_private_and_separate_penalties(self):
        with patch('server.secrets.randbelow',return_value=1):v=self.game.action(self.ps,dict(action='roll',base=2,skill=2,gear=1,modifier=-3,artifacts=[8,12]))
        roll=v['freeRisk']['roll'];self.assertNotIn('freeChecks',v)
        with self.assertRaises(ValueError):self.game.action(self.gs,dict(action='freePush',roll=roll))
        with patch('free_risk.secrets.randbelow',return_value=0):v=self.game.action(self.ps,dict(action='freePush',roll=roll))
        self.assertIn('урон характеристике 2',v['diceRolls'][-1]['result']);self.assertIn('износ 1',v['diceRolls'][-1]['result'])
        with self.assertRaises(ValueError):self.game.action(self.ps,dict(action='freePush',roll=roll))

    def test_opposed_tie_and_only_attacker_push(self):
        pc=self.make_pc();npc=self.make_npc()
        v=self.game.action(self.ps,dict(action='opposedCreate',attacker=dict(character=pc['id'],skill='melee'),defender=dict(character=npc['id'],skill='melee')));pair=v['opposedChecks'][-1]['id']
        with patch('skill_checks.die',return_value=2):
            v=self.game.action(self.ps,dict(action='opposedRoll',id=pair,side='attacker'))
            with self.assertRaises(ValueError):self.game.action(self.ps,dict(action='opposedPush',id=pair))
            v=self.game.action(self.gs,dict(action='opposedRoll',id=pair,side='defender'))
        self.assertEqual(v['opposedChecks'][-1]['net'],0)
        defender=next(c for c in v['characters'] if c['id']==npc['id'])['runtime']['lastCheck']
        with self.assertRaises(ValueError):self.game.action(self.gs,dict(action='characterPush',character=npc['id'],roll=defender['id']))
        with patch('skill_checks.die',return_value=6):v=self.game.action(self.ps,dict(action='opposedPush',id=pair))
        self.assertTrue(v['opposedChecks'][-1]['done']);self.assertGreater(v['opposedChecks'][-1]['net'],0)
        with self.assertRaises(ValueError):self.game.action(self.ps,dict(action='opposedPush',id=pair))

    def test_combat_continuation_is_private_and_authorized(self):
        pc=self.make_pc();npc=self.make_npc();self.game.action(self.gs,dict(action='combatCreate',units=[dict(id=pc['id'],team='A'),dict(id=npc['id'],team='B')]))
        room=self.game.room(self.gs['room']);b=room['combat'];b.update(phase='combat',round=1,turn=0,order=[pc['id'],npc['id']])
        for i,u in enumerate(b['units']):u.update(q=3+i,r=3,defense='none',slow=1,fast=1)
        self.game.save(room)
        v=self.game.action(self.gs,dict(action='combatAction',revision=room['combatRevision'],visibility='hidden',command=dict(action='punch',target=npc['id'],interactive=True)))
        if not v['combat'].get('pendingRisk'):self.skipTest('All rolled dice locked; no push required')
        risk=v['combat']['pendingRisk'];self.assertNotIn('replay',json.dumps(v));self.assertEqual(self.game.view(self.ps)['combat']['pendingRisk'],{'waiting':True})
        cmd=dict(action='combatAction',revision=v['combatRevision'],command=dict(action='risk',roll=risk['id'],push=False))
        with self.assertRaises(PermissionError):self.game.action(self.ps,cmd)
        v=self.game.action(self.gs,cmd);self.assertFalse(v['combat'].get('pendingRisk'));self.assertFalse(self.game.view(self.ps)['diceRolls'])

    def test_journey_waits_for_owner_choice_then_applies_once(self):
        import journey_risk
        from campaign_rules import state
        pc=self.make_pc();room=self.game.room(self.gs['room']);t=state(room)
        t.update(party=[pc['id']],plans={pc['id']:dict(job='forageFood',role='none',modifier=0,gear=0)},route=[],season='summer',interactiveRisk=True)
        with patch('campaign_rules.secrets.randbelow',return_value=1):journey_risk.resolve(room)
        self.assertIn('journeyRisk',room);self.assertEqual(t['quarter'],0);self.game.save(room)
        v=self.game.view(self.ps);self.assertNotIn('journeyResolution',v);risk=v['journeyRisk']['id']
        with patch('campaign_rules.secrets.randbelow',return_value=5):v=self.game.action(self.ps,dict(action='travelRisk',roll=risk,push=True))
        self.assertNotIn('journeyRisk',v);self.assertEqual(v['journey']['quarter'],0);self.assertEqual(v['journey']['phase'],'resolving')
        with self.assertRaises(ValueError):self.game.action(self.ps,dict(action='travelRisk',roll=risk,push=True))
