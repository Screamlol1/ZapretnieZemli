"""Casting regressions exercise the actual persistent server action boundary."""
import copy
import unittest
from unittest.mock import patch
import test_server as support
import magic_rules as magic

class MagicTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown
    make_pc=support.CampaignTests.make_pc
    make_npc=support.CampaignTests.make_npc

    def wizard(self,school='healing',rank=2,kin='human'):
        c=self.make_pc();room=self.game.room(self.gs['room']);c=next(x for x in room['characters'] if x['id']==c['id'])
        c['sheet'].update(path=school,pathRank=rank,paths={school:rank},kin=kin)
        c['runtime']['wp']=10;self.game.save(room);return c
    def act(self,op,s=None,**data):return self.game.action(s or self.ps,dict(action='magic',op=op,**data))
    def declare(self,c,spell='healing_hands',target=None,**data):
        v=self.act('declare',character=c['id'],spell=spell,target=target or '',wp=1,safe=True,note='Цель видна и находится на расстоянии руки.',**data)
        return v['magicCastings'][-1]['id']
    def approve(self,r):self.act('approve',self.gs,casting=r,confirmed=True)
    def room(self):return self.game.room(self.gs['room'])

    def test_catalog_has_all_core_schools_and_sources(self):
        self.assertEqual(len(magic.SPELLS),68)
        self.assertEqual({k:sum(s['school']==k for s in magic.SPELLS.values()) for k in magic.CATALOG['schools']},dict(general=6,healing=9,shapes=8,sight=9,signs=9,stone=9,blood=8,death=10))
        self.assertTrue(all(121<=s['page']<=142 and s['ingredient'] and s['summary'] for s in magic.SPELLS.values()))

    def test_safe_cast_heals_and_spends_once_persists_no_push(self):
        c=self.wizard();target=self.make_npc();room=self.room();victim=next(x for x in room['characters'] if x['id']==target['id']);victim['runtime']['current']['str']=1;self.game.save(room)
        r=self.declare(c,target=target['id']);self.approve(r)
        with patch('magic_rules.die',side_effect=AssertionError('safe cast must have no dice')):v=self.act('cast',casting=r)
        spell=v['magicCastings'][-1];self.assertEqual((spell['power'],spell['status'],spell['dice']),(1,'resolved',[]))
        self.assertEqual(next(x for x in self.room()['characters'] if x['id']==target['id'])['runtime']['current']['str'],2)
        self.assertEqual(self.room()['characters'][0]['runtime']['wp'],9)
        self.assertNotIn('risk',v['diceRolls'][-1]);self.assertNotIn('signature',spell)
        revision=v['revision']
        with self.assertRaises(ValueError):self.act('cast',casting=r)
        self.assertEqual(self.game.view(self.gs)['revision'],revision)

    def test_ownership_and_stale_target(self):
        c=self.wizard();target=self.make_npc();r=self.declare(c,target=target['id'])
        with self.assertRaises(PermissionError):self.act('approve',casting=r,confirmed=True)
        self.approve(r);room=self.room();room['characters'][1]['runtime']['current']['str']-=1;self.game.save(room)
        with self.assertRaisesRegex(ValueError,'изменились'):self.act('cast',casting=r)
        self.assertFalse(self.game.view(self.ps)['magicCastings'][-1]['current'])
        self.assertEqual(self.room()['characters'][0]['runtime']['wp'],10)
        with self.assertRaises(ValueError):self.declare(c,target=c['id'])

    def test_overcharge_halfelf_and_ingredient(self):
        c=self.wizard('blood',1,'halfelf');room=self.room();room.setdefault('items',[]).append(dict(id='blood-drop',name='Кровь',quantity=1,version=1,location=dict(kind='character',id=c['id']),weight=0,kind='gear',bonus=0,armor=0));self.game.save(room)
        r=self.declare(c,'firewalker',ingredientItem='blood-drop');self.approve(r)
        with patch('magic_rules.die',side_effect=[6,4]):v=self.act('cast',casting=r)
        cast=v['magicCastings'][-1];self.assertEqual((cast['power'],cast['formula']['cost'],cast['dice']),(4,1,[6,4]))
        self.assertFalse(any(i['id']=='blood-drop' for i in self.room()['items']))
        self.assertEqual(self.room()['characters'][0]['runtime']['magicEffects'][-1]['kind'],'fireproof')
        room=self.room();room['journey']['quarter']+=1;magic.reconcile(room);self.assertEqual(room['characters'][0]['runtime']['magicEffects'],[])

    def test_chance_cast_always_mishap_and_no_replay(self):
        c=self.wizard('blood',1);target=self.make_npc();r=self.declare(c,'immolate',target=target['id']);self.approve(r)
        with patch('magic_rules.die',side_effect=[6,2,4]):v=self.act('cast',casting=r)
        cast=v['magicCastings'][-1];self.assertEqual(cast['mishap']['value'],24);self.assertEqual(cast['status'],'rolled')
        with self.assertRaises(ValueError):self.act('cancel',casting=r)
        with self.assertRaises(ValueError):self.game.action(self.gs,dict(action='runtime',id=c['id'],wp=10))
        before=copy.deepcopy(self.room())
        with self.assertRaises(PermissionError):self.act('resolve',casting=r,mode='apply',note='Обычный эффект и потеря ловкости.')
        self.assertEqual(self.room()['revision'],before['revision'])
        self.act('resolve',self.gs,casting=r,mode='apply',note='Обычный эффект; осечка истощила заклинателя.')
        room=self.room();self.assertEqual(room['characters'][0]['runtime']['current']['agi'],c['sheet']['attrs']['agi']-1)
        self.assertEqual(room['characters'][1]['runtime']['current']['str'],target['runtime']['current']['str']-2)
        with self.assertRaises(ValueError):self.act('resolve',self.gs,casting=r,mode='apply',note='Повтор')

    def test_npc_uses_gm_pool_and_hidden_cast_stays_secret(self):
        c=self.make_npc(hidden=True);room=self.room();room['characters'][0]['sheet'].update(npcTalentsConfigured=True,path='blood',pathRank=2,paths={'blood':2});self.game.save(room)
        self.act('pool',self.gs,value=4)
        v=self.act('declare',self.gs,character=c['id'],spell='firewalker',wp=1,safe=True,note='Тайное колдовство.',visibility='hidden');r=v['magicCastings'][-1]['id'];self.approve(r)
        self.act('cast',self.gs,casting=r)
        v=self.game.view(self.ps);self.assertEqual(v['magicCastings'],[]);self.assertNotIn('magicWillpower',v);self.assertFalse(v['diceRolls'])
        self.assertEqual(self.room()['magicWillpower'],3)

    def test_ritual_requires_game_time_and_gm_confirmation(self):
        c=self.wizard('sight',3);r=self.declare(c,'divination');self.approve(r);self.act('cast',casting=r)
        self.assertEqual(self.room()['characters'][0]['runtime']['wp'],10)
        with self.assertRaises(ValueError):self.act('finish_ritual',self.gs,casting=r,confirmed=True)
        room=self.room();room['medicalClock']=360;self.game.save(room)
        with patch('magic_rules.die',return_value=4):v=self.act('finish_ritual',self.gs,casting=r,confirmed=True)
        self.assertEqual(v['magicCastings'][-1]['status'],'rolled');self.assertEqual(self.room()['characters'][0]['runtime']['wp'],9)
        self.act('resolve',self.gs,casting=r,mode='manual',note='В видении — мост и человек в красном плаще.')
        self.assertIn('красном',self.room()['magicCastings'][-1]['verdict'])

    def test_invalid_numbers_and_foreign_ingredients_are_rejected(self):
        c=self.wizard('blood',2)
        for wp in (True,0,11,'1'):
            with self.assertRaises(ValueError):self.act('declare',character=c['id'],spell='firewalker',wp=wp,note='Цель — я.')
        with self.assertRaises(ValueError):self.declare(c,'firewalker',ingredientItem='missing')
        self.assertFalse(self.room().get('magicCastings'))

    def test_bound_spell_cost_and_dice_not_power(self):
        c=self.wizard('blood',3);r=self.declare(c,'firewalker',bind=2,obscure=True);self.approve(r);self.act('cast',casting=r)
        room=self.room();room['medicalClock']=360;self.game.save(room)
        with patch('magic_rules.die',return_value=4):v=self.act('finish_ritual',self.gs,casting=r,confirmed=True)
        cast=v['magicCastings'][-1];self.assertEqual((cast['formula']['cost'],cast['formula']['dice'],cast['power']),(4,1,1))
        self.assertEqual(cast['status'],'rolled');self.assertFalse(self.room()['characters'][0]['runtime'].get('magicEffects'))

    def battle(self,c,target):
        self.game.action(self.gs,dict(action='combatCreate',units=[dict(id=c['id'],team='A'),dict(id=target['id'],team='B')]))
        room=self.room();b=room['combat'];b.update(phase='combat',round=1,turn=0,order=[c['id'],target['id']])
        for n,u in enumerate(b['units']):u.update(q=3+n,r=3,fast=1,slow=1)
        self.game.save(room)

    def test_combat_grimoire_spends_both_actions_and_syncs_wp(self):
        c=self.wizard('blood',2);target=self.make_npc();self.battle(c,target)
        room=self.room();room['items'].append(dict(id='grimoire',name='Книга огня',quantity=1,version=1,location=dict(kind='character',id=c['id']),weight=1,kind='gear'));self.game.save(room)
        r=self.declare(c,'firewalker',grimoire='grimoire');self.approve(r)
        with patch('magic_rules.die',side_effect=AssertionError('safe spell from book rolls no dice')):v=self.act('cast',casting=r)
        u=next(u for u in v['combat']['units'] if u['id']==c['id'])
        self.assertEqual((u['fast'],u['slow'],u['wp']),(0,0,9));self.assertTrue(u['fireproof'])
        self.assertTrue(any(i['id']=='grimoire' for i in self.room()['items']))
        with self.assertRaises(ValueError):self.declare(c,'firewalker')

    def test_armor_artifact_and_wear_follow_normal_protection(self):
        c=self.wizard('shapes',3);target=self.make_npc();self.battle(c,target)
        room=self.room();plate=dict(id='magic-plate',name='Доспех с руной',quantity=1,version=1,location=dict(kind='character',id=target['id']),weight=1,kind='armor',armor=2,wear=0,artifactDie='D8')
        room['items'].append(plate);u=room['combat']['units'][1];u.update(armor=2,maxArmor=2,armorSources=[dict(id=plate['id'],current=2,maximum=2,artifact=8)])
        self.game.save(room)
        v=self.act('declare',character=c['id'],spell='bears_claw',target=target['id'],wp=3,safe=True,note='Касаюсь противника медвежьей лапой.');r=v['magicCastings'][-1]['id'];self.approve(r)
        with patch('magic_rules.die',side_effect=[4,4,1,2,8]):self.act('cast',casting=r)
        room=self.room();self.assertEqual(room['magicCastings'][-1]['armor']['blocked'],2)
        self.assertEqual(room['characters'][1]['runtime']['current']['str'],target['runtime']['current']['str']-1)
        plate=next(i for i in room['items'] if i['id']=='magic-plate');self.assertEqual((plate['wear'],plate['version']),(1,2));self.assertEqual(room['combat']['units'][1]['armor'],1)

    def test_restore_invalidates_commands_without_rerolling(self):
        c=self.wizard('sight',2);r=self.declare(c,'sense_magic');self.approve(r)
        saved=self.room();magic.restored(saved)
        restored=saved['magicCastings'][-1];self.assertNotEqual(restored['id'],r);self.assertEqual(restored['status'],'requested')
        self.act('cast',casting=r)
        saved=self.room();cast=saved['magicCastings'][-1];before=copy.deepcopy(cast);magic.restored(saved)
        self.assertNotEqual(saved['magicCastings'][-1]['id'],before['id']);self.assertEqual(saved['magicCastings'][-1]['dice'],before['dice']);self.assertEqual(saved['characters'][0]['runtime']['wp'],9)

if __name__=='__main__':unittest.main()
