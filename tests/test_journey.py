import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]))
from server import Game
from campaign_rules import state, adjacent, MATERIALS

class JourneyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.game=Game(Path(self.tmp.name)/'test.sqlite',reference_root=Path(self.tmp.name)/'local-assets')
        self.login=self.game.login({'name':'Мастер'},True);self.gm=self.game.session(self.login['token'])
        p=self.game.login({'name':'Игрок','code':self.login['code'],'key':self.login['playerKey']});self.player=self.game.session(p['token'])
        room=self.game.room(self.gm['room']);room['worldLayout']='legacy';state(room)['automatic']=False
        room['characters']=[dict(id='hero',name='Герой',kind='pc',owner=self.player['owner'],hidden=False,sheet=dict(kin='human',attrs=dict(str=4,agi=3,wit=3,emp=2),skills=dict(survive=2,scout=1,endure=2,craft=1)),runtime=dict(current=dict(str=4,agi=3,wit=3,emp=2),wp=0,resources=dict(food=6,water=8)))]
        self.game.save(room)
        self.act('travelSetup',party=['hero'],x=0,y=0,season='spring')
    def tearDown(self):self.game.db.close();self.tmp.cleanup()
    def act(self,action,session=None,**data):
        t=state(self.game.room(self.gm['room']))
        return self.game.action(session or self.gm,dict(action=action,revision=t['revision'],**data))
    def plan(self,job='hike',role='lead',**data):return self.act('travelPlan',id='hero',job=job,role=role,**data)
    def clear(self):
        for p in list(self.game.view(self.gm)['journey']['pending']):self.act('travelResolve',id=p['id'],note='Решено.',reveal=False)
    def stock(self,**kw):return {k:kw.get(k,0) for k in MATERIALS}
    def hold(self):return self.act('holdCreate',name='Дом',x=0,y=0,confirmed=True)['strongholds'][0]
    @patch('campaign_rules.dice',side_effect=lambda n,sides=6:[6]*n)
    def test_regional_journey_requires_marked_terrain_and_accepts_column_neighbors(self,_):
        room=self.game.room(self.gm['room']);room['worldLayout']='ravenland';self.game.save(room)
        self.plan()
        with self.assertRaisesRegex(ValueError,'Сначала'):self.act('travelAdvance',path=[dict(x=1,y=0)])
        self.assertEqual(self.game.view(self.gm)['journey']['position'],dict(x=0,y=0))
        self.game.action(self.gm,dict(action='paint',map='world',x=1,y=0,terrain='plain',hidden=False))
        self.game.action(self.gm,dict(action='paint',map='world',x=1,y=1,terrain='plain',hidden=False))
        v=self.act('travelAdvance',path=[dict(x=1,y=0),dict(x=1,y=1)])
        self.assertEqual(v['journey']['position'],dict(x=1,y=1))
        self.assertIn('1,1',v['journey']['visited'])

    def test_hex_adjacency(self):
        p=dict(x=3,y=1)
        self.assertTrue(adjacent(p,dict(x=4,y=0)));self.assertTrue(adjacent(p,dict(x=4,y=2)))
        self.assertFalse(adjacent(p,dict(x=2,y=2)));self.assertFalse(adjacent(p,p))

    @patch('campaign_rules.dice',side_effect=lambda n,sides=6:[6]*n)
    def test_conditions_limit_recovery_and_sleep_clears_sleepiness(self,_):
        flags=dict(hungry=True,thirsty=False,sleepy=True,cold=False)
        with self.assertRaises(PermissionError):self.act('travelConditions',session=self.player,id='hero',conditions=flags)
        with self.assertRaises(ValueError):self.act('travelConditions',id='hero',conditions={'hungry':1})
        for flags,expected in [
            (dict(hungry=True,thirsty=False,sleepy=True,cold=False),dict(str=1,agi=3,wit=1,emp=2)),
            (dict(hungry=False,thirsty=False,sleepy=False,cold=True),dict(str=1,agi=3,wit=1,emp=2)),
            (dict(hungry=False,thirsty=True,sleepy=False,cold=False),dict(str=1,agi=1,wit=1,emp=1))]:
            self.clear();self.act('travelConditions',id='hero',conditions=flags)
            room=self.game.room(self.gm['room']);room['characters'][0]['runtime']['current']=dict(str=1,agi=1,wit=1,emp=1);self.game.save(room)
            self.plan('rest','none');self.act('travelAdvance',path=[])
            v=self.act('travelRecover',id='hero',confirmed=True)
            self.assertEqual(v['characters'][0]['runtime']['current'],expected)
        self.clear();self.act('travelConditions',id='hero',conditions=dict(hungry=False,thirsty=False,sleepy=True,cold=False))
        self.plan('sleep','none');self.act('travelAdvance',path=[])
        v=self.act('travelRecover',id='hero',confirmed=True)
        self.assertFalse(v['characters'][0]['runtime']['conditions']['sleepy'])
        self.assertEqual(v['characters'][0]['runtime']['current'],v['characters'][0]['sheet']['attrs'])

    @patch('campaign_rules.dice',side_effect=lambda n,sides=6:[1]*n)
    def test_last_ration_removes_condition_and_failed_consumption_does_not(self,_):
        self.act('travelConditions',id='hero',conditions=dict(hungry=True,thirsty=True,sleepy=False,cold=False))
        v=self.act('travelConsume',id='hero',resource='food',session=self.player)
        self.assertFalse(v['characters'][0]['runtime']['conditions']['hungry'])
        self.assertTrue(v['characters'][0]['runtime']['conditions']['thirsty'])
        self.assertEqual(v['characters'][0]['runtime']['resources']['food'],0)
        self.act('travelSupplies',id='hero',resources=dict(food=0,water=0))
        with self.assertRaises(ValueError):self.act('travelConsume',id='hero',resource='water')
        self.assertTrue(self.game.view(self.gm)['characters'][0]['runtime']['conditions']['thirsty'])
        self.act('travelFinds',kind='meat',amount=1,confirmed=True)
        room=self.game.room(self.gm['room']);room['characters'][0]['runtime']['conditions']['hungry']=True;room['characters'][0]['runtime']['consumed']={};self.game.save(room)
        v=self.act('travelConsume',id='hero',resource='food',source='meat')
        self.assertFalse(v['characters'][0]['runtime']['conditions']['hungry'])
    @patch('campaign_rules.dice',side_effect=lambda n,sides=6:[6]*n)
    def test_travel_unvisited_and_return(self,_):
        self.plan();v=self.act('travelAdvance',path=[dict(x=1,y=0),dict(x=2,y=0)])
        t=v['journey'];self.assertEqual(t['position'],dict(x=2,y=0));self.assertEqual(t['quarter'],1)
        self.assertEqual(sum(r['skill']=='survive' for r in t['history'][-1]['rolls']),2)
        self.clear();self.plan();v=self.act('travelAdvance',path=[dict(x=1,y=0),dict(x=0,y=0)])
        self.assertEqual(sum(r['skill']=='survive' for r in v['journey']['history'][-1]['rolls']),0)
    def test_limits_and_blocked_terrain_are_atomic(self):
        self.plan();self.game.action(self.gm,dict(action='paint',map='world',x=1,y=0,terrain='mountain'))
        with self.assertRaises(ValueError):self.act('travelAdvance',path=[dict(x=1,y=0),dict(x=2,y=0)])
        self.assertEqual(self.game.view(self.gm)['journey']['quarter'],0)
        self.game.action(self.gm,dict(action='paint',map='world',x=1,y=0,terrain='highmountain'))
        with self.assertRaises(ValueError):self.act('travelAdvance',path=[dict(x=1,y=0)])
    @patch('campaign_rules.dice',side_effect=lambda n,sides=6:[3]*n)
    def test_forced_march_failure_stops_party_and_hurts_agility(self,_):
        r=self.game.room(self.gm['room']);r['journey']['hikes']=2;self.game.save(r);self.plan()
        v=self.act('travelAdvance',path=[dict(x=1,y=0)])
        self.assertEqual(v['journey']['position'],dict(x=0,y=0));self.assertEqual(v['characters'][0]['runtime']['current']['agi'],2)
        self.assertTrue(any('марш' in p['category'] for p in v['journey']['pending']))
    @patch('campaign_rules.dice',side_effect=lambda n,sides=6:[3]*n)
    def test_darkness_and_hidden_mishaps(self,_):
        r=self.game.room(self.gm['room']);r['journey']['season']='winter';self.game.save(r);self.plan()
        v=self.act('travelAdvance',path=[dict(x=1,y=0)]);self.assertEqual(v['characters'][0]['runtime']['current']['str'],3)
        self.assertEqual(v['journey']['history'][-1]['rolls'][1]['modifier'],-2)
        public=self.game.view(self.player)['journey'];self.assertEqual(public['pending'],[]);self.assertGreater(public['pendingCount'],0)
        self.clear();self.plan('rest','none');private=self.act('travelEvent')['journey']['pending'][0]
        secret=private['note'];self.act('travelResolve',id=private['id'],note=secret,reveal=False)
        self.assertNotIn(secret,str(self.game.view(self.player)))
    def test_permissions_roles_and_stale_commands(self):
        self.act('travelPlan',session=self.player,id='hero',job='hike',role='lead',modifier=10,gear=10,equipped=True)
        p=self.game.view(self.gm)['journey']['plans']['hero'];self.assertEqual(p['modifier'],0);self.assertFalse(p['equipped'])
        for action in ('travelAdvance','travelEvent','holdCreate','holdStock','travelSupplies'):
            with self.assertRaises(PermissionError):self.act(action,session=self.player)
        with self.assertRaises(ValueError):self.game.action(self.gm,dict(action='travelSession',revision=-1))
        with self.assertRaises(ValueError):self.act('travelAdvance',path=[None])
    def test_assigned_npc_does_not_disclose_gm_notes(self):
        r=self.game.room(self.gm['room']);r['characters'][0]['kind']='npc';r['characters'][0]['sheet']['notes']='Тайный заговор';self.game.save(r)
        self.assertNotIn('Тайный заговор',str(self.game.view(self.player)))
    @patch('campaign_rules.dice',return_value=[1])
    def test_consuming_last_food_portion_once_per_day(self,_):
        v=self.act('travelConsume',session=self.player,id='hero',resource='food')
        self.assertEqual(v['characters'][0]['runtime']['resources']['food'],0)
        self.assertEqual(v['characters'][0]['runtime']['consumed']['food'],1)
        with self.assertRaises(ValueError):self.act('travelConsume',session=self.player,id='hero',resource='food')
    @patch('campaign_rules.dice',side_effect=lambda n,sides=6:[6]*n)
    def test_forage_water_refills_party_and_season_modifier(self,_):
        self.plan('forageWater','none');v=self.act('travelAdvance',path=[])
        self.assertEqual(v['characters'][0]['runtime']['resources']['water'],12)
        self.assertEqual(v['journey']['history'][-1]['rolls'][0]['modifier'],-2)
    def test_building_requirements_costs_and_work(self):
        h=self.hold();self.act('holdStock',hold=h['id'],stock=self.stock(stone=500,iron=60))
        with self.assertRaises(ValueError):self.act('holdBuild',hold=h['id'],function='forge',confirmed=True)
        v=self.act('holdBuild',hold=h['id'],function='fireplace',confirmed=True);h=v['strongholds'][0];self.assertEqual(h['stock']['stone'],480)
        p=h['projects'][0];self.act('holdWork',hold=h['id'],project=p['id'],confirmed=True)
        with self.assertRaises(ValueError):self.act('holdWork',hold=h['id'],project=p['id'],confirmed=True)
        r=self.game.room(self.gm['room']);r['journey']['quarter']=1;self.game.save(r)
        v=self.act('holdWork',hold=h['id'],project=p['id'],confirmed=True);self.assertIn('fireplace',v['strongholds'][0]['functions'])
        v=self.act('holdBuild',hold=h['id'],function='forge',confirmed=True);self.assertEqual(v['strongholds'][0]['stock']['stone'],80)
    def test_hireling_pay_and_production_are_limited(self):
        h=self.hold();self.act('holdStock',hold=h['id'],stock=self.stock(copper=100,flour=20))
        v=self.act('holdHire',hold=h['id'],name='Пекарь',job='пекарь',wage=5,confirmed=True);p=v['strongholds'][0]['hirelings'][0]
        v=self.act('holdPay',hold=h['id'],person=p['id'],days=7);self.assertEqual(v['strongholds'][0]['stock']['copper'],65);self.assertEqual(v['strongholds'][0]['hirelings'][0]['paidThrough'],7)
        r=self.game.room(self.gm['room']);r['strongholds'][0]['functions']=['bakery'];self.game.save(r)
        v=self.act('holdProduce',hold=h['id'],function='bakery',amount=12,confirmed=True)
        self.assertEqual(v['strongholds'][0]['stock']['food'],12)
        with self.assertRaises(ValueError):self.act('holdProduce',hold=h['id'],function='bakery',amount=1,confirmed=True)
    def test_fresh_food_expires_and_does_not_refresh_old_batches(self):
        self.act('travelFinds',kind='meat',amount=2,confirmed=True)
        r=self.game.room(self.gm['room']);r['journey']['quarter']=3;self.game.save(r)
        self.act('travelFinds',kind='fish',amount=1,confirmed=True)
        r=self.game.room(self.gm['room']);r['journey'].update(day=2,quarter=0);self.game.save(r)
        with self.assertRaises(ValueError):self.act('travelConsume',id='hero',resource='food',source='meat',session=self.player)
        v=self.act('travelConsume',id='hero',resource='food',source='fish',session=self.player)
        self.assertEqual(v['journey']['finds']['fish'],0);self.assertEqual(v['characters'][0]['runtime']['resources']['food'],6)
    @patch('campaign_rules.dice',side_effect=lambda n,sides=6:[8 if sides==8 else 3]*n)
    def test_pathfinder_d8_and_modifier_does_not_leak_into_scouting(self,_):
        r=self.game.room(self.gm['room']);r['characters'][0]['sheet']['talents']={'pathfinder':3};r['journey']['season']='winter';self.game.save(r)
        self.plan(modifier=2);v=self.act('travelAdvance',path=[dict(x=1,y=0)])
        scout,survive=v['journey']['history'][-1]['rolls'][:2]
        self.assertEqual(scout['modifier'],0);self.assertEqual(survive['modifier'],1);self.assertEqual(survive['hits'],2);self.assertEqual(survive['artifact'],8)
    @patch('campaign_rules.dice',side_effect=lambda n,sides=6:[8 if sides==8 else 6]*n)
    def test_negative_skill_cancels_artifact_successes_before_clamping(self,_):
        r=self.game.room(self.gm['room']);r['characters'][0]['sheet']['talents']={'pathfinder':3};self.game.save(r)
        self.plan(modifier=-8);v=self.act('travelAdvance',path=[dict(x=1,y=0)])
        roll=v['journey']['history'][-1]['rolls'][0]
        self.assertEqual(roll['netHits'],-2);self.assertEqual(roll['hits'],0)
    @patch('campaign_rules.dice',side_effect=lambda n,sides=6:[6]*n)
    def test_reputation_pool_uses_highest_die_and_events_are_private(self,_):
        h=self.hold();v=self.act('holdRoll',hold=h['id'],category='guarded',reputation=3,modifier=1)
        p=v['journey']['pending'][0];self.assertEqual(p['roll'],66);self.assertIn('[6, 6, 6, 6]',p['note']);self.assertEqual(self.game.view(self.player)['journey']['pending'],[])
    @patch('campaign_rules.dice',side_effect=lambda n,sides=6:[6]*n)
    def test_day_at_home_grants_wp_once_session_and_survives_restart(self,_):
        self.hold()
        for _ in range(4):self.plan('sleep','none');self.act('travelAdvance',path=[]);self.clear()
        self.assertEqual(self.game.view(self.gm)['characters'][0]['runtime']['wp'],1)
        self.plan('sleep','none');self.act('travelAdvance',path=[]);self.clear()
        self.assertEqual(self.game.view(self.gm)['characters'][0]['runtime']['wp'],1)
        self.act('travelSession');self.plan('sleep','none');self.act('travelAdvance',path=[])
        self.assertEqual(self.game.view(self.gm)['characters'][0]['runtime']['wp'],2)
        new=Game(Path(self.tmp.name)/'test.sqlite',reference_root=Path(self.tmp.name)/'local-assets')
        try:self.assertEqual(new.room(self.gm['room'])['journey']['day'],2)
        finally:new.db.close()
    def test_resting_in_stronghold_has_no_wilderness_mishap(self):
        self.hold();self.plan('sleep','none');v=self.act('travelAdvance',path=[])
        self.assertEqual(v['journey']['pending'],[])

if __name__=='__main__':unittest.main()
