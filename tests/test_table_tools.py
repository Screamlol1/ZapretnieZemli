import copy
import json
import time
import unittest
import test_server as support


class TableToolsTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown
    make_pc=support.CampaignTests.make_pc

    def tool(self,op,session=None,**data):return self.game.action(session or self.ps,dict(action='tableTool',op=op,**data))
    def room(self):return self.game.room(self.gs['room'])
    def travel(self,action,session=None,**data):
        t=self.room()['journey'];s=session or self.gs
        return self.game.action(s,dict(action=action,revision=t['revision'],cycle=[t['day'],t['quarter'],t['cycleId']],phase=t['phase'],routeVersion=t['routeVersion'],completionVersion=t['completionVersions'].get('gm' if s['role']=='gm' else s['owner'],0),**data))
    def prepare(self):
        cid=self.make_pc()['id'];self.travel('travelSetup',party=[cid],x=0,y=0,season='summer');return cid
    def paint(self,x,y,hidden):self.game.action(self.gs,dict(action='paint',map='world',x=x,y=y,terrain='plain',hidden=hidden))

    def test_map_pings_and_focus_never_reveal_hidden_hexes_or_locations(self):
        self.paint(1,0,False);self.tool('ping',x=1,y=0)
        with self.assertRaisesRegex(ValueError,'две секунды'):self.tool('ping',x=2,y=0)
        with self.assertRaises(PermissionError):self.tool('focus',target=dict(kind='world',x=1,y=0))
        self.tool('focus',session=self.gs,target=dict(kind='world',x=1,y=0))
        self.paint(1,0,True)
        view=self.game.view(self.ps);self.assertEqual(view['tableTools']['pings'],[]);self.assertNotIn('focus',view['tableTools'])
        for s in (self.ps,self.gs):
            with self.assertRaises(ValueError):self.tool('ping',session=s,x=1,y=0)
        m=self.game.action(self.gs,dict(action='locationMapGenerate',title='Скрытое логово',settings=dict(kind='cave',seed='table-test')))['locationMaps'][-1]
        with self.assertRaisesRegex(ValueError,'Откройте'):self.tool('focus',session=self.gs,target=dict(kind='location',id=m['id']))
        self.game.action(self.gs,dict(action='locationMapReveal',id=m['id'],version=m['version'],revealed=True))
        self.tool('focus',session=self.gs,target=dict(kind='location',id=m['id']))
        self.assertEqual(self.game.view(self.ps)['tableTools']['focus']['target'],dict(kind='location',id=m['id']))

    def test_route_is_only_proposal_until_gm_accepts_and_rejects_stale_or_hidden(self):
        self.prepare();t=self.room()['journey'];owner=self.ps['owner'];path=[dict(x=1,y=0),dict(x=2,y=0)]
        self.tool('propose',cycle=t['cycleId'],version=0,path=path)
        self.assertEqual(self.room()['journey']['route'],[]);self.assertEqual(self.room()['journey']['position'],dict(x=0,y=0))
        with self.assertRaises(PermissionError):self.tool('acceptRoute',owner=owner,version=1)
        with self.assertRaisesRegex(ValueError,'другом окне'):self.tool('propose',cycle=t['cycleId'],version=0,path=path)
        with self.assertRaisesRegex(ValueError,'стартовый'):self.tool('propose',cycle=t['cycleId'],version=1,path=[dict(x=1,y=0),dict(x=0,y=0)])
        def accept(version=1):
            t=self.room()['journey'];return self.tool('acceptRoute',session=self.gs,owner=owner,version=version,revision=t['revision'],cycle=[t['day'],t['quarter'],t['cycleId']],phase=t['phase'],routeVersion=t['routeVersion'])
        self.paint(2,0,True)
        self.assertEqual(self.game.view(self.ps)['tableTools']['proposals'],{})
        with self.assertRaises(ValueError):accept()
        self.paint(2,0,False);accept();self.assertEqual(self.room()['journey']['route'],path)
        self.assertTrue(self.room()['tableTools']['proposals'][owner]['accepted'])
        self.tool('withdraw',cycle=t['cycleId'],version=1)
        self.assertEqual(self.room()['journey']['route'],path)
        with self.assertRaisesRegex(ValueError,'устарело'):accept()
        self.travel('travelRelocate',x=3,y=0,confirmed=True)
        self.assertEqual(self.game.view(self.ps)['tableTools']['proposals'],{})
        with self.assertRaises(ValueError):self.tool('propose',cycle=t['cycleId'],version=2,path=path)

    def test_absent_control_does_not_confirm_automatically_and_return_revokes(self):
        cid=self.prepare();owner=self.ps['owner']
        with self.assertRaises(PermissionError):self.tool('claim',owner=owner)
        with self.assertRaisesRegex(ValueError,'подключён'):self.tool('claim',session=self.gs,owner=owner)
        self.game.sessions[self.player['token']]['seen']=time.time()-60
        self.tool('claim',session=self.gs,owner=owner)
        room=self.room();self.assertEqual(room['characters'][0]['owner'],owner);self.assertEqual(room['journey']['completed'],{})
        room['journey'].update(phase='resolving',pending=[],completed={},completionVersions={},automatic=True);self.game.save(room)
        t=self.room()['journey'];oldcycle=t['cycleId']
        self.tool('completeFor',session=self.gs,owner=owner,complete=True,revision=t['revision'],cycle=[t['day'],t['quarter'],t['cycleId']],phase=t['phase'],completionVersion=0)
        self.assertEqual(self.room()['journey']['cycleId'],oldcycle);self.assertTrue(self.room()['journey']['completed'][owner])
        self.travel('travelComplete',complete=True)
        self.assertNotEqual(self.room()['journey']['cycleId'],oldcycle)
        returned=self.game.reconnect(dict(code=self.player['code'],resume=self.player['resume']))
        self.assertEqual(self.game.session(returned['token'])['owner'],owner);self.assertNotIn(owner,self.room()['tableTools']['control'])
        self.assertIn('вернулся',self.room()['log'][-1]['text'])
        with self.assertRaises(ValueError):self.tool('completeFor',session=self.gs,owner=owner,complete=True)

    def test_proxy_requires_claim_and_current_result_version(self):
        self.prepare();owner=self.ps['owner'];self.game.sessions[self.player['token']]['seen']=time.time()-60
        room=self.room();room['journey'].update(phase='resolving',pending=[],completed={},completionVersions={owner:2});self.game.save(room);t=self.room()['journey']
        data=dict(owner=owner,complete=True,revision=t['revision'],cycle=[t['day'],t['quarter'],t['cycleId']],phase=t['phase'],completionVersion=1)
        with self.assertRaises(ValueError):self.tool('completeFor',session=self.gs,**data)
        self.tool('claim',session=self.gs,owner=owner)
        with self.assertRaisesRegex(ValueError,'Результаты'):self.tool('completeFor',session=self.gs,**data)
        self.assertNotIn(owner,self.room()['journey']['completed'])
        self.tool('release',session=self.gs,owner=owner)
        with self.assertRaises(ValueError):self.tool('completeFor',session=self.gs,**{**data,'completionVersion':2})
