import copy
import unittest
from unittest.mock import patch
import test_server as support
import card_combat
import siege
import weapon_poison
from equipment_rules import PROFILES,weapon_properties


class WarfareTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown
    make_pc=support.CampaignTests.make_pc
    make_npc=support.CampaignTests.make_npc

    def command(self,command,session=None):
        return self.game.action(session or self.gs,dict(action='combatAction',revision=self.game.view(self.gs)['combatRevision'],command=command))

    def test_hidden_combinations_ownership_reload_and_once_only(self):
        pc=self.make_pc();npc=self.make_npc()
        self.game.action(self.gs,dict(action='combatCreate',units=[dict(id=pc['id'],team='A'),dict(id=npc['id'],team='B')]))
        with self.assertRaises(PermissionError):self.command(dict(action='cardEnable',value=True),self.ps)
        self.command(dict(action='cardEnable',value=True));self.command(dict(action='start'))
        room=self.game.room(self.gs['room']);b=room['combat'];b['terrain']={};b['turn']=b['order'].index(pc['id'])
        for i,u in enumerate(b['units']):u.update(q=i,r=0,fast=1,slow=1,offhandOptions=[dict(id='private-'+u['id'])])
        self.game.save(room)
        v=self.command(dict(action='cardStart',unit=pc['id'],target=npc['id']),self.ps);exchange=v['combat']['cardExchange']['id']
        common=dict(exchange=exchange)
        self.command(dict(action='cardChoose',unit=npc['id'],cards=['await','defend'],**common))
        v=self.game.view(self.ps)
        self.assertEqual(v['combat']['cardExchange']['choices'][npc['id']],[None,None])
        self.assertNotIn('offhandOptions',next(u for u in v['combat']['units'] if u['id']==npc['id']))
        with self.assertRaises(PermissionError):self.command(dict(action='cardChoose',unit=npc['id'],cards=['await','defend'],**common),self.ps)
        with self.assertRaises(ValueError):self.command(dict(action='end'))
        self.command(dict(action='cardChoose',unit=pc['id'],cards=['maneuver','await'],**common),self.ps)
        self.assertEqual(self.game.view(self.ps)['combat']['cardExchange']['choices'][npc['id']],['await',None])
        for who,choice in [(pc['id'],'feint'),(npc['id'],'await')]:self.command(dict(action='cardDeclare',unit=who,choice=choice,**common))
        self.command(dict(action='cardResolve',unit=pc['id'],**common),self.ps)
        for who,choice in [(pc['id'],'await'),(npc['id'],'dodgeStand')]:self.command(dict(action='cardDeclare',unit=who,choice=choice,**common))
        self.command(dict(action='cardResolve',unit=pc['id'],**common),self.ps)
        self.assertNotIn('cardExchange',self.game.view(self.ps)['combat'])
        with self.assertRaises(ValueError):self.command(dict(action='cardResolve',unit=pc['id'],**common),self.ps)
        self.assertEqual(len(self.game.room(self.gs['room'])['combat']['lastCardExchange']['history']),2)

    def test_poison_uses_inventory_and_only_penetrating_hit_exposes_target(self):
        pc=self.make_pc();npc=self.make_npc()
        for name,kind,extra in [('Доза','gear',dict(quantity=2)),('Клинок','weapon',dict(combatProfile='dagger',bonus=1,damage=1,quantity=1))]:
            self.game.action(self.gs,dict(action='itemCreate',location=dict(kind='character',id=pc['id']),item=dict(name=name,kind=kind,weight=.5,**extra)))
        def items():return self.game.view(self.gs)['items']
        dose=next(i for i in items() if i['name']=='Доза');weapon=next(i for i in items() if i['name']=='Клинок')
        config=dict(action='weaponPoison',op='configure',character=pc['id'],item=dose['id'],version=dose['version'],type='lethal',potency=3)
        with self.assertRaises(PermissionError):self.game.action(self.ps,config)
        self.game.action(self.gs,config)
        def coat():
            d=next(i for i in items() if i['id']==dose['id']);w=next(i for i in items() if i['id']==weapon['id'])
            return self.game.action(self.ps,dict(action='weaponPoison',op='coat',character=pc['id'],item=d['id'],version=d['version'],weapon=w['id'],weaponVersion=w['version']))
        coat();self.assertEqual(next(i for i in items() if i['id']==dose['id'])['quantity'],1)
        with self.assertRaises(ValueError):coat()
        room=self.game.room(self.gs['room']);hit=dict(actor=pc['id'],target=npc['id'],action='stab',weapon=weapon['id'],damage=0)
        weapon_poison.after_combat(room,[hit]);self.assertFalse(room['weaponCoatings']);self.assertFalse(next(c for c in room['characters'] if c['id']==npc['id'])['runtime'].get('afflictions'))
        self.game.save(room);coat();room=self.game.room(self.gs['room']);weapon_poison.after_combat(room,[{**hit,'damage':1}]);weapon_poison.after_combat(room,[{**hit,'damage':1}])
        effects=next(c for c in room['characters'] if c['id']==npc['id'])['runtime']['afflictions'];self.assertEqual(len(effects),1);self.assertEqual((effects[0]['phase'],effects[0]['potency']),('exposed',3));self.assertFalse(any(i['id']==dose['id'] for i in room['items']))

    def test_poison_expires_and_is_private(self):
        pc=self.make_pc();npc=self.make_npc();room=self.game.room(self.gs['room'])
        room['items']=[dict(id='hidden',location=dict(kind='character',id=npc['id']))];room['poisonSupplies']={'hidden':dict(type='lethal',potency=9)};room['weaponCoatings']=[dict(weapon='hidden',expiresAt=360)]
        view=copy.deepcopy(room);weapon_poison.project(view,self.ps);self.assertEqual(view['poisonSupplies'],{});self.assertEqual(view['weaponCoatings'],[])
        room['medicalClock']=360;weapon_poison.reconcile(room);self.assertEqual(room['weaponCoatings'],[])

    def test_real_catalog_weapon_features(self):
        self.assertEqual(len(PROFILES),25)
        self.assertEqual(PROFILES['knife'],'dagger');self.assertEqual(PROFILES['sling'],'sling')
        knife=weapon_properties(dict(catalogId='knife',combatProfile='dagger'));self.assertFalse(knife['slash']);self.assertTrue(knife['stab']);self.assertTrue(knife['light'])
        self.assertFalse(weapon_properties(dict(catalogId='falchion',combatProfile='sword'))['parrying'])
        self.assertTrue(weapon_properties(dict(catalogId='scimitar',combatProfile='sword'))['hook'])
        self.assertFalse(weapon_properties(dict(catalogId='handaxe',combatProfile='axe'))['heavy'])
        self.assertTrue(weapon_properties(dict(catalogId='longsword',combatProfile='sword'))['heavy'])


