import copy
import json
import unittest
import uuid
import test_server as support
from server import Game


class SceneServicesTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown
    make_pc=support.CampaignTests.make_pc

    def setup_place(self):
        self.cid=self.make_pc()['id']
        m=self.game.action(self.gs,dict(action='locationMapGenerate',title='Речной дом',settings=dict(kind='settlement',seed='scene-services')))['locationMaps'][-1]
        self.mid=m['id']
        m=self.game.action(self.gs,dict(action='locationMapPopulationGenerate',id=m['id'],version=m['version'],count=5,mode='artisans',kin='human',seed='folk',revealed=True))['locationMaps'][-1]
        self.rid=m['population']['residents'][0]['id']
        self.game.action(self.gs,dict(action='locationMapReveal',id=m['id'],version=m['version'],revealed=True))
        self.game.action(self.ps,dict(action='inventoryOpen',character=self.cid))
        room=self.game.room(self.gs['room']);c=next(c for c in room['characters'] if c['id']==self.cid);c['runtime']['coins']=dict(gold=1,silver=2,copper=3);self.game.save(room)

    def act(self,op,s=None,**d):return self.game.action(s or self.gs,dict(action='residentService',op=op,map=self.mid,resident=self.rid,**d))
    def m(self):return next(m for m in self.game.view(self.gs)['locationMaps'] if m['id']==self.mid)
    def explore(self,op,**d):return self.game.action(self.gs,dict(action='exploration',op=op,map=self.mid,version=self.m()['version'],**d))

    def test_atomic_purchase_replay_stock_and_foreign_wallet(self):
        self.setup_place()
        offer=self.act('offer',kind='goods',title='Верёвка',price=13,stock=2,minutes=0,active=True,item=dict(name='Верёвка',weight=1,gmNote='SECRET-STOCK'))['residentServices']['offers'][0]
        req=dict(action='residentService',op='buy',offer=offer['id'],version=offer['version'],character=self.cid,count=2,requestId=str(uuid.uuid4()))
        stranger=self.game.login(dict(name='Чужой',code=self.gm['code'],key=self.gm['playerKey']))
        with self.assertRaises(PermissionError):self.game.action(self.game.session(stranger['token']),req)
        result=self.game.action(self.ps,req);again=self.game.action(self.ps,req)
        self.assertEqual(result['revision'],again['revision'])
        c=next(c for c in result['characters'] if c['id']==self.cid)
        self.assertEqual(c['runtime']['coins'],dict(gold=0,silver=9,copper=7))
        self.assertEqual(len([i for i in result['items'] if i['name']=='Верёвка' and i['quantity']==2]),1)
        self.assertNotIn('SECRET-STOCK',json.dumps(result))
        with self.assertRaises(ValueError):self.game.action(self.ps,{**req,'requestId':str(uuid.uuid4())})

    def test_service_deadline_cost_once_cancellation_and_restart(self):
        self.setup_place()
        offer=self.act('offer',kind='service',title='Ночлег',price=20,stock=1,minutes=360,active=True)['residentServices']['offers'][0]
        v=self.act('request',self.ps,offer=offer['id'],version=offer['version'],character=self.cid)
        order=v['residentServices']['contracts'][0]
        with self.assertRaises(PermissionError):self.act('complete',self.ps,contract=order['id'],version=1,confirmed=True,note='Отдохнул')
        with self.assertRaises(ValueError):self.act('complete',contract=order['id'],version=1,confirmed=True,note='Отдохнул')
        self.game.action(self.gs,dict(action='injury',op='advance',minutes=360,note='Ночь в поселении'))
        self.act('complete',contract=order['id'],version=1,confirmed=True,note='Ночлег предоставлен')
        with self.assertRaises(ValueError):self.act('complete',contract=order['id'],version=1,confirmed=True,note='Повторная оплата')
        before=self.game.view(self.ps);self.game.db.close();self.game=Game(self.path,reference_root=self.path.parent/'local-assets')
        after=self.game.view(self.ps);self.assertEqual(before['residentServices'],after['residentServices'])
        order=self.act('request',self.ps,offer=offer['id'],version=offer['version'],character=self.cid)['residentServices']['contracts'][-1]
        self.act('cancel',self.ps,contract=order['id'],version=1)
        c=next(c for c in self.game.view(self.ps)['characters'] if c['id']==self.cid)
        self.assertEqual(c['runtime']['coins'],dict(gold=1,silver=0,copper=3))

    def test_repair_uses_successes_and_teaching_only_grants_prerequisite(self):
        self.setup_place()
        offer=self.act('offer',kind='training',title='Урок ремесла',skill='craft',teacherRank=2,price=0,stock=1,minutes=1,active=True)['residentServices']['offers'][0]
        order=self.act('request',self.ps,offer=offer['id'],version=1,character=self.cid)['residentServices']['contracts'][0]
        self.assertEqual(order['dueAt']-order['createdAt'],360)
        self.game.action(self.gs,dict(action='injury',op='advance',minutes=360,note='Четверть у учителя'))
        r=self.act('complete',contract=order['id'],version=1,confirmed=True,note='Учитель подтвердил четверть занятий')
        c=next(c for c in r['characters'] if c['id']==self.cid);self.assertEqual(c['sheet']['skills']['craft'],0)
        self.assertEqual(c['sheet']['progression']['training']['craft']['method'],'teacher')
        room=self.game.room(self.gs['room']);room['items'].append(dict(id='damaged',name='Инструмент',kind='gear',quantity=1,bonus=3,armor=0,wear=2,weight=1,version=1,location=dict(kind='character',id=self.cid)));self.game.save(room)
        o=self.act('offer',kind='repair',title='Ремонт инструмента',price=1,stock=1,minutes=0,active=True)['residentServices']['offers'][-1]
        order=self.act('request',self.ps,offer=o['id'],version=1,character=self.cid,item='damaged')['residentServices']['contracts'][-1]
        r=self.act('complete',contract=order['id'],version=1,confirmed=True,note='Ремесло: один успех',hits=1)
        self.assertEqual(next(i for i in r['items'] if i['id']=='damaged')['wear'],1)

    def test_discovery_hides_geometry_people_services_and_tokens(self):
        self.setup_place();m=self.m();f=m['features'][0]
        self.act('offer',kind='service',title='PRIVATE-OFFER',price=1,stock=1,minutes=0,active=True)
        self.explore('settings',enabled=True,dark=True)
        room=self.game.room(self.gs['room']);m=next(m for m in room['locationMaps'] if m['id']==self.mid)
        m['tokens']=[dict(id='hidden-token',characterId=self.cid,x=f['x']+f['w']/2,y=f['y']+f['h']/2,secret=False)];self.game.save(room)
        public=self.game.view(self.ps);m=public['locationMaps'][0]
        self.assertEqual(m['features'],[]);self.assertEqual(m['tokens'],[])
        self.assertFalse(public['residentServices']['offers']);self.assertNotIn('hidden-token',json.dumps(public))
        self.explore('discover',feature=f['id'],revealed=True)
        m=self.game.view(self.ps)['locationMaps'][0];self.assertEqual([x['id'] for x in m['features']],[f['id']]);self.assertEqual(len(m['tokens']),1)
        with self.assertRaises(PermissionError):self.game.action(self.ps,dict(action='exploration',op='settings',map=self.mid,version=m['version'],enabled=False,dark=False))

    def test_light_expiry_scene_privacy_and_stale_map(self):
        self.setup_place();m=self.m();version=m['version'];f=m['features'][0]
        self.explore('light',name='Фонарь',x=f['x'],y=f['y'],radius=10,minutes=15)
        with self.assertRaises(ValueError):self.game.action(self.gs,dict(action='exploration',op='settings',map=self.mid,version=version,enabled=True,dark=True))
        self.game.action(self.gs,dict(action='injury',op='advance',minutes=15,note='Осмотр комнаты'))
        self.assertTrue(self.m()['exploration']['lights'][0]['expired'])
        self.game.action(self.gs,dict(action='exploration',op='scene',version=0,map=self.mid,title='SECRET-SCENE',description='Скрытая сцена'))
        m=self.m();self.game.action(self.gs,dict(action='locationMapReveal',id=self.mid,version=m['version'],revealed=False))
        self.assertNotIn('SECRET-SCENE',json.dumps(self.game.view(self.ps)))

    def test_checkpoint_invalidates_old_contract_and_hides_secret_work(self):
        from save_points import apply as checkpoint
        self.setup_place()
        offer=self.act('offer',kind='service',title='Согласованная работа',price=20,stock=1,minutes=0,active=True)['residentServices']['offers'][0]
        order=self.act('request',self.ps,offer=offer['id'],version=1,character=self.cid)['residentServices']['contracts'][0]
        saved=checkpoint(self.game,self.gs,dict(operation='create',scope='campaign',label='До работы'))
        self.act('complete',contract=order['id'],version=1,confirmed=True,note='Работа выполнена')
        checkpoint(self.game,self.gs,dict(operation='restore',scope='campaign',id=saved['id'],revision=self.game.view(self.gs)['revision'],confirmed=True))
        with self.assertRaises(ValueError):self.act('complete',contract=order['id'],version=1,confirmed=True,note='Старая команда после отката')
        fresh=self.game.view(self.gs)['residentServices']['contracts'][0]
        self.act('complete',contract=fresh['id'],version=fresh['version'],confirmed=True,note='Работа в новой ветке')
        c=next(c for c in self.game.view(self.ps)['characters'] if c['id']==self.cid)
        self.assertEqual(c['runtime']['coins'],dict(gold=1,silver=0,copper=3))
        m=self.m();self.game.action(self.gs,dict(action='locationMapReveal',id=m['id'],version=m['version'],revealed=False))
        secret=self.act('offer',kind='service',title='SECRET-CONTRACT',price=0,stock=1,minutes=0,active=True)['residentServices']['offers'][-1]
        self.act('request',offer=secret['id'],version=1,character=self.cid)
        self.assertNotIn('SECRET-CONTRACT',json.dumps(self.game.view(self.ps)))
