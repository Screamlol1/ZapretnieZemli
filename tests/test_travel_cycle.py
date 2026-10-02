import json
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen

sys.path.insert(0,str(Path(__file__).parents[1]))
from server import Game, make_handler


class TravelCycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.db=self.root/'campaign.sqlite';self.game=Game(self.db,reference_root=self.root/'assets')
        self.auth=self.game.login(dict(name='GM'),True);self.gm=self.game.session(self.auth['token'])
        self.auths=[self.game.login(dict(name=f'Player {i}',code=self.auth['code'],key=self.auth['playerKey'])) for i in range(2)]
        self.players=[self.game.session(a['token']) for a in self.auths]
        room=self.game.room(self.gm['room']);room['worldLayout']='legacy'
        room['characters']=[self.hero(f'hero{i}',p['owner']) for i,p in enumerate(self.players)]+[self.hero('npc',self.gm['owner'],'npc')]
        self.game.save(room);self.act('travelSetup',party=['hero0','hero1','npc'],x=0,y=0,season='summer')

    def tearDown(self):self.game.db.close();self.tmp.cleanup()

    def hero(self,cid,owner,kind='pc'):
        return dict(id=cid,name=cid,kind=kind,owner=owner,hidden=False,sheet=dict(attrs=dict(str=4,agi=3,wit=3,emp=2),skills=dict(survive=2,scout=1,endure=2),talents={}),runtime=dict(current=dict(str=4,agi=3,wit=3,emp=2),wp=0,resources=dict(food=8,water=8)))

    def payload(self,action,participant=None,**data):
        t=self.game.view(self.gm)['journey']
        p=participant or self.players[0];who='gm' if p['role']=='gm' else p['owner']
        return dict(action=action,revision=t['revision'],cycle=[t['day'],t['quarter'],t['cycleId']],phase=t['phase'],planVersion=t['planVersions'].get(data.get('id'),0),routeVersion=t['routeVersion'],completionVersion=t['completionVersions'].get(who,0),**data)

    def act(self,action,session=None,**data):return self.game.action(session or self.gm,self.payload(action,participant=session or self.gm,**data))

    def plans(self,hike=False):
        for i,p in enumerate(self.players):self.act('travelPlan',session=p,id=f'hero{i}',job='hike' if hike else 'rest',role='lead' if hike and i==0 else 'none')
        self.act('travelPlan',id='npc',job='hike' if hike else 'rest',role='none')

    def test_party_change_preserves_journey_and_repeated_setup_is_rejected(self):
        self.act('travelPlan',session=self.players[0],id='hero0',job='hike',role='lead')
        self.act('travelRoute',path=[dict(x=1,y=0)])
        before=self.game.view(self.gm)['journey']
        with self.assertRaises(ValueError):self.act('travelSetup',party=['hero0'],x=3,y=2,season='winter')
        self.assertEqual(self.game.view(self.gm)['journey'],before)
        with self.assertRaises(PermissionError):self.act('travelParty',session=self.players[0],party=['hero0'])
        t=self.act('travelParty',party=['hero0','hero1'])['journey']
        for field in ('position','day','quarter','visited','history','route','plans','planVersions'):
            self.assertEqual(t[field],before[field])
        self.assertFalse(t['gmReady'])
        old_cycle=t['cycleId']
        t=self.act('travelParty',party=['hero0','hero1'],season='winter',mounted=True)['journey']
        self.assertEqual(t['season'],'winter');self.assertTrue(t['mounted']);self.assertNotEqual(t['cycleId'],old_cycle)
        self.assertEqual(t['plans'],before['plans']);self.assertEqual(t['route'],before['route'])
        with self.assertRaises(ValueError):self.act('travelParty',party=['hero0','hero1'],season='unknown')
        with self.assertRaises(ValueError):self.act('travelRelocate',x=4,y=3,confirmed=False)
        t=self.act('travelRelocate',x=4,y=3,confirmed=True)['journey']
        self.assertEqual(t['position'],dict(x=4,y=3));self.assertEqual(t['plans'],before['plans']);self.assertEqual(t['route'],[])

    def resolve(self):
        for p in self.game.view(self.gm)['journey']['pending']:
            self.act('travelResolve',id=p['id'],note='Private outcome',reveal=False)

    @patch('campaign_rules.dice',side_effect=lambda n,sides=6:[6]*n)
    def test_waits_for_all_declarations_and_all_completions(self,_):
        self.act('travelReady',ready=True)
        self.act('travelPlan',session=self.players[0],id='hero0',job='rest')
        self.act('travelPlan',session=self.players[1],id='hero1',job='rest')
        self.assertEqual(self.game.view(self.gm)['journey']['phase'],'planning')
        v=self.act('travelPlan',id='npc',job='rest')
        self.assertEqual((v['journey']['phase'],v['journey']['quarter']),('resolving',0))
        self.assertTrue(v['journey']['pending'])
        for p in self.players:
            with self.assertRaisesRegex(ValueError,'события'):self.act('travelComplete',session=p,complete=True)
        with self.assertRaisesRegex(ValueError,'события'):self.act('travelComplete',complete=True)
        self.resolve()
        for p in self.players:self.act('travelComplete',session=p,complete=True)
        self.assertEqual(self.game.view(self.gm)['journey']['quarter'],0)
        v=self.act('travelComplete',complete=True)
        self.assertEqual((v['journey']['phase'],v['journey']['quarter']),('planning',1))
        self.assertFalse(v['journey']['plans']);self.assertFalse(v['journey']['completed'])

    @patch('campaign_rules.dice',side_effect=lambda n,sides=6:[6]*n)
    def test_last_player_finishes_once_and_stale_packet_cannot_finish_next_quarter(self,roll):
        self.plans(True);self.act('travelRoute',path=[dict(x=1,y=0)])
        self.act('travelReady',ready=True);self.resolve()
        count=roll.call_count
        self.act('travelComplete',complete=True)
        old=self.payload('travelComplete',complete=True)
        self.game.action(self.players[0],old)
        v=self.game.action(self.players[1],old)
        self.assertEqual(v['journey']['quarter'],1);self.assertEqual(roll.call_count,count)
        self.assertEqual(len([h for h in v['journey']['history'] if 'plans' in h]),1)
        with self.assertRaises(ValueError):self.game.action(self.players[1],old)

    @patch('campaign_rules.dice',side_effect=lambda n,sides=6:[6]*n)
    def test_invalid_route_commits_no_checks_then_corrected_route_executes(self,roll):
        self.plans(True);self.act('travelRoute',path=[dict(x=8,y=8)])
        v=self.act('travelReady',ready=True)
        self.assertEqual(v['journey']['phase'],'planning');self.assertTrue(v['journey']['blocker'])
        self.assertEqual(v['journey']['position'],dict(x=0,y=0));self.assertEqual(roll.call_count,0)
        self.act('travelRoute',path=[dict(x=1,y=0)])
        v=self.act('travelReady',ready=True)
        self.assertEqual(v['journey']['position'],dict(x=1,y=0));self.assertEqual(v['journey']['quarter'],0)
        with self.assertRaises(ValueError):self.act('travelReady',ready=True)

    def test_conflicting_draft_and_old_setup_generation_are_rejected(self):
        draft=self.payload('travelPlan',id='hero0',job='rest')
        self.game.action(self.players[0],draft)
        with self.assertRaises(ValueError):self.game.action(self.players[0],draft)
        old=self.payload('travelPlan',id='hero0',job='sleep')
        self.act('travelParty',party=['hero0'])
        self.act('travelRelocate',x=2,y=0,confirmed=True)
        with self.assertRaises(ValueError):self.game.action(self.players[0],old)

    @patch('campaign_rules.dice',side_effect=lambda n,sides=6:[6]*n)
    def test_changed_plan_requires_new_gm_declaration(self,_):
        self.act('travelPlan',session=self.players[0],id='hero0',job='rest')
        self.act('travelReady',ready=True)
        old_ready=self.payload('travelReady',ready=True)
        v=self.act('travelPlan',session=self.players[0],id='hero0',job='sleep')
        self.assertFalse(v['journey']['gmReady'])
        with self.assertRaises(ValueError):self.game.action(self.gm,old_ready)
        self.act('travelPlan',session=self.players[1],id='hero1',job='rest');self.act('travelPlan',id='npc',job='rest')
        self.assertEqual(self.game.view(self.gm)['journey']['phase'],'planning')

    @patch('campaign_rules.dice',side_effect=lambda n,sides=6:[6]*n)
    def test_disconnect_restart_and_spectator_cannot_remove_required_confirmation(self,_):
        other=self.game.login(dict(name='Spectator',code=self.auth['code'],key=self.auth['playerKey']))
        spectator=self.game.session(other['token'])
        self.plans();self.act('travelReady',ready=True);self.resolve()
        with self.assertRaises(PermissionError):self.act('travelComplete',session=spectator,complete=True)
        self.act('travelComplete',complete=True);self.act('travelComplete',session=self.players[0],complete=True)
        self.game.sessions.pop(self.auths[1]['token']);self.game.db.close()
        self.game=Game(self.db,reference_root=self.root/'assets')
        v=self.game.view(self.gm);self.assertEqual(v['journey']['quarter'],0)
        self.assertTrue(v['journey']['completed'][self.players[0]['owner']])
        auth=self.game.login(dict(name='Player 1',code=self.auth['code'],key=self.auth['playerKey'],resume=self.auths[1]['resume']))
        p=self.game.session(auth['token']);self.assertEqual(p['owner'],self.players[1]['owner'])
        v=self.act('travelComplete',session=p,complete=True);self.assertEqual(v['journey']['quarter'],1)

    @patch('campaign_rules.dice',side_effect=lambda n,sides=6:[6]*n)
    def test_pending_events_and_private_scouting_are_hidden_from_players(self,_):
        self.plans(True);self.act('travelRoute',path=[dict(x=1,y=0)]);self.act('travelReady',ready=True)
        public=self.game.view(self.players[0])['journey']
        self.assertFalse(public['pending']);self.assertGreater(public['pendingCount'],0)
        self.assertFalse(any(r['skill']=='scout' or r['character']!='hero0' for h in public['history'] for r in h.get('rolls',[])))
        self.resolve();self.assertNotIn('Private outcome',str(self.game.view(self.players[0])))

    @patch('campaign_rules.dice',side_effect=lambda n,sides=6:[6]*n)
    def test_night_keeps_day_until_daily_needs_and_confirmations_are_resolved(self,_):
        room=self.game.room(self.gm['room']);room['journey']['quarter']=3;self.game.save(room)
        self.plans();v=self.act('travelReady',ready=True)
        self.assertEqual((v['journey']['day'],v['journey']['quarter']),(1,3))
        self.assertTrue(any('потребности' in p['category'] for p in v['journey']['pending']))
        self.resolve()
        for p in self.players:self.act('travelComplete',session=p,complete=True)
        v=self.act('travelComplete',complete=True)
        self.assertEqual((v['journey']['day'],v['journey']['quarter']),(2,0))

    @patch('campaign_rules.dice',side_effect=lambda n,sides=6:[6]*n)
    def test_permissions_lock_plans_and_manual_advance_cannot_bypass_readiness(self,_):
        with self.assertRaises(ValueError):self.act('travelAdvance',path=[])
        with self.assertRaises(PermissionError):self.act('travelReady',session=self.players[0],ready=True)
        with self.assertRaises(PermissionError):self.act('travelPlan',session=self.players[0],id='hero1',job='rest')
        self.plans();self.act('travelReady',ready=True)
        with self.assertRaises(ValueError):self.act('travelPlan',session=self.players[0],id='hero0',job='sleep')
        with self.assertRaises(ValueError):self.game.action(self.gm,dict(action='assignCharacter',id='hero0',owner=self.gm['owner']))

    @patch('campaign_rules.dice',side_effect=lambda n,sides=6:[6]*n)
    def test_further_actions_invalidate_completion_and_new_events_require_acknowledgement(self,_):
        self.plans();self.act('travelReady',ready=True);self.resolve()
        old=self.payload('travelComplete',complete=True)
        self.act('travelComplete',session=self.players[0],complete=True)
        self.act('travelConditions',id='hero0',conditions=dict(hungry=True,thirsty=False,sleepy=False,cold=False))
        self.assertNotIn(self.players[0]['owner'],self.game.view(self.gm)['journey']['completed'])
        with self.assertRaises(ValueError):self.game.action(self.players[0],old)
        for p in self.players:self.act('travelComplete',session=p,complete=True)
        self.act('travelEvent',category='journey')
        self.assertFalse(self.game.view(self.gm)['journey']['completed'])
        self.resolve();self.act('travelComplete',complete=True)
        self.assertEqual(self.game.view(self.gm)['journey']['quarter'],0)

    @patch('campaign_rules.dice',side_effect=lambda n,sides=6:[6]*n)
    def test_ten_simultaneous_players_can_declare_and_complete_without_lost_updates(self,_):
        extra=[self.game.login(dict(name=f'Player {i}',code=self.auth['code'],key=self.auth['playerKey'])) for i in range(2,10)]
        auths=self.auths+extra;players=[self.game.session(a['token']) for a in auths]
        room=self.game.room(self.gm['room']);room['characters']=[self.hero(f'hero{i}',p['owner']) for i,p in enumerate(players)]
        self.game.save(room);self.act('travelParty',party=[f'hero{i}' for i in range(10)])
        self.act('travelReady',ready=True)
        requests=[(a['token'],self.payload('travelPlan',id=f'hero{i}',job='rest')) for i,a in enumerate(auths)]
        http=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.game))
        thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        def post(pair):
            token,data=pair
            req=Request(f'http://127.0.0.1:{http.server_port}/api/action',data=json.dumps(data).encode(),headers={'Authorization':token,'Content-Type':'application/json'})
            with urlopen(req,timeout=8) as response:return json.load(response)
        try:
            with ThreadPoolExecutor(max_workers=10) as pool:results=list(pool.map(post,requests))
            self.assertEqual(self.game.view(self.gm)['journey']['phase'],'resolving')
            self.resolve();self.act('travelComplete',complete=True)
            requests=[(a['token'],self.payload('travelComplete',participant=players[i],complete=True)) for i,a in enumerate(auths)]
            with ThreadPoolExecutor(max_workers=10) as pool:results=list(pool.map(post,requests))
            t=self.game.view(self.gm)['journey'];self.assertEqual(t['quarter'],1)
            self.assertEqual(len([h for h in t['history'] if 'plans' in h]),1)
        finally:http.shutdown();http.server_close();thread.join()


if __name__=='__main__':unittest.main()
