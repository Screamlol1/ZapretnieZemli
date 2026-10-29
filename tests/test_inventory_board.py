import unittest
from unittest.mock import patch
import test_server as support


class InventoryBoardTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown
    make_pc=support.CampaignTests.make_pc
    make_npc=support.CampaignTests.make_npc

    def hero(self):
        c=self.make_pc();self.game.action(self.ps,dict(action='inventoryOpen',character=c['id']));return c
    def view(self):return self.game.view(self.gs)
    def resource(self,c,op='use',resource='arrows',session=None,**kw):
        return self.game.action(session or self.ps,dict(action='inventoryResource',character=c['id'],op=op,resource=resource,revision=self.view()['revision'],**kw))
    def set_stock(self,c,resource,value):return self.resource(c,'set',resource,self.gs,value=value,note='Тестовый запас')
    def stack(self,c):
        return self.game.action(self.gs,dict(action='itemCreate',location=dict(kind='character',id=c['id']),item=dict(name='Эликсир',art='potion',quantity=5,weight=.5,gmNote='SECRET',description='Редкий настой')))['items'][-1]

    def test_consumable_falls_on_one_two_and_last_die_empties(self):
        c=self.hero();self.set_stock(c,'arrows',8)
        old=self.view()['revision'];command=dict(action='inventoryResource',character=c['id'],resource='arrows',op='use',revision=old)
        with patch('inventory_actions.secrets.randbelow',return_value=0):v=self.game.action(self.ps,command)
        self.assertEqual(v['characters'][0]['runtime']['resources']['arrows'],6)
        self.assertEqual(v['diceRolls'][-1]['groups'][0]['sides'],8)
        with self.assertRaises(ValueError):self.game.action(self.ps,command)
        with patch('inventory_actions.secrets.randbelow',return_value=1):v=self.resource(c)
        self.assertEqual(v['characters'][0]['runtime']['resources']['arrows'],0)
        with self.assertRaises(ValueError):self.resource(c)
        self.assertEqual(len(self.view()['diceRolls']),2)

    def test_no_change_roll_still_rejects_duplicate_and_daily_food_matches_travel(self):
        c=self.hero();self.set_stock(c,'food',8)
        with patch('inventory_actions.secrets.randbelow',return_value=5):self.resource(c,resource='food')
        self.assertEqual(self.view()['characters'][0]['runtime']['resources']['food'],8)
        with self.assertRaises(ValueError):self.resource(c,resource='food')
        room=self.game.room(self.gs['room']);room['journey']['party']=[c['id']];self.game.save(room)
        with self.assertRaises(ValueError):self.game.action(self.ps,dict(action='travelConsume',id=c['id'],resource='food'))
        room=self.game.room(self.gs['room']);room['journey']['day']+=1;self.game.save(room)
        with patch('inventory_actions.secrets.randbelow',return_value=5):self.resource(c,resource='food')

    def test_share_conserves_steps_caps_and_permissions(self):
        c=self.hero();npc=self.make_npc();self.set_stock(c,'water',12);self.set_stock(npc,'water',10)
        with self.assertRaises(PermissionError):self.resource(c,'share','water',target=npc['id'],steps=1)
        v=self.resource(c,'share','water',self.gs,target=npc['id'],steps=1)
        by={x['id']:x for x in v['characters']};self.assertEqual(by[c['id']]['runtime']['resources']['water'],10);self.assertEqual(by[npc['id']]['runtime']['resources']['water'],12)
        before=self.view()
        with self.assertRaises(ValueError):self.resource(c,'share','water',self.gs,target=npc['id'],steps=1)
        self.assertEqual(before,self.view())
        with self.assertRaises(PermissionError):self.resource(c,'set','water',value=12,note='Чит')
        stranger=self.game.login(dict(name='Чужой',code=self.gm['code'],key=self.gm['playerKey']));ss=self.game.session(stranger['token'])
        with self.assertRaises(PermissionError):self.resource(c,session=ss,resource='water')

    def test_hidden_npc_resource_roll_does_not_leak(self):
        npc=self.make_npc(hidden=True);self.set_stock(npc,'arrows',8)
        self.resource(npc,session=self.gs)
        public=self.game.view(self.ps);self.assertEqual(public['diceRolls'],[]);self.assertNotIn(npc['name'],str(public['log']))

    def test_stock_edit_conflict_and_combat_inventory_locks(self):
        c=self.hero();i=self.stack(c);npc=self.make_npc();self.set_stock(c,'arrows',8)
        with self.assertRaises(ValueError):self.resource(c,'set','arrows',self.gs,value=12,note='Старое окно',expectedValue=6)
        self.assertEqual(self.view()['characters'][0]['runtime']['resources']['arrows'],8)
        self.game.action(self.gs,dict(action='combatCreate',units=[dict(id=c['id'],team='A'),dict(id=npc['id'],team='B')]))
        for action,extra in [('itemSplit',dict(quantity=1)),('itemConsume',dict(quantity=1,confirmed=True)),('itemAppearance',dict(art='scroll'))]:
            with self.assertRaises(ValueError):self.game.action(self.ps,dict(action=action,id=i['id'],version=i['version'],**extra))
        with self.assertRaises(ValueError):self.set_stock(c,'arrows',12)
        with patch('inventory_actions.secrets.randbelow',return_value=0):self.resource(c)
        self.assertEqual(self.view()['characters'][0]['runtime']['resources']['arrows'],6)
        room=self.game.room(self.gs['room']);room['combat']['pendingRisk']={'id':'unresolved'};self.game.save(room)
        with self.assertRaises(ValueError):self.resource(c)

    def test_split_merge_consume_preserve_properties_and_versions(self):
        c=self.hero();i=self.stack(c)
        cmd=dict(action='itemSplit',id=i['id'],version=i['version'],quantity=2)
        self.game.action(self.ps,cmd)
        with self.assertRaises(ValueError):self.game.action(self.ps,cmd)
        stacks=[x for x in self.view()['items'] if x['name']=='Эликсир'];self.assertEqual(sorted(x['quantity'] for x in stacks),[2,3])
        for x in stacks:self.assertEqual(x['gmNote'],'SECRET');self.assertEqual(x['art'],'potion')
        a,b=stacks;self.game.action(self.ps,dict(action='itemMerge',id=a['id'],version=a['version'],target=b['id'],targetVersion=b['version']))
        one=next(x for x in self.view()['items'] if x['name']=='Эликсир');self.assertEqual(one['quantity'],5)
        cmd=dict(action='itemConsume',id=one['id'],version=one['version'],quantity=5,confirmed=True)
        self.game.action(self.ps,cmd)
        with self.assertRaises(ValueError):self.game.action(self.ps,cmd)
        self.assertFalse(any(x['name']=='Эликсир' for x in self.view()['items']))

    def test_appearance_preserves_mechanics_and_unequip_when_last_item_removed(self):
        c=self.hero();i=self.stack(c)
        v=self.game.action(self.ps,dict(action='itemAppearance',id=i['id'],version=i['version'],art='scroll'))
        own=next(x for x in v['items'] if x['id']==i['id']);self.assertEqual(own['quantity'],5);self.assertNotIn('gmNote',own)
        self.assertEqual(next(x for x in self.view()['items'] if x['id']==i['id'])['gmNote'],'SECRET')
        with self.assertRaises(ValueError):self.game.action(self.ps,dict(action='itemAppearance',id=i['id'],version=own['version'],art='<script>'))
        v=self.game.action(self.gs,dict(action='itemCreate',location=dict(kind='character',id=c['id']),item=dict(name='Клинок',kind='weapon',combatProfile='sword',quantity=1,bonus=2)))
        weapon=v['items'][-1];hero=next(x for x in v['characters'] if x['id']==c['id'])
        self.game.action(self.ps,dict(action='equipment',character=c['id'],slot='weapon',item=weapon['id'],itemVersion=weapon['version'],version=hero['equipmentVersion']))
        self.game.action(self.ps,dict(action='itemConsume',id=weapon['id'],version=weapon['version'],quantity=1,confirmed=True))
        self.assertNotIn('weapon',self.view()['characters'][0]['equipment'])


if __name__=='__main__':unittest.main()
