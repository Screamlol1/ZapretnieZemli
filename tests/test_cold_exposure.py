import copy
import unittest
from unittest.mock import patch
import test_server as support
import injuries
import save_points


class ColdExposureTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown
    make_pc=support.CampaignTests.make_pc
    make_npc=support.CampaignTests.make_npc

    def hero(self):return next(c for c in self.game.view(self.gs)['characters'] if c['id']==self.cid)
    def act(self,op,s=None,**data):return self.game.action(s or self.ps,dict(action='coldExposure',op=op,character=self.cid,**data))
    def start(self,**data):
        self.cid=self.make_pc()['id']
        self.act('configure',self.gs,intervalHours=1,modifier=0,note='Мороз на перевале',**data)
        return self.hero()['runtime']['coldExposure']
    def roll(self,value=2):
        with patch('cold_exposure.die',return_value=value):
            return self.act('roll',exposure=self.hero()['runtime']['coldExposure']['id'])['coldCheck']
    def time(self,n):return self.game.action(self.gs,dict(action='injury',op='advance',minutes=n,note='Прошло время у перевала'))
    def travel(self,action,s=None,**data):
        t=self.game.view(self.gs)['journey']
        return self.game.action(s or self.gs,dict(action=action,revision=t['revision'],**data))

    def test_owner_roll_failure_no_critical_and_warm_does_not_heal(self):
        e=self.start();before=self.hero()['runtime']['current'].copy()
        with self.assertRaises(PermissionError):self.act('configure',intervalHours=1,note='Обход')
        p=self.roll()
        with self.assertRaises(ValueError):self.time(1)
        self.act('accept',roll=p['id']);c=self.hero()
        self.assertTrue(c['runtime']['conditions']['cold'])
        for attr in ('str','wit'):self.assertEqual(c['runtime']['current'][attr],max(0,before[attr]-1))
        self.assertFalse(c['runtime'].get('injuries'))
        with self.assertRaises(PermissionError):self.act('warm',exposure=e['id'],confirmed=True,note='Костёр')
        self.act('warm',self.gs,exposure=e['id'],confirmed=True,note='Согрелся у костра')
        self.assertFalse(self.hero()['runtime']['conditions']['cold']);self.assertNotIn('coldExposure',self.hero()['runtime'])
        self.assertEqual(c['runtime']['current'],self.hero()['runtime']['current'])

    def test_due_clock_catches_up_hourly_without_skipping_and_blocks_next_advance(self):
        e=self.start()
        with self.assertRaises(ValueError):self.time(60)
        p=self.roll(6);self.act('accept',roll=p['id'])
        self.time(360)
        with self.assertRaises(ValueError):self.time(1)
        for expected in (120,180,240,300,360,420):
            p=self.roll(6);self.act('accept',roll=p['id'])
            self.assertEqual(self.hero()['runtime']['coldExposure']['nextAt'],expected)
        self.assertFalse(self.hero()['runtime']['coldExposure']['due'])
        self.time(1)
        with self.assertRaises(ValueError):self.roll()

    def test_push_damage_gear_wp_and_forest_rescue(self):
        self.cid=self.make_pc()['id'];self.game.action(self.ps,dict(action='inventoryOpen',character=self.cid))
        item=self.game.action(self.gs,dict(action='itemCreate',location=dict(kind='character',id=self.cid),item=dict(name='Тёплый плащ',kind='gear',bonus=1,weight=1)))['items'][-1]
        room=self.game.room(self.gs['room']);c=next(c for c in room['characters'] if c['id']==self.cid)
        c['sheet']['paths']={'forest':2};self.game.save(room)
        self.act('configure',self.gs,intervalHours=1,modifier=0,note='Мороз',item=item['id'])
        p=self.roll();old=self.hero()['runtime']['current']['str']
        with patch('cold_exposure.die',return_value=1):v=self.act('push',roll=p['id'])
        self.assertEqual(self.hero()['runtime']['current']['str'],0)
        self.assertEqual(self.hero()['runtime']['wp'],old)
        self.assertEqual(next(i for i in v['items'] if i['id']==item['id'])['wear'],1)
        self.assertTrue(v['coldCheck']['canForest']);self.assertFalse(self.hero()['runtime'].get('injuries'))
        self.act('forest',roll=p['id'])
        self.assertNotIn('coldCheck',self.game.view(self.gs));self.assertEqual(self.hero()['runtime']['wp'],old-1)
        self.assertEqual(self.hero()['runtime']['current']['str'],0,'Forest success does not heal pushing damage')
        self.assertFalse(self.hero()['runtime'].get('conditions',{}).get('cold'))
        with self.assertRaises(ValueError):self.act('forest',roll=p['id'])

    def test_fatal_due_requires_gm_confirmation_not_another_roll(self):
        e=self.start();room=self.game.room(self.gs['room']);c=next(c for c in room['characters'] if c['id']==self.cid)
        c['runtime']['current']['str']=1;self.game.save(room)
        p=self.roll();self.act('accept',roll=p['id']);self.assertEqual(self.hero()['runtime']['current']['str'],0)
        self.assertFalse(self.hero()['runtime']['coldExposure']['fatalDue'])
        with self.assertRaises(ValueError):self.act('confirmDeath',self.gs,exposure=e['id'],confirmed=True,note='Слишком рано')
        self.time(60);self.assertTrue(self.hero()['runtime']['coldExposure']['fatalDue']);self.assertFalse(self.hero()['runtime'].get('dead'))
        with self.assertRaises(ValueError):self.roll()
        with self.assertRaises(PermissionError):self.act('confirmDeath',exposure=e['id'],confirmed=True,note='Игрок')
        self.act('confirmDeath',self.gs,exposure=e['id'],confirmed=True,note='До укрытия не добрались')
        self.assertTrue(self.hero()['runtime']['dead']);self.assertFalse(self.hero()['runtime'].get('injuries'))

    def test_hidden_npc_check_is_private_and_restart_keeps_pending(self):
        self.cid=self.make_npc(hidden=True)['id'];e=self.act('configure',self.gs,intervalHours=2,note='Тайный пленник')['characters'][-1]['runtime']['coldExposure']
        player=self.game.view(self.ps)
        self.assertTrue(player['coldWaiting']);self.assertFalse(player['coldTargets'])
        self.assertNotIn(self.cid,str(player));self.assertNotIn('Тайный пленник',str(player))
        with patch('cold_exposure.die',return_value=2):p=self.act('roll',self.gs,exposure=e['id'])['coldCheck']
        player=self.game.view(self.ps);self.assertEqual(player['coldCheck'],{'waiting':True});self.assertFalse(player['coldTargets']);self.assertFalse(player['diceRolls'])
        self.assertNotIn('signature',self.game.view(self.gs)['coldCheck'])
        self.game.db.close();self.game=support.Game(self.path,reference_root=self.path.parent/'local-assets')
        restored=self.game.reconnect(dict(code=self.gm['code'],resume=self.gm['resume']));self.gs=self.game.session(restored['token'])
        self.assertEqual(self.game.view(self.gs)['coldCheck']['roll'],p['roll'])
        self.act('accept',self.gs,roll=p['id'])
        self.assertTrue(self.hero()['runtime']['conditions']['cold'])

    def test_update_gear_does_not_postpone_due_and_foreign_owner_cannot_roll(self):
        e=self.start()
        self.act('configure',self.gs,exposure=e['id'],intervalHours=4,modifier=-2,item='',note='Укрытие изменилось')
        self.assertEqual(self.hero()['runtime']['coldExposure']['nextAt'],0);self.assertEqual(self.hero()['runtime']['coldExposure']['id'],e['id'])
        other=self.game.login(dict(name='Другой',code=self.gm['code'],key=self.gm['playerKey']));os=self.game.session(other['token'])
        with self.assertRaises(PermissionError):self.act('roll',os,exposure=e['id'])
        p=self.roll()
        self.assertEqual(len(p['roll']['penalty']),2)
        with self.assertRaises(ValueError):self.act('configure',self.gs,exposure=e['id'],intervalHours=4,note='Поздно')
        with self.assertRaises(ValueError):self.game.action(self.gs,dict(action='runtime',id=self.cid,current=self.hero()['runtime']['current'],wp=0))

    def test_conditions_block_natural_and_healer_recovery_until_removed(self):
        for flag,attr in [('cold','str'),('cold','wit'),('hungry','str'),('thirsty','agi'),('sleepy','wit')]:
            with self.subTest(flag=flag,attr=attr):
                room=dict(characters=[],medicalClock=0,log=[])
                c=dict(id='c',name='c',kind='pc',sheet=dict(attrs=dict(str=3,agi=3,wit=3,emp=3)),runtime=dict(current=dict(str=3,agi=3,wit=3,emp=3),conditions={flag:True},brokenRecovery={attr:dict(due=60)}))
                c['runtime']['current'][attr]=0;room['characters']=[c]
                injuries.advance(room,120);self.assertEqual(c['runtime']['current'][attr],0)
                c['runtime']['conditions'][flag]=False;injuries.advance(room,0);self.assertEqual(c['runtime']['current'][attr],1)

    def test_actual_quarter_finishes_once_then_hourly_checks_catch_up(self):
        self.start();p=self.roll(6);self.act('accept',roll=p['id'])
        self.travel('travelSetup',party=[self.cid],x=0,y=0,season='winter')
        self.travel('travelPlan',self.ps,id=self.cid,job='rest',role='none')
        self.travel('travelReady',ready=True,path=[])
        for event in self.game.view(self.gs)['journey']['pending']:
            self.travel('travelResolve',id=event['id'],note='Мастер разрешил событие',reveal=False)
        self.travel('travelComplete',self.ps,complete=True)
        v=self.travel('travelComplete',complete=True)
        self.assertEqual(v['medicalClock'],360);self.assertEqual(v['journey']['quarter'],1)
        for _ in range(6):p=self.roll(6);self.act('accept',roll=p['id'])
        v=self.game.view(self.gs);self.assertEqual(v['medicalClock'],360);self.assertEqual(v['journey']['quarter'],1)
        self.assertEqual(self.hero()['runtime']['coldExposure']['nextAt'],420)

    def test_checkpoint_preserves_pending_roll_and_session_cannot_finish_midcheck(self):
        self.start();p=self.roll()
        with self.assertRaises(ValueError):self.game.action(self.gs,dict(action='sessionRecap',operation='open',characters=[self.cid]))
        saved=save_points.apply(self.game,self.gs,dict(scope='campaign',operation='create',label='Во время проверки холода'))
        self.act('accept',roll=p['id'])
        v=save_points.apply(self.game,self.gs,dict(scope='campaign',operation='restore',id=saved['id'],confirmed=True,revision=self.game.view(self.gs)['revision']))['state']
        self.assertEqual(v['coldCheck']['roll'],p['roll'])
        self.act('accept',roll=p['id'])
        self.assertEqual(self.hero()['runtime']['coldExposure']['nextAt'],60)


if __name__=='__main__':unittest.main()
