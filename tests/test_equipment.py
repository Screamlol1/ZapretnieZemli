import unittest
from unittest.mock import patch
import test_server as support
from equipment_rules import sync_wear

class EquipmentTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown
    make_pc=support.CampaignTests.make_pc
    make_npc=support.CampaignTests.make_npc

    def hero(self):
        c=self.make_pc();self.game.action(self.ps,dict(action='inventoryOpen',character=c['id']));return c
    def current(self,c):return next(x for x in self.game.view(self.gs)['characters'] if x['id']==c['id'])
    def item(self,c,**values):
        return self.game.action(self.gs,dict(action='itemCreate',location=dict(kind='character',id=c['id']),item=dict(name='Меч бури',kind='artifact',combatProfile='sword',bonus=4,damage=3,weight=1,artifactDie='D10',**values)))['items'][-1]
    def equip(self,c,i,slot='weapon',session=None):
        return self.game.action(session or self.ps,dict(action='equipment',character=c['id'],slot=slot,item=i['id'],itemVersion=i['version'],version=self.current(c)['equipmentVersion']))
    def battle(self,c,npc):return self.game.action(self.gs,dict(action='combatCreate',units=[dict(id=c['id'],team='A'),dict(id=npc['id'],team='B')]))

    def test_travel_initializes_unopened_inventory_once(self):
        c=self.make_pc();t=self.game.view(self.gs)['journey']
        command=dict(action='travelSetup',party=[c['id']],x=0,y=0,season='summer',revision=t['revision'])
        v=self.game.action(self.gs,command)
        current=next(x for x in v['characters'] if x['id']==c['id'])
        self.assertTrue(current['inventoryInitialized']);self.assertIn('load',current)
        before=v['items'];resources=current['runtime']['resources'].copy()
        self.game.action(self.ps,dict(action='inventoryOpen',character=c['id']))
        self.assertEqual(before,self.game.view(self.gs)['items'])
        self.assertEqual(resources,self.current(c)['runtime']['resources'])

    def test_custom_equipment_drives_combat_and_transfer_removes_old_weapon(self):
        c=self.hero();i=self.item(c);self.equip(c,i);npc=self.make_npc()
        v=self.battle(c,npc);u=next(u for u in v['combat']['units'] if u['id']==c['id'])
        self.assertEqual((u['gear'],u['weaponStats']['damage'],u['weaponArtifact']),(4,3,10))
        with self.assertRaises(ValueError):self.game.action(self.ps,dict(action='itemTransfer',id=i['id'],version=i['version'],quantity=1,location=dict(kind='character',id=npc['id'])))
        self.game.action(self.gs,dict(action='combatClose'))
        self.game.action(self.gs,dict(action='itemTransfer',id=i['id'],version=i['version'],quantity=1,location=dict(kind='character',id=npc['id'])))
        self.assertNotIn('weapon',self.current(c)['equipment'])
        v=self.battle(c,npc);u=next(u for u in v['combat']['units'] if u['id']==c['id']);self.assertEqual(u['gear'],0)

    def test_wear_follows_item_across_battles_and_repair_is_gm_only(self):
        c=self.hero();i=self.item(c);self.equip(c,i);npc=self.make_npc()
        room=self.game.room(self.gs['room']);sync_wear(room,dict(units=[dict(id=c['id'],equipmentWear=[dict(id=i['id'],maximum=4,current=1)])]));self.game.save(room)
        v=self.battle(c,npc);u=next(u for u in v['combat']['units'] if u['id']==c['id']);self.assertEqual(u['gear'],1)
        self.game.action(self.gs,dict(action='combatClose'))
        with self.assertRaises(PermissionError):self.game.action(self.ps,dict(action='itemWear',id=i['id'],version=2,wear=0,note='Repair'))
        self.game.action(self.gs,dict(action='itemWear',id=i['id'],version=2,wear=1,note='Ремесло: два успеха'))
        v=self.battle(c,npc);u=next(u for u in v['combat']['units'] if u['id']==c['id']);self.assertEqual(u['gear'],3)

    def test_equipment_versions_ownership_and_sheet_save(self):
        c=self.hero();i=self.item(c);old=self.current(c)['equipmentVersion'];self.equip(c,i)
        with self.assertRaises(ValueError):self.game.action(self.ps,dict(action='equipment',character=c['id'],slot='weapon',item='',version=old))
        stranger=self.game.login(dict(name='Other',code=self.gm['code'],key=self.gm['playerKey']))
        with self.assertRaises(PermissionError):self.equip(c,i,session=self.game.session(stranger['token']))
        self.game.action(self.ps,dict(action='character',id=c['id'],sheet=c['sheet']))
        self.assertEqual(self.current(c)['equipment']['weapon'],i['id'])

    def test_legacy_wear_migrates_only_once_and_never_refills(self):
        c=self.make_pc();room=self.game.room(self.gs['room']);room['characters'][0]['runtime']['gearBonus']=0;self.game.save(room)
        self.game.action(self.ps,dict(action='inventoryOpen',character=c['id']))
        before=self.game.view(self.gs)['items'];self.game.action(self.ps,dict(action='inventoryOpen',character=c['id']))
        self.assertEqual(before,self.game.view(self.gs)['items'])
        for i in before:
            if i.get('combatProfile'):self.assertEqual(i['wear'],i['bonus'])

    @patch('skill_checks.die',side_effect=lambda sides=6:sides)
    def test_skill_pool_uses_wounds_separate_penalty_item_and_artifact(self,_):
        c=self.hero();i=self.item(c)
        data=dict(action='characterRoll',character=c['id'],skill='lore',modifier=-2,item=i['id'],itemVersion=i['version'],revision=self.game.view(self.gs)['revision'])
        v=self.game.action(self.ps,data);r=next(x for x in v['characters'] if x['id']==c['id'])['runtime']['lastCheck']
        self.assertEqual(len(r['gear']),4);self.assertEqual(r['artifact'],[10]);self.assertFalse(r['negative']);self.assertEqual(r['penalty'],[6,6]);self.assertEqual(len(r['skillDice']),c['sheet']['skills']['lore'])
        self.assertEqual(r['hits'],len(r['base'])-2+4+3)
        with self.assertRaises(ValueError):self.game.action(self.ps,data)

    @patch('skill_checks.die',return_value=1)
    def test_push_wears_correct_item_once_and_preserves_resource_dice(self,_):
        c=self.hero();i=self.item(c)
        v=self.game.action(self.ps,dict(action='characterRoll',character=c['id'],skill='survive',modifier=0,item=i['id'],itemVersion=i['version'],revision=self.game.view(self.gs)['revision']))
        r=next(x for x in v['characters'] if x['id']==c['id'])['runtime']['lastCheck'];cmd=dict(action='characterPush',character=c['id'],roll=r['id'])
        self.game.action(self.ps,cmd)
        with self.assertRaises(ValueError):self.game.action(self.ps,cmd)
        v=self.game.view(self.gs);item=next(x for x in v['items'] if x['id']==i['id']);self.assertEqual(item['wear'],4)
        current=self.current(c);self.assertEqual(current['runtime']['current']['wit'],0);self.assertEqual(current['runtime']['resources']['food'],8)

    def test_transfer_invalidates_push_and_coins_affect_load(self):
        c=self.hero();i=self.item(c)
        self.game.action(self.ps,dict(action='characterRoll',character=c['id'],skill='survive',modifier=0,item=i['id'],itemVersion=i['version'],revision=self.game.view(self.gs)['revision']))
        r=self.current(c)['runtime']['lastCheck']
        self.game.action(self.gs,dict(action='itemTransfer',id=i['id'],version=i['version'],quantity=1,location=dict(kind='treasury',id='')))
        with self.assertRaises(ValueError):self.game.action(self.ps,dict(action='characterPush',character=c['id'],roll=r['id']))
        self.game.action(self.gs,dict(action='inventoryCoins',character=c['id'],version=self.current(c)['equipmentVersion'],coins=dict(copper=2000)))
        self.assertEqual(self.current(c)['load']['coins'],10);self.assertTrue(self.current(c)['load']['overloaded'])

    def test_two_handed_weapon_and_shield_are_incompatible(self):
        c=self.hero();i=self.item(c,grip='2Р');self.equip(c,i)
        sh=self.game.action(self.gs,dict(action='itemCreate',location=dict(kind='character',id=c['id']),item=dict(name='Щит',kind='shield',bonus=2)))['items'][-1]
        with self.assertRaises(ValueError):self.equip(c,sh,'shield')
        self.assertNotIn('shield',self.current(c)['equipment'])
