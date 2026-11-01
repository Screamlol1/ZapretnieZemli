import sys
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]))
import campaign_rules as campaign
import expedition

class ExpeditionTests(unittest.TestCase):
    def setUp(self):
        self.gm={'role':'gm','owner':'gm'};self.player={'role':'player','owner':'owner'}
        self.c={'id':'hero','owner':'owner','name':'Охотник','kind':'pc','hidden':False,'sheet':{'attrs':dict(str=3,agi=3,wit=3,emp=3),'skills':dict(shoot=2,survive=2,craft=2,scout=1,endure=1),'talents':{},'kin':'human'},'runtime':{'current':dict(str=3,agi=3,wit=3,emp=3),'wp':3,'resources':{'arrows':12}}}
        self.bow={'id':'bow','name':'Лук','catalogId':'shortbow','combatProfile':'bow','quantity':1,'bonus':2,'wear':0,'version':1,'location':{'kind':'character','id':'hero'},'weight':1}
        self.room={'id':'test','characters':[self.c],'items':[self.bow],'maps':{'world':{}},'log':[],'diceRolls':[],'worldLayout':'legacy','identities':{'a':self.gm}}
        self.t=campaign.state(self.room);self.t.update(party=['hero'],encounterDay=1)
    def act(self,op,s=None,**data):
        return expedition.apply(self.room,s or self.gm,dict(action='expedition',op=op,revision=self.t['revision'],**data))
    def hunt(self,prey=3,hits=2):
        with patch('expedition.die',return_value=prey):expedition.start_hunt(self.room,self.c,{'hits':hits})
        return self.room['hunts'][-1]
    def shot(self,h,method='weapon'):
        self.act('huntRoll',self.player,hunt=h['id'],huntRevision=h['revision'],choice=0,method=method,item='bow')
    def accept(self,s=None):
        p=self.room['expeditionCheck'];self.act('accept',s or self.player,roll=p['id'],diceEvent=p['diceEvent'])
    def boat(self):
        self.act('vesselCreate',name='Тихая вода',kind='Лодка',capacity=4,cargoLimit=30)
        return self.room['vessels'][0]
    def board(self,v):self.act('vesselBoard',vessel=v['id'],vesselRevision=v['revision'],aboard=True)
    def hold(self):
        campaign.stronghold(self.room,dict(action='holdCreate',name='Дом',x=0,y=0,confirmed=True));h=self.room['strongholds'][0]
        h['stock'].update(wood=1000,stone=1000,iron=1000,copper=1000,flour=40)
        h['hirelings']=[dict(id='baker',name='Пекарь',job='Пекарь',wage=10,paidThrough=10),dict(id='worker',name='Рабочий',job='Строитель',wage=12,paidThrough=10)]
        return h
    def test_hunt_rerolls_spend_extra_successes_and_keep_master_choice(self):
        self.c['sheet']['talents']['masterhunt']=3;h=self.hunt()
        self.assertEqual(h['choices'],[3,3])
        with patch('expedition.die',return_value=6):self.act('huntReroll',self.player,hunt=h['id'],huntRevision=0,slot=0)
        self.assertEqual(h['choices'],[6,3]);self.assertEqual(h['rerolls'],0)
        with self.assertRaises(ValueError):self.act('huntReroll',self.player,hunt=h['id'],huntRevision=1,slot=0)
    def test_hunt_awards_once_only_after_accept_and_consumes_arrow_die(self):
        h=self.hunt(3)
        with patch('expedition.die',return_value=1),patch('campaign_rules.dice',side_effect=lambda n,sides=6:[6]*n):self.shot(h)
        self.assertEqual(self.c['runtime']['resources']['arrows'],10)
        self.assertNotIn('finds',self.t);p=deepcopy(self.room['expeditionCheck']);self.accept()
        self.assertEqual(self.t['finds']['meat'],2);self.assertEqual(self.t['finds']['pelts'],1)
        self.assertFalse(any(p.get('hunt') for p in self.t['pending']))
        with self.assertRaises(ValueError):self.act('accept',self.player,roll=p['id'],diceEvent=p['diceEvent'])
        self.assertEqual(self.t['finds']['meat'],2)
    def test_boar_failure_requires_encounter_and_disallows_trap(self):
        h=self.hunt(5)
        with self.assertRaises(ValueError):self.shot(h,'trap')
        with patch('expedition.die',return_value=6),patch('campaign_rules.dice',side_effect=lambda n,sides=6:[2]*n):self.shot(h)
        self.accept();self.assertTrue(any(p.get('huntBoar')=='hero' for p in self.t['pending']))
    def test_hunt_private_owner_permissions_and_stale_revision(self):
        h=self.hunt();before=deepcopy(self.room)
        with self.assertRaises(PermissionError):self.act('huntAbandon',{'role':'player','owner':'other'},hunt=h['id'],huntRevision=0)
        self.assertEqual(before,self.room)
        self.c['hidden']=True;view=deepcopy(self.room);expedition.project(view,self.player);self.assertEqual(view['hunts'],[])
        with self.assertRaises(ValueError):self.act('huntAbandon',hunt=h['id'],huntRevision=9)
    def test_push_keeps_pending_and_applies_damage_wear_willpower(self):
        h=self.hunt()
        with patch('expedition.die',return_value=6),patch('campaign_rules.dice',side_effect=lambda n,sides=6:[2]*n):self.shot(h)
        p=self.room['expeditionCheck'];old=p['diceEvent']
        with patch('expedition.die',return_value=1):self.act('push',self.player,roll=p['id'],diceEvent=old)
        self.assertIn('expeditionCheck',self.room);self.assertEqual(self.c['runtime']['current']['agi'],0);self.assertEqual(self.c['runtime']['wp'],6);self.assertEqual(self.bow['wear'],2)
        with self.assertRaises(ValueError):self.act('accept',self.player,roll=p['id'],diceEvent=old)
    def test_dwarf_repeat_uses_willpower_and_cannot_replay_old_event(self):
        self.c['sheet']['kin']='dwarf';h=self.hunt()
        with patch('expedition.die',return_value=6),patch('campaign_rules.dice',side_effect=lambda n,sides=6:[2]*n):self.shot(h)
        p=self.room['expeditionCheck']
        with patch('expedition.die',return_value=3):self.act('push',self.player,roll=p['id'],diceEvent=p['diceEvent'])
        self.assertTrue(p['roll']['pushAvailable'])
        with self.assertRaises(ValueError):self.act('push',self.player,roll=p['id'],diceEvent=p['diceEvent'])
        with patch('expedition.die',return_value=6):self.act('push',self.player,roll=p['id'],diceEvent=p['diceEvent'],kinRepeat=True,kinAttempt=0)
        self.assertEqual(self.c['runtime']['wp'],2);self.assertEqual(p['roll']['kinPushes'],1)
    def test_magical_insomnia_blocks_sleep_and_preserves_sleepiness(self):
        self.c['runtime'].update(magicEffects=[{'kind':'insomnia','until':30}],conditions={'sleepy':True})
        with self.assertRaisesRegex(ValueError,'бессонница'):campaign.apply(self.room,self.gm,dict(action='travelPlan',revision=self.t['revision'],id='hero',job='sleep',role='none'))
        self.t['history']=[{'plans':{'hero':{'job':'sleep'}}}]
        campaign.apply(self.room,self.gm,dict(action='travelRecover',revision=self.t['revision'],id='hero',confirmed=True))
        self.assertTrue(self.c['runtime']['conditions']['sleepy'])
    def test_boat_failure_enters_water_and_navigation_mishap_returns_to_origin(self):
        v=self.boat();self.board(v);self.t['plans']['hero']=dict(job='hike',role='lead',gear=0,modifier=0,darkvision=True,equipped=True)
        self.room['maps']['world']['1,0']={'terrain':'water'}
        with patch('campaign_rules.dice',side_effect=lambda n,sides=6:[1]*n):campaign.advance(self.room,{'path':[dict(x=1,y=0)]},True)
        self.assertEqual(self.t['position'],dict(x=1,y=0));self.assertEqual(v['position'],self.t['position'])
        p=next(p for p in self.t['pending'] if p.get('vessel'))
        self.act('vesselMishap',vessel=v['id'],vesselRevision=v['revision'],pending=p['id'],note='Вернулись к знакомому берегу.')
        self.assertEqual(self.t['position'],dict(x=0,y=0));self.assertEqual(v['position'],dict(x=0,y=0))
    def test_boat_overboard_starts_real_water_exposure(self):
        v=self.boat();self.board(v)
        with patch('expedition.die',return_value=5):p=expedition.sea_mishap(self.room,v,self.c)
        self.act('vesselMishap',vessel=v['id'],vesselRevision=v['revision'],pending=p['id'],character='hero',metalArmor=True,note='Смыло волной.')
        self.assertEqual(self.c['runtime']['waterExposure']['phase'],'afloat');self.assertTrue(self.c['runtime']['waterExposure']['metalArmor'])
    def test_boat_cargo_capacity_permissions_and_repair(self):
        with self.assertRaises(PermissionError):self.act('vesselCreate',self.player,name='Чужое',kind='Лодка',capacity=1,cargoLimit=1)
        v=self.boat();v['cargo']=31
        with self.assertRaises(ValueError):self.board(v)
        v['cargo']=0;self.board(v);v['condition']='grounded'
        with self.assertRaises(ValueError):self.act('vesselRepair',vessel=v['id'],vesselRevision=v['revision'],character='hero')
        with patch('campaign_rules.dice',side_effect=lambda n,sides=6:[6]*n):self.act('vesselRepair',vessel=v['id'],vesselRevision=v['revision'],character='hero',shore=True)
        self.accept();self.assertEqual(v['condition'],'sound')
    def test_moving_boat_allows_fisher_and_sailor_artifact(self):
        v=self.boat();self.board(v);passenger=deepcopy(self.c);passenger.update(id='fisher',name='Рыбак');passenger['sheet']['talents']={'fisher':3};self.room['characters'].append(passenger);self.t['party'].append('fisher');self.c['sheet']['talents']['sailor']=3
        self.t['plans']={'hero':dict(job='hike',role='lead',gear=0,modifier=0,darkvision=True,equipped=True),'fisher':dict(job='fish',role='none',gear=0,modifier=0,darkvision=True,equipped=True)}
        self.room['maps']['world']['1,0']={'terrain':'water'}
        with patch('campaign_rules.dice',side_effect=lambda n,sides=6:[6]*n):campaign.advance(self.room,{'path':[dict(x=1,y=0)]},True)
        rolls=self.t['history'][-1]['rolls'];self.assertTrue(any(r['artifacts'] for r in rolls));self.assertGreater(self.t['finds']['fish'],0)
    def test_stronghold_assignment_production_and_daily_overtime(self):
        h=self.hold();h['functions']=['bakery'];self.act('holdAssign',hold=h['id'],worker='hire:baker',task='produce:bakery',qualified=True)
        self.act('holdShift',hold=h['id'],worker='hire:baker',amount=4);self.assertEqual(h['stock']['food'],4)
        with self.assertRaises(ValueError):self.act('holdShift',hold=h['id'],worker='hire:baker',amount=4)
        self.t['quarter']=1;self.act('holdShift',hold=h['id'],worker='hire:baker',amount=4)
        self.t['quarter']=2
        with self.assertRaises(ValueError):self.act('holdShift',hold=h['id'],worker='hire:baker',amount=4)
        self.act('holdShift',hold=h['id'],worker='hire:baker',amount=4,overtime=True);self.assertEqual(h['stock']['copper'],990);self.assertEqual(h['stock']['food'],12)
        self.t['quarter']=3
        with self.assertRaises(ValueError):self.act('holdShift',hold=h['id'],worker='hire:baker',amount=4,overtime=True)
    def test_stronghold_project_finishes_and_production_missing_stock_blocks(self):
        h=self.hold();campaign.stronghold(self.room,dict(action='holdBuild',hold=h['id'],function='fireplace',confirmed=True));p=h['projects'][0]
        self.act('holdAssign',hold=h['id'],worker='hire:worker',task='project:'+p['id'],qualified=True)
        self.act('holdShift',hold=h['id'],worker='hire:worker');self.t['quarter']=1;self.act('holdShift',hold=h['id'],worker='hire:worker')
        self.assertIn('fireplace',h['functions']);self.assertEqual(h['projects'],[]);self.assertEqual(h['assignments'],{})
        h['functions'].append('mill');self.act('holdAssign',hold=h['id'],worker='hire:baker',task='produce:mill',qualified=True)
        with self.assertRaises(ValueError):self.act('holdShift',hold=h['id'],worker='hire:baker',amount=12)
        self.assertEqual(h['stock']['flour'],40)
    def test_garden_weekly_seasonal_and_wages_gates(self):
        h=self.hold();h['functions']=['garden'];self.act('holdAssign',hold=h['id'],worker='hire:baker',task='produce:garden',qualified=True)
        self.act('holdShift',hold=h['id'],worker='hire:baker');self.assertEqual(h['stock']['vegetables'],10)
        self.t['day']=2
        with self.assertRaises(ValueError):self.act('holdShift',hold=h['id'],worker='hire:baker')
        self.t['day']=8;self.act('holdShift',hold=h['id'],worker='hire:baker');self.assertEqual(h['stock']['vegetables'],20)
        self.t['day']=15
        with self.assertRaises(ValueError):self.act('holdShift',hold=h['id'],worker='hire:baker')
    def test_layout_collisions_and_hidden_hunt_check_projection(self):
        h=self.hold();h['functions']=['fireplace','garden'];self.act('holdLayout',hold=h['id'],function='garden',x=1,y=1)
        with self.assertRaises(ValueError):self.act('holdLayout',hold=h['id'],function='fireplace',x=1,y=1)
        self.room['expeditionCheck']={'actor':'hero','private':True,'roll':{'secret':1}};view=deepcopy(self.room);expedition.project(view,self.player);self.assertEqual(view['expeditionCheck'],{'waiting':True,'private':True})

if __name__=='__main__':unittest.main()
