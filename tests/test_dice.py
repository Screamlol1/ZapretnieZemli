import json
import unittest
from unittest.mock import patch
import test_server as support
from save_points import capture


class DiceTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown
    make_pc=support.CampaignTests.make_pc
    make_npc=support.CampaignTests.make_npc

    def roll(self, session, **args):
        return self.game.action(session, dict(action='roll',base=3,skill=2,gear=1,**args))

    def test_open_roll_identical_for_everyone_and_persisted(self):
        v=self.roll(self.ps,artifact=12,modifier=-4)
        e=v['diceRolls'][-1]
        self.assertEqual(e,self.game.view(self.gs)['diceRolls'][-1])
        other=self.game.login(dict(name='Другой игрок',code=self.gm['code'],key=self.gm['playerKey']))
        self.assertEqual(e,self.game.view(self.game.session(other['token']))['diceRolls'][-1])
        self.assertEqual([g['kind'] for g in e['groups']],['base','skill','gear','artifact'])
        self.assertTrue(e['groups'][1]['negative'])
        self.assertEqual(len(e['groups'][1]['values']),2)
        self.assertEqual(e['groups'][-1]['sides'],12)
        self.assertEqual(e,self.game.room(self.gs['room'])['diceRolls'][-1])

    def test_hidden_roll_is_server_redacted_and_player_cannot_request_it(self):
        before=self.game.view(self.ps)['revision']
        with self.assertRaises(PermissionError):self.roll(self.ps,visibility='hidden')
        self.assertEqual(before,self.game.view(self.ps)['revision'])
        v=self.roll(self.gs,visibility='hidden');e=v['diceRolls'][-1]
        self.assertTrue(e['private'])
        public=self.game.view(self.ps)
        self.assertEqual(public['diceRolls'],[])
        self.assertNotIn(e['id'],json.dumps(public))
        self.assertFalse(any(x.get('private') for x in public['log']))
        self.roll(self.gs)
        self.assertEqual(len(self.game.view(self.ps)['diceRolls']),1)

    @patch('skill_checks.die',return_value=2)
    def test_private_character_check_and_push_never_enter_player_sheet(self,_):
        c=self.make_pc()
        v=self.game.action(self.gs,dict(action='characterRoll',character=c['id'],skill='survive',visibility='hidden',note='secret dice note',revision=self.game.view(self.gs)['revision']))
        r=v['gmChecks'][c['id']]
        for session in (self.ps,):
            self.assertNotIn('secret dice note',json.dumps(self.game.view(session)))
            with self.assertRaises(ValueError):self.game.action(session,dict(action='characterPush',character=c['id'],roll=r['id']))
        room=self.game.room(self.gs['room']);char=next(x for x in room['characters'] if x['id']==c['id'])
        self.assertNotIn('secret dice note',json.dumps(capture(room,'character',char)))
        v=self.game.action(self.gs,dict(action='characterPush',character=c['id'],roll=r['id'],visibility='public'))
        self.assertTrue(v['diceRolls'][-1]['private'])
        self.assertTrue(v['gmChecks'][c['id']]['pushed'])
        self.assertEqual(self.game.view(self.ps)['diceRolls'],[])
        with self.assertRaises(ValueError):self.game.action(self.gs,dict(action='characterPush',character=c['id'],roll=r['id']))

    def test_player_character_checks_cannot_be_hidden(self):
        c=self.make_pc()
        with self.assertRaises(PermissionError):self.game.action(self.ps,dict(action='characterRoll',character=c['id'],skill='survive',visibility='hidden',revision=self.game.view(self.gs)['revision']))
        v=self.game.action(self.ps,dict(action='characterRoll',character=c['id'],skill='survive',revision=self.game.view(self.gs)['revision']))
        self.assertFalse(v['diceRolls'][-1]['private'])

    def test_hidden_combat_dice_do_not_leak_through_combat_log(self):
        pc=self.make_pc();npc=self.make_npc()
        self.game.action(self.gs,dict(action='combatCreate',units=[dict(id=pc['id'],team='A'),dict(id=npc['id'],team='B')]))
        room=self.game.room(self.gs['room']);b=room['combat'];b.update(phase='combat',round=1,turn=0,order=[npc['id'],pc['id']])
        for i,u in enumerate(b['units']):u.update(q=3+i,r=3,defense='none',slow=1,fast=1)
        self.game.save(room);old=self.game.view(self.ps)['combat']['log']
        v=self.game.action(self.gs,dict(action='combatAction',revision=room['combatRevision'],visibility='hidden',command=dict(action='punch',target=pc['id'])))
        self.assertTrue(v['diceRolls'])
        public=self.game.view(self.ps)
        self.assertEqual(public['combat']['log'],old)
        for e in v['diceRolls']:self.assertNotIn(e['id'],json.dumps(public))
        self.assertNotIn('commandLog',json.dumps(public))
        self.assertNotIn('diceEvents',json.dumps(public))
        # Following public actions do not republish a previous private trace.
        v=self.game.action(self.gs,dict(action='combatAction',revision=v['combatRevision'],command=dict(action='defense',unit=npc['id'],value='none')))
        self.assertEqual(self.game.view(self.ps)['diceRolls'],[])

    def test_invalid_pool_does_not_create_event(self):
        for value in (True,7,'12',-1):
            with self.assertRaises(ValueError):self.roll(self.gs,artifact=value)
        self.assertEqual(self.game.view(self.gs).get('diceRolls',[]),[])

if __name__=='__main__':unittest.main()
