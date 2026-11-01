import json
import subprocess
from pathlib import Path
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
        self.assertEqual([g['kind'] for g in e['groups']],['base','skill','gear','penalty','artifact'])
        self.assertFalse(e['groups'][1]['negative'])
        self.assertTrue(e['groups'][3]['negative'])
        self.assertEqual(len(e['groups'][3]['values']),4)
        self.assertEqual(len(e['groups'][1]['values']),2)
        self.assertEqual(e['groups'][-1]['sides'],12)
        self.assertEqual(e,self.game.room(self.gs['room'])['diceRolls'][-1])

    @patch('server.secrets.randbelow',side_effect=lambda sides:sides-1)
    def test_free_check_subtracts_penalty_successes_after_artifacts(self,_):
        e=self.roll(self.ps,artifact=12,modifier=-4)['diceRolls'][-1]
        self.assertEqual(e['result'],'Успехов: 10 − 4 = 6.')

    def test_skill_counts_keep_full_skill_even_for_small_penalties(self):
        from dice_pools import skill_counts
        for skill in (0,2,4):
            for penalty in (1,2,5):self.assertEqual(skill_counts(skill,-penalty),(skill,penalty))
        self.assertEqual(skill_counts(2,1,-4),(3,4))
        from campaign_rules import check
        c=dict(id='sample',name='Герой',sheet=dict(attrs=dict(wit=2),skills=dict(survive=2)))
        with patch('campaign_rules.dice',side_effect=lambda n:[6]*n):r=check(c,'survive',[1,-4])
        self.assertEqual(len(r['skillDice']),3);self.assertEqual(r['penalty'],[6]*4)
        self.assertEqual(r['hits'],1)

    @patch('server.secrets.randbelow',side_effect=lambda sides:sides-1)
    def test_mixed_artifact_pool_sums_every_die_and_preserves_penalties(self,_):
        e=self.roll(self.ps,artifacts=[8,8,10,12],modifier=-4)['diceRolls'][-1]
        art=[g for g in e['groups'] if g['kind']=='artifact']
        self.assertEqual([(g['sides'],g['values']) for g in art],[(8,[8,8]),(10,[10]),(12,[12])])
        self.assertEqual(e['result'],'Успехов: 17 − 4 = 13.')
        self.assertEqual(e,self.game.view(self.gs)['diceRolls'][-1])
        revision=self.game.view(self.gs)['revision']
        for pool in ([6],[True],[8]*11,'D8',None):
            with self.assertRaises(ValueError):self.roll(self.ps,artifacts=pool)
        self.assertEqual(revision,self.game.view(self.gs)['revision'])

    def test_mixed_artifact_push_keeps_successes_and_rerolls_matching_die_sizes(self):
        c=self.make_pc()
        with patch('skill_checks.die',return_value=6):
            self.game.action(self.ps,dict(action='characterRoll',character=c['id'],skill='melee',artifacts=[8,10,12],revision=self.game.view(self.gs)['revision']))
        room=self.game.room(self.gs['room']);r=room['characters'][0]['runtime']['lastCheck']
        r['artifacts']=[dict(sides=8,value=8),dict(sides=10,value=2),dict(sides=12,value=5)];self.game.save(room)
        with patch('skill_checks.die',side_effect=lambda sides=6:sides) as die:
            v=self.game.action(self.ps,dict(action='characterPush',character=c['id'],roll=r['id']))
        result=v['characters'][0]['runtime']['lastCheck']
        self.assertEqual([a['value'] for a in result['artifacts']],[8,10,12])
        self.assertEqual([a['held'] for a in result['artifacts']],[True,False,False])
        self.assertEqual([call.args for call in die.call_args_list],[(10,),(12,)])
        self.assertEqual((result['damage'],result['wear']),(0,0))
        self.assertEqual(result['hits'],len(r['base'])+len(r['skillDice'])+9)
        self.assertEqual([g['held'] for g in v['diceRolls'][-1]['groups'] if g['kind']=='artifact'],[[True],[False],[False]])

    def test_penalty_push_locks_sixes_rerolls_ones_without_damage(self):
        c=self.make_pc();revision=self.game.view(self.gs)['revision']
        with patch('skill_checks.die',return_value=6):
            v=self.game.action(self.ps,dict(action='characterRoll',character=c['id'],skill='melee',modifier=-2,revision=revision))
        room=self.game.room(self.gs['room']);r=room['characters'][0]['runtime']['lastCheck']
        self.assertEqual(len(r['skillDice']),c['sheet']['skills']['melee'])
        self.assertEqual(r['penalty'],[6,6])
        r['penalty']=[6,1];self.game.save(room)
        with patch('skill_checks.die',return_value=2) as die:
            v=self.game.action(self.ps,dict(action='characterPush',character=c['id'],roll=r['id']))
        r=v['characters'][0]['runtime']['lastCheck']
        self.assertEqual(die.call_count,1);self.assertEqual(r['penalty'],[6,2])
        self.assertEqual(r['held']['penalty'],[True,False])
        self.assertEqual((r['damage'],r['wear']),(0,0))
        self.assertEqual(r['hits'],len(r['base'])+len(r['skillDice'])-1)

    def test_legacy_pending_push_keeps_original_pool(self):
        c=self.make_pc()
        with patch('skill_checks.die',return_value=6):
            self.game.action(self.ps,dict(action='characterRoll',character=c['id'],skill='lore',modifier=-2,revision=self.game.view(self.gs)['revision']))
        room=self.game.room(self.gs['room']);r=room['characters'][0]['runtime']['lastCheck']
        r.pop('poolRule');r.pop('penalty');r.update(negative=True,skillDice=[6,2])
        self.game.save(room)
        with patch('skill_checks.die',return_value=2):
            v=self.game.action(self.ps,dict(action='characterPush',character=c['id'],roll=r['id']))
        r=v['characters'][0]['runtime']['lastCheck']
        self.assertEqual(r['skillDice'],[6,2]);self.assertTrue(r['negative'])
        self.assertEqual(r['penalty'],[]);self.assertEqual(r['hits'],len(r['base'])-1)

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
        self.assertTrue(v['combat']['event']['private'])
        self.assertNotIn('event',public['combat'])
        self.assertEqual(self.game.view(self.gs)['combat']['event'],v['combat']['event'])
        for e in v['diceRolls']:self.assertNotIn(e['id'],json.dumps(public))
        self.assertNotIn('commandLog',json.dumps(public))
        self.assertNotIn('diceEvents',json.dumps(public))
        # Campaign rolls always wait for explicit decisions, even when an old
        # client omits interactive. Secret continuation stays secret as well.
        for _ in range(8):
            pending=v['combat'].get('pendingRisk')
            if not pending:break
            self.assertTrue(pending['private'])
            self.assertEqual(self.game.view(self.ps)['combat']['pendingRisk'],{'waiting':True})
            v=self.game.action(self.gs,dict(action='combatAction',revision=v['combatRevision'],command=dict(action='risk',roll=pending['id'],push=False,wp=0)))
            self.assertTrue(v['combat']['event']['private'])
            self.assertNotIn('event',self.game.view(self.ps)['combat'])
        self.assertFalse(v['combat'].get('pendingRisk'))
        # Following public actions do not republish a previous private trace.
        v=self.game.action(self.gs,dict(action='combatAction',revision=v['combatRevision'],command=dict(action='defense',unit=npc['id'],value='none')))
        self.assertEqual(self.game.view(self.ps)['diceRolls'],[])
        self.assertFalse(v['combat']['event']['private'])
        self.assertEqual(self.game.view(self.ps)['combat']['event'],v['combat']['event'])

    def test_invalid_pool_does_not_create_event(self):
        for value in (True,7,'12',-1):
            with self.assertRaises(ValueError):self.roll(self.gs,artifact=value)
        self.assertEqual(self.game.view(self.gs).get('diceRolls',[]),[])

    def pending_weapon_attack(self,success):
        pc=self.make_pc();npc=self.make_npc()
        self.game.action(self.gs,dict(action='combatCreate',units=[dict(id=pc['id'],team='A'),dict(id=npc['id'],team='B')]))
        room=self.game.room(self.gs['room']);b=room['combat'];b.update(phase='combat',round=1,turn=0,order=[pc['id'],npc['id']])
        for i,u in enumerate(b['units']):
            u.update(q=3+i,r=3,defense='none',fast=1,slow=1,armor=0,maxArmor=0,armorSources=[],str=8,maxStr=8,weapon='sword',gear=1,wp=0,talents={},kin='human',prideAvailable=False)
            u['weaponStats']=dict(name='Тестовый меч',bonus=2,damage=2)
        source="""import {riskCommand} from './combat-risk.mjs';import {attack} from './public/tools/battle-rules.js';let input='';for await(const s of process.stdin)input+=s;const {battle,success}=JSON.parse(input);let n=0;const result=riskCommand(battle,{action:'slash',target:battle.order[1],interactive:true},(s,c,d)=>attack(s,c.target,'slash',{},d),()=>success&&n++===0?6:2);process.stdout.write(JSON.stringify(result));"""
        out=subprocess.run(['node','--input-type=module','-e',source],input=json.dumps(dict(battle=b,success=success)),text=True,encoding='utf-8',capture_output=True,cwd=Path(__file__).parents[1],check=True)
        b=json.loads(out.stdout);b['pendingRisk']['private']=False;b.pop('diceEvents',None);b.pop('commandLog',None);b.pop('attackImpacts',None)
        room['combat']=b;self.game.save(room);return pc['id'],npc['id'],room

    def test_accept_weapon_roll_reports_original_action_and_actual_target_hit(self):
        actor,target,room=self.pending_weapon_attack(True)
        v=self.game.action(self.gs,dict(action='combatAction',revision=room['combatRevision'],command=dict(action='risk',roll=room['combat']['pendingRisk']['id'],push=False)))
        event=v['combat']['event']
        self.assertFalse(v['combat'].get('pendingRisk'))
        self.assertEqual((event['actor'],event['target'],event['action'],event['kind']),(actor,target,'slash','strike'))
        self.assertEqual(event['hitIds'],[target]);self.assertNotIn('attackImpacts',v['combat'])
        self.assertEqual(event,self.game.view(self.ps)['combat']['event'])

    def test_failed_push_self_damage_is_not_a_weapon_impact(self):
        actor,target,room=self.pending_weapon_attack(False)
        # Pre-record only the pending push's future draws for a deterministic replay.
        room['combat']['pendingRisk']['replay']['draws'].extend([dict(sides=6,value=1)]*100)
        self.game.save(room)
        v=self.game.action(self.gs,dict(action='combatAction',revision=room['combatRevision'],command=dict(action='risk',roll=room['combat']['pendingRisk']['id'],push=True)))
        units={u['id']:u for u in v['combat']['units']}
        self.assertLess(units[actor]['str'],8);self.assertLess(units[actor]['gear'],1)
        self.assertEqual(units[target]['str'],8)
        self.assertEqual(v['combat']['event']['hitIds'],[])
        self.assertNotIn('attackImpacts',v['combat'])

if __name__=='__main__':unittest.main()
