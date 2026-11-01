import copy
import unittest
from unittest.mock import patch
import test_server as support
from dice_events import publish


class PrideTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown
    make_pc=support.CampaignTests.make_pc

    def setup_hero(self):
        c=self.make_pc();self.cid=c['id']
        sheet=copy.deepcopy(c['sheet']);sheet['pride']='Я всегда нахожу дорогу домой'
        self.game.action(self.ps,dict(action='character',id=self.cid,sheet=sheet))

    def hero(self,gm=False):return next(c for c in self.game.view(self.gs if gm else self.ps)['characters'] if c['id']==self.cid)
    def roll(self,gm=False,modifier=0):
        s=self.gs if gm else self.ps
        with patch('skill_checks.die',return_value=2):
            self.game.action(s,dict(action='characterRoll',character=self.cid,skill='survive',modifier=modifier,revision=self.game.view(s)['revision'],visibility='hidden' if gm else 'public'))
        return self.game.view(self.gs)['gmChecks'][self.cid] if gm else self.hero()['runtime']['lastCheck']

    def power(self,op,s=None,**data):return self.game.action(s or self.ps,dict(action='characterPride',character=self.cid,op=op,**data))
    def request(self,gm=False):
        r=self.roll(gm)
        self.power('request',self.gs if gm else self.ps,roll=r['id'],note='Следы ведут к знакомым местам')
        return r,self.hero(True)['runtime']['prideRequest']

    def approve(self,r,p):self.power('approve',self.gs,roll=r['id'],request=p['id'])

    def test_owner_request_gm_review_d12_once_and_persistence(self):
        self.setup_hero();r,p=self.request()
        with self.assertRaises(PermissionError):self.power('approve',roll=r['id'],request=p['id'])
        with self.assertRaises(ValueError):self.power('roll',roll=r['id'],request=p['id'])
        self.approve(r,p)
        with patch('pride.secrets.randbelow',return_value=11):v=self.power('roll',roll=r['id'],request=p['id'])
        c=self.hero();self.assertEqual(c['runtime']['lastCheck']['hits'],4);self.assertTrue(c['runtime']['lastCheck']['accepted'])
        self.assertEqual(c['runtime']['pride']['usedSession'],v['journey']['session'])
        self.assertEqual(v['diceRolls'][-1]['groups'][-1]['label'],'Гордость');self.assertEqual(v['diceRolls'][-1]['groups'][-1]['sides'],12)
        with self.assertRaises(ValueError):self.power('roll',roll=r['id'],request=p['id'])
        self.game.db.close();self.game=support.Game(self.path,reference_root=self.path.parent/'local-assets')
        self.assertEqual(self.hero()['runtime']['lastCheck']['pride']['value'],12)
        r2=self.roll()
        with self.assertRaises(ValueError):self.power('request',roll=r2['id'],note='Ещё раз')

    def test_failed_pride_requires_full_following_session_and_cannot_edit_around_it(self):
        self.setup_hero();r,p=self.request();self.approve(r,p)
        with patch('pride.secrets.randbelow',return_value=0):self.power('roll',roll=r['id'],request=p['id'])
        c=self.hero();lost=c['runtime']['pride']['lostSession'];self.assertTrue(c['runtime']['pride']['lost']);self.assertEqual(c['sheet']['pride'],'')
        sheet=copy.deepcopy(c['sheet']);sheet['pride']='Обход через редактор'
        with self.assertRaises(ValueError):self.game.action(self.ps,dict(action='character',id=self.cid,sheet=sheet))
        for session in (lost,lost+1):
            room=self.game.room(self.gs['room']);room['journey']['session']=session;self.game.save(room)
            with self.assertRaises(ValueError):self.power('replace',lostSession=lost,text='Новая гордость')
        room=self.game.room(self.gs['room']);room['journey']['session']=lost+2;self.game.save(room)
        self.power('replace',lostSession=lost,text='Новая гордость');self.assertFalse(self.hero()['runtime']['pride']['lost'])
        self.assertEqual(self.hero()['sheet']['pride'],'Новая гордость')

    def test_request_blocks_rerolls_and_session_finish_but_can_cancel(self):
        self.setup_hero();r,p=self.request()
        with self.assertRaises(ValueError):self.roll()
        with self.assertRaises(ValueError):self.game.action(self.ps,dict(action='characterPush',character=self.cid,roll=r['id']))
        with self.assertRaises(ValueError):self.game.action(self.gs,dict(action='sessionRecap',operation='open',characters=[self.cid]))
        self.power('cancel',request=p['id']);self.assertNotIn('prideRequest',self.hero()['runtime'])
        self.roll()

    def test_pride_after_push_can_rescue_failed_roll_even_when_broken(self):
        self.setup_hero();r=self.roll()
        with patch('skill_checks.die',return_value=1):self.game.action(self.ps,dict(action='characterPush',character=self.cid,roll=r['id']))
        self.assertEqual(self.hero()['runtime']['current']['wit'],0)
        self.power('request',roll=r['id'],note='Последний шанс вернуться')
        p=self.hero()['runtime']['prideRequest'];self.approve(r,p)
        with patch('pride.secrets.randbelow',return_value=5):self.power('roll',roll=r['id'],request=p['id'])
        self.assertEqual(self.hero()['runtime']['lastCheck']['hits'],1)
        self.assertEqual(self.hero()['runtime']['current']['wit'],0,'Pride must not heal push damage')

    def test_stale_approval_and_foreign_owner_cannot_roll(self):
        self.setup_hero();r,p=self.request();self.approve(r,p)
        other=self.game.login(dict(name='Другой',code=self.gm['code'],key=self.gm['playerKey']));os=self.game.session(other['token'])
        with self.assertRaises(PermissionError):self.power('roll',os,roll=r['id'],request=p['id'])
        c=self.hero();self.game.action(self.gs,dict(action='runtime',id=self.cid,current=c['runtime']['current'],wp=1))
        self.assertFalse(self.hero()['runtime']['prideRequest']['current'])
        with self.assertRaises(ValueError):self.power('roll',roll=r['id'],request=p['id'])
        self.assertNotIn('pride',self.hero()['runtime']);self.power('cancel',request=p['id'])

    def test_private_request_and_die_stay_private(self):
        self.setup_hero();r,p=self.request(True);self.approve(r,p)
        self.assertNotIn('prideRequest',self.hero()['runtime'])
        with self.assertRaises(ValueError):self.power('roll',roll=r['id'],request=p['id'])
        with patch('pride.secrets.randbelow',return_value=7):v=self.power('roll',self.gs,roll=r['id'],request=p['id'])
        self.assertTrue(v['diceRolls'][-1]['private']);self.assertFalse(self.game.view(self.ps)['diceRolls'])

    def test_separate_penalties_can_cancel_pride_successes(self):
        self.setup_hero();r=self.roll(modifier=-5)
        room=self.game.room(self.gs['room']);check=next(c for c in room['characters'] if c['id']==self.cid)['runtime']['lastCheck'];check['penalty']=[6]*5;self.game.save(room)
        self.power('request',roll=r['id'],note='Ещё одна попытка');p=self.hero()['runtime']['prideRequest'];self.approve(r,p)
        with patch('pride.secrets.randbelow',return_value=11):self.power('roll',roll=r['id'],request=p['id'])
        self.assertEqual(self.hero()['runtime']['lastCheck']['hits'],0);self.assertTrue(self.hero()['runtime']['pride']['lost'])

    def test_pending_event_survives_other_players_history(self):
        self.setup_hero();r=self.roll();room=self.game.room(self.gs['room'])
        for _ in range(205):publish(room,'Другой','Бросок',[],'Готово')
        self.assertEqual(len(room['diceRolls']),200);self.assertIn(r['diceEvent'],[e['id'] for e in room['diceRolls']])
        room['characters'][0]['runtime']['lastCheck']['accepted']=True
        for _ in range(205):publish(room,'Другой','Бросок',[],'Готово')
        self.assertNotIn(r['diceEvent'],[e['id'] for e in room['diceRolls']])


if __name__=='__main__':unittest.main()
