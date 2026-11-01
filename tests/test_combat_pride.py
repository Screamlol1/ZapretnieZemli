import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
import test_server as support
from dice_events import publish


class CombatPrideTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown
    make_pc=support.CampaignTests.make_pc
    make_npc=support.CampaignTests.make_npc

    def pending(self):
        c=self.make_pc();victim=self.make_npc();room=self.game.room(self.gs['room'])
        room['characters'][0]['sheet']['pride']='Никто не избежит моего кулака.';self.game.save(room)
        self.game.action(self.gs,dict(action='combatCreate',units=[dict(id=c['id'],team='A'),dict(id=victim['id'],team='B')]))
        room=self.game.room(self.gs['room']);b=room['combat'];b.update(phase='combat',round=1,turn=0,order=[c['id'],victim['id']])
        for n,u in enumerate(b['units']):u.update(q=3+n,r=3,defense='none',fast=1,slow=1,armor=0,maxArmor=0,armorSources=[])
        source="""import {riskCommand} from './combat-risk.mjs';import {attack} from './public/tools/battle-rules.js';let input='';for await (const s of process.stdin) input+=s;const b=JSON.parse(input);const result=riskCommand(b,{action:'punch',target:b.order[1],interactive:true},(s,c,d)=>{s.diceEvents=[];s.commandLog=[];attack(s,c.target,'punch',{},d);},()=>2);process.stdout.write(JSON.stringify(result));"""
        out=subprocess.run(['node','--input-type=module','-e',source],input=json.dumps(b),text=True,encoding='utf-8',capture_output=True,cwd=Path(__file__).parents[1],check=True)
        b=json.loads(out.stdout);room['combat']=b;b['pendingRisk']['private']=False
        for e in b.pop('diceEvents'):publish(room,e['name'],e['label'],e['groups'],e['result'],False,risk=e.get('risk'))
        self.game.save(room);return c['id'],victim['id'],b['pendingRisk']['id']

    def test_pride_replays_combat_once_and_finishes_failed_attack(self):
        cid,target,roll=self.pending()
        self.game.action(self.ps,dict(action='characterPride',op='request',character=cid,roll=roll,note='Гордость героя — его кулачный бой.'))
        req=self.game.room(self.gs['room'])['characters'][0]['runtime']['prideRequest']['id']
        self.game.action(self.gs,dict(action='characterPride',op='approve',character=cid,roll=roll,request=req))
        with patch('pride.die',return_value=12):v=self.game.action(self.ps,dict(action='characterPride',op='roll',character=cid,roll=roll,request=req))
        self.assertFalse(v['combat'].get('pendingRisk'))
        actor=next(u for u in v['combat']['units'] if u['id']==cid);victim=next(u for u in v['combat']['units'] if u['id']==target)
        self.assertEqual(actor['slow'],0);self.assertFalse(actor['prideAvailable']);self.assertLess(victim['str'],victim['maxStr'])
        before=v['revision']
        with self.assertRaises(ValueError):self.game.action(self.ps,dict(action='characterPride',op='roll',character=cid,roll=roll,request=req))
        self.assertEqual(self.game.view(self.gs)['revision'],before)
        self.assertTrue(any(e['label'].startswith('Гордость') and any(g['sides']==12 for g in e['groups']) for e in v['diceRolls']))

    def test_no_client_can_supply_a_pride_die_without_review(self):
        cid,target,roll=self.pending();room=self.game.room(self.gs['room'])
        v=self.game.action(self.ps,dict(action='combatAction',revision=room['combatRevision'],command=dict(action='risk',roll=roll,push=False,pride={'value':12,'hits':4})))
        victim=next(u for u in v['combat']['units'] if u['id']==target)
        self.assertEqual(victim['str'],victim['maxStr'])
        self.assertFalse(any(g['sides']==12 for e in v['diceRolls'] for g in e['groups']))

if __name__=='__main__':unittest.main()