class SiegeTests(unittest.TestCase):
    def setUp(self):
        self.gm=dict(role='gm',owner='gm');self.player=dict(role='player',owner='p');self.room=dict(journey=dict(day=1),characters=[dict(id='pc',kind='pc',owner='p')],strongholds=[dict(id='h',name='Форт',stock=dict(food=10))],log=[])
        siege.apply(self.room,self.gm,dict(op='create',hold='h',setup=dict(heroes=['pc'],defenderOwner='p',defenders=dict(guards=20,ramparts=2),attackers=dict(soldiers=60,commander=True),occupants=20,waterStock=10)))

    def action(self,op,session=None,**kwargs):
        v=self.room['strongholds'][0]['siege'];siege.apply(self.room,session or self.gm,dict(op=op,hold='h',id=v['id'],version=v['version'],**kwargs));return v

    def test_round_simultaneous_losses_event_and_decisions(self):
        v=self.action('start');self.assertEqual(v['rating'],dict(defenders=5,attackers=4))
        with self.assertRaises(PermissionError):self.action('roll',self.player,side='attackers')
        with patch('siege.die',side_effect=[6,2,2,2,2,6,2,2,2]):
            self.action('roll',self.player,side='defenders');self.assertEqual(v['phase'],'rolling')
            with self.assertRaises(ValueError):self.action('roll',self.player,side='defenders')
            self.action('roll',side='attackers')
        self.assertEqual(v['losses'],dict(defenders=1,attackers=1));self.action('loss',self.player,side='defenders',kind='ramparts');self.action('loss',side='attackers',kind='soldiers');self.assertEqual(v['phase'],'event');self.assertEqual(v['defenders']['ramparts'],1);self.assertEqual(v['attackers']['soldiers'],40)
        with patch('siege.die',return_value=3):self.action('event')
        self.room['combat']=dict(phase='combat')
        with self.assertRaises(ValueError):self.action('resolveEvent',note='Победа')
        self.room['combat']={};self.action('resolveEvent',note='Победа героя над рядовым');self.action('decision',self.player,side='defenders',value='fight');self.assertEqual(v['phase'],'decision');self.action('decision',side='attackers',value='fight');self.assertEqual((v['phase'],v['round']),('rolling',2))
        self.assertEqual([len(e['groups'][0]['values']) for e in self.room['diceRolls'][:2]],[5,4])

    def test_supply_once_and_stale_commands(self):
        v=self.room['strongholds'][0]['siege'];version=v['version'];self.action('supply');self.assertEqual(self.room['strongholds'][0]['stock']['food'],6);self.assertEqual(v['waterStock'],6)
        with self.assertRaises(ValueError):self.action('supply')
        with self.assertRaises(ValueError):siege.apply(self.room,self.gm,dict(op='start',hold='h',id=v['id'],version=version))
        self.room['journey']['day']=3;self.action('supply');self.assertTrue(v['defenders']['hungry']);self.assertEqual(v['rating']['defenders'],4)

    def test_errata_single_pc_bonus_sortie_and_undefended(self):
        v=self.room['strongholds'][0]['siege'];v['heroes']=['pc','pc2'];self.assertEqual(siege.ratings(v)['defenders'],5)
        v['sortie']=True;v['attackers'].update(ram=True,ladders=True);self.assertEqual(siege.ratings(v),dict(defenders=2,attackers=4))
        v['heroes']=[];v['defenders']['guards']=0;self.action('start');self.assertEqual((v['phase'],v['winner']),('finished','attackers'))


if __name__=='__main__':unittest.main()
