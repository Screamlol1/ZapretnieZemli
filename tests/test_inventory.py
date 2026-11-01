import unittest
import test_server as support

class InventoryTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown
    make_pc=support.CampaignTests.make_pc
    make_npc=support.CampaignTests.make_npc

    def open(self):
        c=self.make_pc();view=self.game.action(self.ps,dict(action='inventoryOpen',character=c['id']))
        return c,view

    def test_starting_items_migrate_once_and_sheet_edits_never_refill(self):
        c,v=self.open();ids=[i['id'] for i in v['items']]
        self.assertTrue(ids);self.assertIn('Рюкзак',[i['name'] for i in v['items']])
        self.game.action(self.ps,dict(action='inventoryOpen',character=c['id']))
        self.game.action(self.ps,dict(action='character',id=c['id'],sheet=c['sheet']))
        v=self.game.action(self.ps,dict(action='inventoryOpen',character=c['id']))
        self.assertEqual(ids,[i['id'] for i in v['items']])
        self.assertEqual(v['characters'][0]['runtime']['resources']['food'],8)

    def test_artifact_secrets_and_mechanics_require_gm(self):
        c,v=self.open();location=dict(kind='character',id=c['id'])
        raw=dict(name='Ключ бури',kind='artifact',quantity=1,weight=.5,artifactDie='D8',effect='Решение Мастера',gmNote='Секретный ключ')
        with self.assertRaises(PermissionError):self.game.action(self.ps,dict(action='itemCreate',location=location,item=raw))
        v=self.game.action(self.gs,dict(action='itemCreate',location=location,item=raw));i=v['items'][-1]
        own=next(x for x in self.game.view(self.ps)['items'] if x['id']==i['id'])
        self.assertNotIn('gmNote',own);self.assertEqual(own['artifactDie'],'D8')
        stranger=self.game.login(dict(name='Stranger',code=self.gm['code'],key=self.gm['playerKey']))
        ss=self.game.session(stranger['token'])
        self.assertEqual(self.game.view(ss)['items'],[])
        with self.assertRaises(PermissionError):self.game.action(ss,dict(action='itemTransfer',id=i['id'],version=i['version'],location=dict(kind='treasury',id=''),quantity=1))

    def test_split_transfer_rejects_stale_commands_without_duplication(self):
        c,v=self.open();location=dict(kind='character',id=c['id'])
        room=self.game.room(self.gs['room']);room['strongholds']=[dict(id='hold',name='Дом')];self.game.save(room)
        v=self.game.action(self.ps,dict(action='itemCreate',location=location,item=dict(name='Камни',weight=1,quantity=5)))
        i=v['items'][-1];command=dict(action='itemTransfer',id=i['id'],version=i['version'],quantity=2,location=dict(kind='hold',id='hold'))
        self.game.action(self.ps,command)
        with self.assertRaises(ValueError):self.game.action(self.ps,command)
        items=[x for x in self.game.view(self.gs)['items'] if x['name']=='Камни']
        self.assertEqual(sorted(x['quantity'] for x in items),[2,3])
        with self.assertRaises(PermissionError):self.game.action(self.ps,dict(action='itemEdit',id=i['id'],version=2,item=dict(name='Магический камень')))

    def test_hidden_items_do_not_leak_into_log_and_deleted_owner_keeps_property(self):
        c,v=self.open();i=v['items'][0]
        self.game.action(self.gs,dict(action='itemEdit',id=i['id'],version=i['version'],item=dict(name='Секретное имя',gmNote='Секрет')))
        self.game.action(self.gs,dict(action='itemTransfer',id=i['id'],version=2,quantity=1,location=dict(kind='treasury',id='')))
        self.assertNotIn('Секретное имя',str(self.game.view(self.ps)['log']))
        self.game.action(self.gs,dict(action='deleteCharacter',id=c['id']))
        self.assertTrue(all(x['location']['kind']=='treasury' for x in self.game.view(self.gs)['items']))
        self.assertEqual(self.game.view(self.ps)['items'],[])

    def test_negative_fractional_and_locked_mutations_leave_state_unchanged(self):
        c,v=self.open();location=dict(kind='character',id=c['id']);before=self.game.view(self.gs)['items']
        for raw in (dict(name='Bad',quantity=1.5),dict(name='Bad',weight=-1),dict(name='Bad',weight=float('nan'))):
            with self.assertRaises(ValueError):self.game.action(self.gs,dict(action='itemCreate',location=location,item=raw))
        room=self.game.room(self.gs['room']);room['journey']['party']=[c['id']];room['journey']['phase']='resolving';self.game.save(room)
        with self.assertRaises(ValueError):self.game.action(self.gs,dict(action='itemCreate',location=location,item=dict(name='Blocked')))
        self.assertEqual(self.game.view(self.gs)['items'],before)
