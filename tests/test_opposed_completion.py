import copy
import unittest
from unittest.mock import patch
import test_server as support
from opposed_checks import finish_checks


class OpposedCompletionTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown
    make_pc=support.CampaignTests.make_pc
    make_npc=support.CampaignTests.make_npc

    def pair(self,private=False,defender_roll=True):
        pc=self.make_pc();npc=self.make_npc();self.pc=pc['id'];self.npc=npc['id']
        actor=self.gs if private else self.ps
        v=self.game.action(actor,dict(action='opposedCreate',visibility='hidden' if private else 'public',attacker=dict(character=self.pc,skill='melee'),defender=dict(character=self.npc,skill='melee')))
        self.pair_id=v['opposedChecks'][-1]['id'];self.actor=actor
        with patch('skill_checks.die',return_value=2):
            self.game.action(actor,dict(action='opposedRoll',id=self.pair_id,side='attacker'))
            if defender_roll:self.game.action(self.gs,dict(action='opposedRoll',id=self.pair_id,side='defender'))

    def verify_finished(self,private=False,defender_roll=True):
        state=self.game.view(self.gs)
        for cid in [self.pc,self.npc] if defender_roll else [self.pc]:
            c=next(c for c in state['characters'] if c['id']==cid)
            r=state['gmChecks'][cid] if private else c['runtime']['lastCheck']
            self.assertTrue(r['accepted']);self.assertFalse(r['current']);self.assertFalse(r['pushAvailable'])
        self.game.action(self.gs,dict(action='sessionRecap',operation='open',characters=[self.pc]))

    def test_accept_closes_both_checks_and_allows_session_recap(self):
        self.pair();self.game.action(self.actor,dict(action='opposedAccept',id=self.pair_id));self.verify_finished()

    def test_push_closes_both_checks_and_allows_session_recap(self):
        self.pair()
        with patch('skill_checks.die',return_value=6):self.game.action(self.actor,dict(action='opposedPush',id=self.pair_id))
        self.verify_finished()

    def test_cancel_closes_existing_roll_without_waiting_for_defender(self):
        self.pair(defender_roll=False);self.game.action(self.actor,dict(action='opposedCancel',id=self.pair_id));self.verify_finished(defender_roll=False)

    def test_private_completion_closes_hidden_checks_without_leaking(self):
        self.pair(private=True);self.game.action(self.gs,dict(action='opposedAccept',id=self.pair_id));self.verify_finished(private=True)
        public=self.game.view(self.ps)
        self.assertNotIn('gmChecks',public);self.assertEqual(public['opposedChecks'],[]);self.assertEqual(public['diceRolls'],[])

    def test_legacy_finished_cancelled_and_pruned_pairs_do_not_block_recap(self):
        self.pair()
        original=self.game.room(self.gs['room'])
        for status in ('finished','cancelled','pruned'):
            with self.subTest(status=status):
                room=copy.deepcopy(original)
                if status=='pruned':room['opposedChecks']=[]
                else:
                    room['opposedChecks'][-1]['done']=True
                    room['opposedChecks'][-1]['cancelled']=status=='cancelled'
                self.game.save(room)
                view=self.game.view(self.gs)
                for c in view['characters']:self.assertFalse(c['runtime']['lastCheck']['current'])
                self.game.action(self.gs,dict(action='sessionRecap',operation='open',characters=[self.pc]))

    def test_finalizer_does_not_accept_replacement_rolls(self):
        self.pair();room=self.game.room(self.gs['room']);p=room['opposedChecks'][-1]
        a=next(c for c in room['characters'] if c['id']==self.pc)['runtime']['lastCheck']
        a['id']='new-roll';a.pop('opposed')
        finish_checks(room,p)
        self.assertFalse(a.get('accepted',False))
        b=next(c for c in room['characters'] if c['id']==self.npc)['runtime']['lastCheck']
        self.assertTrue(b['accepted'])


if __name__=='__main__':unittest.main()
