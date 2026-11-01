import copy
import unittest
from unittest.mock import patch
import test_server as support
import afflictions
import injuries

class AfflictionTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown
    make_pc=support.CampaignTests.make_pc
    make_npc=support.CampaignTests.make_npc
    def hero(self):return next(c for c in self.game.view(self.gs)['characters'] if c['id']==self.cid)
    def act(self,op,s=None,**data):return self.game.action(s or self.ps,dict(action='affliction',op=op,character=self.cid,**data))
    def start(self,kind='poison',typ='lethal',hidden=False):
        self.cid=(self.make_npc(hidden=True) if hidden else self.make_pc())['id']
        self.act('configure',self.gs,kind=kind,type=typ,potency=1,note='Проверка заражённой пищи')
        return self.effect()
    def effect(self):return self.hero()['runtime']['afflictions'][-1]
    def roll(self,win=True,s=None,**data):
        c=self.hero();actor=next((x for x in self.game.view(self.gs)['characters'] if x['id']==data.get('caregiver')),c)
        n=actor['runtime']['current']['emp' if data.get('caregiver') else 'str']+actor['sheet']['skills'].get('heal' if data.get('caregiver') else 'endure',0)
        with patch('afflictions.die',side_effect=([6 if win else 2]*n)+[2 if win else 6]):v=self.act('roll',s,affliction=self.effect()['id'],**data)
        return v['afflictionCheck']
    def time(self,n):return self.game.action(self.gs,dict(action='injury',op='advance',minutes=n,note='Прошло игровое время'))
    def test_poison_tie_limited_effect_owner_and_idempotent_accept(self):
        a=self.start();before=self.hero()['runtime']['current']['str']
        with patch('afflictions.die',return_value=2):p=self.act('roll',affliction=a['id'])['afflictionCheck']
        self.assertEqual(p['enemyHits'],0);self.assertFalse(p['roll']['pushAvailable'])
        with self.assertRaises(ValueError):self.act('push',roll=p['id'])
        v=self.act('accept',roll=p['id']);self.assertEqual(self.hero()['runtime']['current']['str'],before-1)
        self.assertEqual(self.effect()['phase'],'resolved');self.assertNotIn('afflictionCheck',v)
        with self.assertRaises(ValueError):self.act('accept',roll=p['id'])
    def test_full_lethal_ticks_each_round_antidote_keeps_damage(self):
        a=self.start();room=self.game.room(self.gs['room']);c=next(c for c in room['characters'] if c['id']==self.cid);c['runtime']['current']['str']=4;c['sheet']['attrs']['str']=4;self.game.save(room);before=4;p=self.roll(False);self.act('accept',roll=p['id'])
        self.assertEqual(self.hero()['runtime']['current']['str'],before-1)
        deadline=self.effect()['nextAt'];self.act('advance',self.gs,affliction=a['id'],nextAt=deadline)
        self.act('tick',self.gs,affliction=a['id'],nextAt=deadline)
        self.assertEqual(self.hero()['runtime']['current']['str'],before-2)
        with self.assertRaises(ValueError):self.act('tick',self.gs,affliction=a['id'],nextAt=deadline)
        self.act('antidote',self.gs,affliction=a['id'],confirmed=True,note='Противоядие из аптечки')
        self.assertEqual(self.effect()['phase'],'resolved');self.assertEqual(self.hero()['runtime']['current']['str'],before-2)
    def test_sleep_breaks_wits_without_critical_and_wakes_after_saved_duration(self):
        a=self.start(typ='sleep');room=self.game.room(self.gs['room']);c=next(c for c in room['characters'] if c['id']==self.cid);c['runtime']['current']['wit']=1;self.game.save(room)
        p=self.roll(False)
        with patch('afflictions.die',return_value=2):self.act('accept',roll=p['id'])
        self.assertEqual(self.effect()['phase'],'sleeping');self.assertTrue(injuries.blocked(self.hero()));self.assertFalse(self.hero()['runtime'].get('injuries'))
        self.time(120);self.act('tick',self.gs,affliction=a['id'],nextAt=120)
        self.assertFalse(injuries.blocked(self.hero()));self.assertEqual(self.hero()['runtime']['current']['wit'],0)
    def test_disease_incubation_daily_damage_caregiver_and_recovery_block(self):
        a=self.start('disease');before=self.hero()['runtime']['current'].copy();p=self.roll(False);self.act('accept',roll=p['id'])
        self.assertEqual(self.hero()['runtime']['current'],before);self.assertTrue(injuries.recovery_blocked(self.hero(),'str'));self.assertTrue(injuries.recovery_blocked(self.hero(),'agi'))
        self.time(1440)
        with self.assertRaises(ValueError):self.time(1)
        self.act('tick',self.gs,affliction=a['id'],nextAt=1440)
        for attr in ('str','agi'):self.assertEqual(self.hero()['runtime']['current'][attr],before[attr]-1)
        self.time(1440);helper=self.make_npc();p=self.roll(True,self.gs,caregiver=helper['id'],careConfirmed=True)
        self.act('accept',self.gs,roll=p['id']);self.assertEqual(self.effect()['phase'],'resolved');self.assertFalse(injuries.recovery_blocked(self.hero(),'str'))
    def test_disease_fatal_clock_manual_and_no_critical(self):
        a=self.start('disease');p=self.roll(False);self.act('accept',roll=p['id']);room=self.game.room(self.gs['room']);c=next(c for c in room['characters'] if c['id']==self.cid);c['runtime']['current']['str']=1;self.game.save(room)
        self.time(1440);self.act('tick',self.gs,affliction=a['id'],nextAt=1440)
        self.assertEqual(self.hero()['runtime']['current']['str'],0);self.assertFalse(self.hero()['runtime'].get('injuries'))
        self.assertEqual(self.effect()['deathAt'],2880);self.time(1440)
        with self.assertRaises(ValueError):self.time(1)
        with self.assertRaises(PermissionError):self.act('confirmDeath',affliction=a['id'],confirmed=True,note='Нет помощи')
        self.act('confirmDeath',self.gs,affliction=a['id'],confirmed=True,note='Помощь не успела');self.assertTrue(self.hero()['runtime']['dead'])
    def test_hidden_patient_and_restart_preserve_pending(self):
        a=self.start(hidden=True);p=self.roll(False,self.gs);v=self.game.view(self.ps)
        self.assertEqual(v['afflictionCheck'],dict(waiting=True));self.assertFalse(v['afflictionTargets']);self.assertNotIn(self.cid,str(v));self.assertNotIn('signature',self.game.view(self.gs)['afflictionCheck'])
        self.game.db.close();self.game=support.Game(self.path,reference_root=self.path.parent/'local-assets')
        self.assertEqual(self.game.view(self.gs)['afflictionCheck']['id'],p['id']);self.act('accept',self.gs,roll=p['id'])
    def test_other_player_cannot_resolve_and_gm_required_to_assign(self):
        a=self.start();p=self.roll(False);outsider=self.game.login(dict(code=self.gm['code'],name='Чужой',key=self.gm['playerKey']));session=self.game.session(outsider['token'])
        with self.assertRaises(PermissionError):self.act('accept',session,roll=p['id'])
        with self.assertRaises(PermissionError):self.act('configure',kind='poison',potency=1,note='Не Мастер')

if __name__=='__main__':unittest.main()
