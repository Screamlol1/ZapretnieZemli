import copy
import json
import unittest
import test_server as support
from session_recap import QUESTIONS
from save_points import apply as saves
from unittest.mock import patch


class SessionRecapTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown
    make_pc=support.CampaignTests.make_pc

    def act(self,operation,session=None,**data):
        r=self.game.room(self.gs['room']).get('sessionRecap') or {}
        return self.game.action(session or self.gs,dict(action='sessionRecap',operation=operation,recap=r.get('id'),version=r.get('version',0),**data))

    def answer(self,cid,session=None,yes=3,note='Тайна принадлежит только мне'):
        r=self.game.room(self.gs['room'])['sessionRecap']
        return self.game.action(session or self.ps,dict(action='sessionRecap',operation='answer',recap=r['id'],character=cid,version=r['answers'].get(cid,{}).get('version',0),answers={q:i<yes for i,q in enumerate(QUESTIONS)},note=note))

    def test_review_awards_once_checkpoint_restart_and_privacy(self):
        c=self.make_pc();cid=c['id']
        self.act('open',characters=[cid]);self.answer(cid)
        self.act('edit',summary='Путь к башне',loot='Старый ключ',gmNote='За башней засада')
        spectator=self.game.login(dict(name='Наблюдатель',code=self.gm['code'],key=self.gm['playerKey']))
        ss=self.game.session(spectator['token']);view=self.game.view(ss)
        self.assertEqual(view['sessionRecap']['answers'],{})
        self.assertNotIn('За башней',json.dumps(view,ensure_ascii=False))
        self.assertNotIn('Тайна принадлежит',json.dumps(view,ensure_ascii=False))
        self.assertIn(cid,view['sessionRecap']['submitted'])
        old=copy.deepcopy(self.game.room(self.gs['room'])['sessionRecap'])
        self.act('finish',confirmed=True,awards={cid:dict(amount=3,note='')})
        room=self.game.room(self.gs['room']);self.assertEqual(room['journey']['session'],2)
        self.assertEqual(next(x for x in room['characters'] if x['id']==cid)['sheet']['progression']['earned'],3)
        self.assertEqual(len(room['sessionHistory']),1)
        self.assertEqual(self.game.db.execute('SELECT COUNT(*) FROM checkpoints WHERE room=?',(room['id'],)).fetchone()[0],1)
        with self.assertRaises(ValueError):
            self.game.action(self.gs,dict(action='sessionRecap',operation='finish',recap=old['id'],version=old['version'],confirmed=True,awards={cid:dict(amount=3,note='')}))
        self.game.db.close();self.game=support.Game(self.path,reference_root=self.path.parent/'local-assets')
        self.assertEqual(self.game.room(room['id'])['sessionHistory'][0]['summary'],'Путь к башне')

    def test_permissions_stale_reviews_independent_answers_and_no_partial_award(self):
        c=self.make_pc();cid=c['id']
        with self.assertRaises(PermissionError):self.act('open',session=self.ps,characters=[cid])
        self.act('open',characters=[cid]);old=copy.deepcopy(self.game.room(self.gs['room'])['sessionRecap'])
        self.answer(cid)
        with self.assertRaises(ValueError):
            self.game.action(self.gs,dict(action='sessionRecap',operation='finish',recap=old['id'],version=old['version'],confirmed=True,awards={cid:dict(amount=3,note='')}))
        with self.assertRaises(PermissionError):self.act('finish',session=self.ps,confirmed=True,awards={cid:dict(amount=3,note='')})
        with self.assertRaisesRegex(ValueError,'поясните'):self.act('finish',confirmed=True,awards={cid:dict(amount=5,note='')})
        self.assertNotIn('progression',next(x for x in self.game.room(self.gs['room'])['characters'] if x['id']==cid)['sheet'])
        self.act('finish',confirmed=True,awards={cid:dict(amount=5,note='Учтены ещё две заслуги после обсуждения')})

    def test_current_actions_and_old_session_cannot_be_bypassed(self):
        c=self.make_pc();cid=c['id'];self.act('open',characters=[cid])
        with self.assertRaises(ValueError):self.game.action(self.gs,dict(action='travelSession'))
        room=self.game.room(self.gs['room']);room['combat']={'phase':'setup'};self.game.save(room)
        with self.assertRaisesRegex(ValueError,'завершите'):self.act('finish',confirmed=True,awards={cid:dict(amount=0,note='Не участвовал')})
        self.assertEqual(self.game.room(self.gs['room'])['journey']['session'],1)
        room['combat']={'phase':'finished'};self.game.save(room)
        self.act('cancel');self.assertIsNone(self.game.room(self.gs['room'])['sessionRecap'])

    def test_restore_invalidates_recap_commands_and_ephemeral_control(self):
        cid=self.make_pc()['id'];self.act('open',characters=[cid]);old=copy.deepcopy(self.game.room(self.gs['room'])['sessionRecap'])
        room=self.game.room(self.gs['room']);room['tableTools']=dict(control={'absent':{'name':'Игрок'}},pings=[{'id':'old','time':0}],focus={'id':'old'},proposals={'absent':{'id':'old'}});self.game.save(room)
        point=saves(self.game,self.gs,dict(operation='create',scope='campaign',label='Перед итогами'))
        self.answer(cid);self.act('finish',confirmed=True,awards={cid:dict(amount=3,note='')})
        room=self.game.room(self.gs['room'])
        saves(self.game,self.gs,dict(operation='restore',scope='campaign',id=point['id'],revision=room['revision'],confirmed=True))
        restored=self.game.room(self.gs['room']);self.assertNotEqual(restored['sessionRecap']['id'],old['id']);self.assertGreater(restored['sessionRecap']['version'],old['version'])
        self.assertEqual(restored['tableTools'],dict(control={},pings=[],focus=None,proposals={}));self.assertEqual(restored['changeHistory'],[]);self.assertEqual(restored['changeVersions'],{})
        with self.assertRaises(ValueError):
            self.game.action(self.ps,dict(action='sessionRecap',operation='answer',recap=old['id'],character=cid,version=0,answers={q:True for q in QUESTIONS},note=''))
        self.answer(cid);self.act('finish',confirmed=True,awards={cid:dict(amount=3,note='')})
        self.assertEqual(next(c for c in self.game.room(self.gs['room'])['characters'] if c['id']==cid)['sheet']['progression']['earned'],3)

    def test_finish_waits_for_live_character_roll_but_not_stale_roll(self):
        cid=self.make_pc()['id'];room=self.game.room(self.gs['room'])
        with patch('skill_checks.die',return_value=2):self.game.action(self.ps,dict(action='characterRoll',character=cid,skill='heal',revision=room['revision']))
        with self.assertRaisesRegex(ValueError,'завершите проверку'):self.act('open',characters=[cid])
        room=self.game.room(self.gs['room']);next(c for c in room['characters'] if c['id']==cid)['runtime']['wp']=1;self.game.save(room)
        self.act('open',characters=[cid])
        self.act('finish',confirmed=True,awards={cid:dict(amount=0,note='Без опыта; проверка уже устарела')})
