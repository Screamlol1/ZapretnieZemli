import copy
import unittest
from unittest.mock import patch
import test_server as support
import injuries


class WaterExposureTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown
    make_pc=support.CampaignTests.make_pc
    make_npc=support.CampaignTests.make_npc

    def hero(self):return next(c for c in self.game.view(self.gs)['characters'] if c['id']==self.cid)
    def act(self,op,s=None,**data):return self.game.action(s or self.ps,dict(action='waterExposure',op=op,character=self.cid,**data))
    def start(self,**data):
        self.cid=self.make_pc()['id'];self.act('configure',self.gs,phase='afloat',metalArmor=False,modifier=0,note='Переправа',**data)
        return self.hero()['runtime']['waterExposure']
    def roll(self,value=2):
        with patch('water_exposure.die',return_value=value):return self.act('roll',exposure=self.hero()['runtime']['waterExposure']['id'])['waterCheck']
    def step(self):
        e=self.hero()['runtime']['waterExposure'];return self.act('advance',self.gs,exposure=e['id'],nextAt=e['nextAt'])
    def tick(self,value=2):
        e=self.hero()['runtime']['waterExposure']
        with patch('water_exposure.die',return_value=value):return self.act('tick',self.gs,exposure=e['id'],nextAt=e['nextAt'])
    def time(self,n):return self.game.action(self.gs,dict(action='injury',op='advance',minutes=n,note='Прошло время у реки'))
    def configure(self,**data):
        e=self.hero()['runtime']['waterExposure'];return self.act('configure',self.gs,exposure=e['id'],metalArmor=e['metalArmor'],modifier=0,note='Уточнение',**data)
    def submerged(self):
        e=self.start();self.act('submerge',self.gs,exposure=e['id'],confirmed=True,note='Унесло под воду');return e

    def test_afloat_failure_submersion_then_breath_failure_applies_once(self):
        e=self.start();before=self.hero()['runtime']['current'].copy();p=self.roll()
        self.act('accept',roll=p['id']);c=self.hero();self.assertEqual(c['runtime']['current'],before)
        self.assertEqual(c['runtime']['waterExposure']['phase'],'submerged');self.assertEqual(c['runtime']['waterExposure']['nextAt'],0.1667)
        with self.assertRaises(ValueError):self.roll()
        self.step();p=self.roll();self.act('accept',roll=p['id'])
        self.assertEqual(self.hero()['runtime']['current']['str'],before['str']-1)
        self.assertEqual(self.hero()['runtime']['waterExposure']['phase'],'drowning')
        with self.assertRaises(ValueError):self.act('accept',roll=p['id'])
        self.assertFalse(self.hero()['runtime'].get('injuries'))

    def test_metal_armor_interval_and_default_round_precision(self):
        e=self.start();p=self.roll(6);self.act('accept',roll=p['id']);self.assertEqual(self.hero()['runtime']['waterExposure']['nextAt'],15)
        self.act('configure',self.gs,exposure=e['id'],metalArmor=True,modifier=0,note='Надета кольчуга')
        self.assertEqual(self.hero()['runtime']['waterExposure']['nextAt'],15,'Updating gear cannot postpone existing deadline')
        for _ in range(3):
            self.step();self.assertTrue(self.hero()['runtime']['waterExposure']['due'])
            p=self.roll(6);self.act('accept',roll=p['id'])
        self.assertEqual(self.hero()['runtime']['waterExposure']['nextAt'],15.5001)
        self.assertEqual(self.game.view(self.gs)['medicalClock'],15.3334)

    def test_drowning_broken_d6_and_explicit_gm_death(self):
        e=self.submerged();p=self.roll();self.act('accept',roll=p['id']);self.step();self.tick(3)
        c=self.hero();deadline=c['runtime']['waterExposure']['deathAt'];self.assertEqual(c['runtime']['current']['str'],0)
        self.assertEqual(deadline,3.1667);self.assertFalse(c['runtime'].get('dead'));self.assertFalse(c['runtime'].get('injuries'))
        with self.assertRaises(ValueError):self.tick(6)
        with self.assertRaises(ValueError):self.act('confirmDeath',self.gs,exposure=e['id'],confirmed=True,note='Рано')
        self.step();self.assertTrue(self.hero()['runtime']['waterExposure']['fatalDue'])
        with self.assertRaises(PermissionError):self.act('confirmDeath',exposure=e['id'],confirmed=True,note='Игрок')
        self.act('confirmDeath',self.gs,exposure=e['id'],confirmed=True,note='Спасение не успело')
        self.assertTrue(self.hero()['runtime']['dead']);self.assertNotIn('waterExposure',self.hero()['runtime'])

    def test_rescue_before_death_no_healing_and_tick_nonce(self):
        e=self.submerged();p=self.roll();self.act('accept',roll=p['id']);self.step()
        old=self.hero()['runtime']['waterExposure']['nextAt'];self.tick(2)
        with self.assertRaises(ValueError):self.act('tick',self.gs,exposure=e['id'],nextAt=old)
        before=self.hero()['runtime']['current'].copy()
        with self.assertRaises(PermissionError):self.act('rescue',exposure=e['id'],confirmed=True,note='Сам себя')
        self.act('rescue',self.gs,exposure=e['id'],confirmed=True,note='Вытащили верёвкой')
        self.assertEqual(self.hero()['runtime']['current'],before);self.assertNotIn('waterExposure',self.hero()['runtime']);self.assertFalse(self.hero()['runtime'].get('dead'))

    def test_push_wear_wp_penalties_and_broken_success_requires_gm(self):
        self.cid=self.make_pc()['id'];self.game.action(self.ps,dict(action='inventoryOpen',character=self.cid))
        item=self.game.action(self.gs,dict(action='itemCreate',location=dict(kind='character',id=self.cid),item=dict(name='Спасательный ремень',kind='gear',bonus=1,weight=1)))['items'][-1]
        self.act('configure',self.gs,phase='afloat',metalArmor=False,modifier=-2,item=item['id'],note='Течение')
        p=self.roll();self.assertEqual(len(p['roll']['penalty']),2)
        with patch('water_exposure.die',return_value=1):v=self.act('push',roll=p['id'])
        self.assertEqual(self.hero()['runtime']['current']['str'],0);self.assertEqual(self.hero()['runtime']['wp'],2)
        self.assertEqual(next(i for i in v['items'] if i['id']==item['id'])['wear'],1);self.assertFalse(self.hero()['runtime'].get('injuries'))
        # Model a successful pushed result that nevertheless broke Strength.
        room=self.game.room(self.gs['room']);room['waterCheck']['roll']['hits']=1;self.game.save(room)
        self.act('accept',roll=p['id']);e=self.hero()['runtime']['waterExposure'];self.assertEqual(e['phase'],'afloat');self.assertNotIn('deathAt',e)
        with patch('water_exposure.die',return_value=2):self.act('submerge',self.gs,exposure=e['id'],confirmed=True,note='Не удержался без помощи')
        self.assertEqual(self.hero()['runtime']['waterExposure']['phase'],'broken')
        with self.assertRaises(ValueError):self.act('submerge',self.gs,exposure=e['id'],confirmed=True,note='Не повторять D6')

    def test_owner_private_restart_and_pending_lock(self):
        e=self.start();other=self.game.login(dict(name='Другой',code=self.gm['code'],key=self.gm['playerKey']));os=self.game.session(other['token'])
        with self.assertRaises(PermissionError):self.act('roll',os,exposure=e['id'])
        p=self.roll()
        with self.assertRaises(ValueError):self.time(1)
        with self.assertRaises(ValueError):self.game.action(self.gs,dict(action='runtime',id=self.cid,current=self.hero()['runtime']['current'],wp=2))
        self.act('accept',roll=p['id']);self.act('rescue',self.gs,exposure=e['id'],confirmed=True,note='Достиг берега')
        self.cid=self.make_npc(hidden=True)['id'];self.act('configure',self.gs,phase='submerged',metalArmor=False,note='Тайная сцена')
        pv=self.game.view(self.ps);self.assertTrue(pv['waterWaiting']);self.assertFalse(pv['waterTargets']);self.assertNotIn('Тайная сцена',str(pv))
        with patch('water_exposure.die',return_value=2):p=self.act('roll',self.gs,exposure=self.hero()['runtime']['waterExposure']['id'])['waterCheck']
        self.assertEqual(self.game.view(self.ps)['waterCheck'],{'waiting':True});self.assertNotIn(p['diceEvent'],str(self.game.view(self.ps)))
        self.game.db.close();self.game=support.Game(self.path,reference_root=self.path.parent/'local-assets')
        restored=self.game.reconnect(dict(code=self.gm['code'],resume=self.gm['resume']));self.gs=self.game.session(restored['token'])
        self.assertEqual(self.game.view(self.gs)['waterCheck']['roll'],p['roll']);self.act('accept',self.gs,roll=p['id'])

    def test_long_advance_catches_due_ticks_and_never_heals_underwater(self):
        self.submerged();p=self.roll();self.act('accept',roll=p['id']);self.time(5)
        with self.assertRaises(ValueError):self.time(1)
        self.tick(2);e=self.hero()['runtime']['waterExposure']
        self.assertEqual(e['deathAt'],2.1667,'Catch-up anchors death deadline to actual scheduled tick')
        self.assertTrue(e['fatalDue']);self.assertFalse(self.hero()['runtime'].get('dead'))
        self.assertEqual(self.hero()['runtime']['current']['str'],0)

    def test_external_damage_starts_death_clock_once(self):
        self.submerged();p=self.roll();self.act('accept',roll=p['id'])
        c=self.hero();values=c['runtime']['current'].copy();values['str']=0
        with patch('water_exposure.die',return_value=4) as rng:
            self.game.action(self.gs,dict(action='runtime',id=self.cid,current=values,wp=0))
            self.game.action(self.gs,dict(action='chat',text='Помощь!'))
            self.assertEqual(rng.call_count,1)
        self.assertEqual(self.hero()['runtime']['waterExposure']['deathAt'],4)

    def test_clock_cross_conditions_and_earlier_cold_recovery(self):
        e=self.start();p=self.roll(6);self.act('accept',roll=p['id'])
        self.game.action(self.gs,dict(action='coldExposure',op='configure',character=self.cid,intervalHours=1,note='Холодная вода'))
        with self.assertRaises(ValueError):self.step()
        with patch('cold_exposure.die',return_value=6):v=self.game.action(self.ps,dict(action='coldExposure',op='roll',character=self.cid,exposure=self.hero()['runtime']['coldExposure']['id']))
        with self.assertRaises(ValueError):self.act('submerge',self.gs,exposure=e['id'],confirmed=True,note='Нельзя во время другой проверки')
        self.game.action(self.ps,dict(action='coldExposure',op='accept',character=self.cid,roll=v['coldCheck']['id']))
        self.step();self.assertEqual(self.game.view(self.gs)['medicalClock'],15)
        room=dict(characters=[],medicalClock=0,log=[])
        c=dict(id='r',name='r',kind='pc',sheet=dict(attrs=dict(str=3,agi=3,wit=3,emp=3)),runtime=dict(current=dict(str=0,agi=3,wit=3,emp=3),conditions={},brokenRecovery={'str':dict(due=60)},coldExposure=dict(id='cold',nextAt=120)))
        room['characters']=[c];injuries.advance(room,120)
        self.assertEqual(c['runtime']['current']['str'],1,'Recovery due before cold check must happen first')


if __name__=='__main__':unittest.main()
