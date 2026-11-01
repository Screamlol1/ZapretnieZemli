import json
import unittest
from pathlib import Path
import test_server as support
from server import Game
from save_points import apply


class SaveTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown
    make_pc=support.CampaignTests.make_pc
    make_npc=support.CampaignTests.make_npc

    def call(self,operation,session=None,scope='character',**data):
        return apply(self.game,session or self.ps,dict(operation=operation,scope=scope,**data))

    def test_player_full_copy_during_battle_keeps_wounds_items_and_no_secrets(self):
        c=self.make_pc();self.game.action(self.ps,dict(action='inventoryOpen',character=c['id']))
        room=self.game.room(self.ps['room']);hero=room['characters'][0]
        hero['runtime'].update(current=dict(str=1,agi=2,wit=1,emp=2),wp=4,coins=dict(gold=2,silver=1,copper=7))
        room['items'][0].update(wear=1,gmNote='SECRET-GM',maintenanceNote='SECRET-REPAIR')
        room['combat']=dict(phase='combat',units=[dict(id=c['id'],str=1,slow=0,fast=1)])
        before=json.dumps(room,sort_keys=True);self.game.save(room)
        result=self.call('create',character=c['id'],label='После удара')
        payload=result['document']['state'];self.assertEqual(payload['character']['runtime']['wp'],4)
        self.assertEqual(payload['items'][0]['wear'],1);self.assertEqual(payload['combatUnit']['slow'],0)
        text=json.dumps(result);self.assertNotIn('SECRET-GM',text);self.assertNotIn('SECRET-REPAIR',text)
        for key in ('gmKey','playerKey','identities','resume'):self.assertNotIn(key,result['document']['state'])
        actual=self.game.room(self.ps['room']);actual.pop('savedAt',None);expected=json.loads(before);expected.pop('savedAt',None)
        self.assertEqual(actual,expected)

    def test_permissions_for_foreign_character_campaign_and_guessing_save_id(self):
        c=self.make_pc();npc=self.make_npc()
        point=self.call('create',character=c['id'])
        other=self.game.session(self.game.login(dict(name='Other',code=self.gm['code'],key=self.gm['playerKey']))['token'])
        for operation in ('create','list','get','restore'):
            with self.assertRaises(PermissionError):self.call(operation,session=other,character=c['id'],id=point['id'])
            with self.assertRaises(PermissionError):self.call(operation,character=npc['id'])
            with self.assertRaises(PermissionError):self.call(operation,scope='campaign')
        with self.assertRaises(ValueError):self.call('restore',character=c['id'],id=point['id'],confirmed=True)

    def test_checkpoints_and_live_state_survive_restart(self):
        c=self.make_pc();point=self.call('create',character=c['id'])
        self.game.db.close();self.game=Game(self.path,reference_root=Path(self.tmp.name)/'local-assets')
        auth=self.game.reconnect(dict(code=self.player['code'],resume=self.player['resume']));self.ps=self.game.session(auth['token'])
        self.assertEqual(self.game.view(self.ps)['characters'][0]['id'],c['id'])
        loaded=self.call('get',character=c['id'],id=point['id'])
        self.assertEqual(loaded['document'],point['document'])

    def test_campaign_restore_is_atomic_with_safety_copy_and_current_access(self):
        c=self.make_pc();self.game.action(self.ps,dict(action='inventoryOpen',character=c['id']))
        original=self.game.room(self.gs['room'])
        point=self.call('create',session=self.gs,scope='campaign',label='Начало встречи')
        self.game.action(self.gs,dict(action='chat',text='После сохранения'))
        room=self.game.room(self.gs['room']);room['characters'][0]['runtime']['wp']=7;room['items'][0]['version']=15
        room['combatRevision']=45;room['journey']['revision']=24;self.game.save(room)
        fresh=self.game.login(dict(name='New player',code=self.gm['code'],key=self.gm['playerKey']))
        before=self.game.room(self.gs['room'])
        result=self.call('restore',session=self.gs,scope='campaign',id=point['id'],confirmed=True,revision=before['revision'])
        restored=self.game.room(self.gs['room'])
        self.assertEqual(restored['characters'][0]['runtime'],original['characters'][0]['runtime'])
        self.assertEqual(restored['identities'],before['identities']);self.assertEqual(restored['gmKey'],before['gmKey'])
        self.assertGreater(restored['revision'],before['revision']);self.assertGreater(restored['items'][0]['version'],15)
        self.assertGreater(restored['combatRevision'],45);self.assertGreater(restored['journey']['revision'],24)
        self.assertNotEqual(restored['journey']['cycleId'],before['journey']['cycleId'])
        self.assertEqual(result['state']['revision'],restored['revision'])
        listed=self.call('list',session=self.gs,scope='campaign')['saves']
        safety=self.call('get',session=self.gs,scope='campaign',id=listed[0]['id'])['document']
        self.assertEqual(safety['label'],'Перед восстановлением');self.assertEqual(safety['state']['characters'][0]['runtime']['wp'],7)
        self.assertNotIn('identities',safety['state']);self.assertNotIn('gmKey',safety['state'])

    def test_stale_or_unconfirmed_restore_changes_nothing(self):
        point=self.call('create',session=self.gs,scope='campaign')
        self.game.action(self.gs,dict(action='chat',text='New action'))
        before=self.game.room(self.gs['room'])
        for params in (dict(revision=0,confirmed=True),dict(revision=before['revision'],confirmed=False)):
            with self.assertRaises(ValueError):self.call('restore',session=self.gs,scope='campaign',id=point['id'],**params)
            self.assertEqual(self.game.room(self.gs['room']),before)

    def test_retention_is_per_character_and_latest_twenty(self):
        c=self.make_pc()
        for i in range(22):self.call('create',character=c['id'],label=str(i))
        points=self.call('list',character=c['id'])['saves']
        self.assertEqual(len(points),20);self.assertEqual(points[0]['label'],'21');self.assertEqual(points[-1]['label'],'2')
        with self.assertRaises(ValueError):self.call('create',character=c['id'],label='x'*101)

    def test_hidden_foreign_items_never_enter_personal_copy(self):
        c=self.make_pc();npc=self.make_npc();room=self.game.room(self.gs['room'])
        room['items']=[dict(id='private',location=dict(kind='character',id=npc['id']),name='SECRET-ITEM')]
        self.game.save(room);point=self.call('create',character=c['id'])
        self.assertNotIn('SECRET-ITEM',json.dumps(point));self.assertEqual(point['document']['state']['items'],[])
