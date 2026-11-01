import unittest
from unittest.mock import patch
import test_server as support

class UnifiedAbilityTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown
    make_pc=support.CampaignTests.make_pc
    def hero(self):return next(c for c in self.game.view(self.gs)['characters'] if c['id']==self.cid)
    def setup_hero(self,kin='human'):
        self.cid=self.make_pc()['id'];room=self.game.room(self.gs['room']);c=next(c for c in room['characters'] if c['id']==self.cid)
        c['sheet'].update(kin=kin,pride='Я выживаю в любых испытаниях');c['runtime']['wp']=3;self.game.save(room)
    def power(self,op,s=None,**data):return self.game.action(s or self.ps,dict(action='characterPride',op=op,character=self.cid,**data))
    def use_pride(self,p,value=12):
        self.power('request',roll=p['id'],note='Мой опыт помогает выстоять');request=self.hero()['runtime']['prideRequest'];self.assertTrue(request['current'])
        self.power('approve',self.gs,roll=p['id'],request=request['id'])
        with patch('pride.die',return_value=value):return self.power('roll',roll=p['id'],request=request['id'])
    def cold(self,kin='human'):
        self.setup_hero(kin);v=self.game.action(self.gs,dict(action='coldExposure',op='configure',character=self.cid,intervalHours=1,note='Стужа'))
        e=self.hero()['runtime']['coldExposure']
        with patch('cold_exposure.die',return_value=2):return self.game.action(self.ps,dict(action='coldExposure',op='roll',character=self.cid,exposure=e['id']))['coldCheck']
    def test_pride_after_cold_failure_and_push_resolves_only_after_accept(self):
        p=self.cold();self.assertTrue(p['roll']['prideAvailable'])
        with patch('cold_exposure.die',return_value=2):v=self.game.action(self.ps,dict(action='coldExposure',op='push',character=self.cid,roll=p['id']))
        v=self.use_pride(v['coldCheck']);self.assertEqual(v['coldCheck']['roll']['hits'],4);self.assertFalse(v['coldCheck']['roll']['pushAvailable'])
        self.game.action(self.ps,dict(action='coldExposure',op='accept',character=self.cid,roll=p['id']))
        self.assertFalse(self.hero()['runtime'].get('conditions',{}).get('cold'))
    def test_dwarf_repeat_cost_nonce_and_preserved_roll(self):
        p=self.cold('dwarf');cmd=dict(action='coldExposure',op='push',character=self.cid,roll=p['id'])
        with patch('cold_exposure.die',return_value=2):self.game.action(self.ps,cmd)
        with self.assertRaises(ValueError):self.game.action(self.ps,cmd)
        repeated=dict(cmd,kinRepeat=True,kinAttempt=0)
        with patch('cold_exposure.die',return_value=2):v=self.game.action(self.ps,repeated)
        self.assertEqual(self.hero()['runtime']['wp'],2);self.assertEqual(v['coldCheck']['roll']['kinPushes'],1)
        with self.assertRaises(ValueError):self.game.action(self.ps,repeated)
        self.game.db.close();self.game=support.Game(self.path,reference_root=self.path.parent/'local-assets')
        self.assertEqual(self.game.view(self.gs)['coldCheck']['roll']['kinPushes'],1)

    def test_accepting_result_cancels_unresolved_pride_request_without_spending(self):
        p=self.cold();self.power('request',roll=p['id'],note='Прошу применить опыт')
        self.game.action(self.ps,dict(action='coldExposure',op='accept',character=self.cid,roll=p['id']))
        self.assertNotIn('prideRequest',self.hero()['runtime']);self.assertNotIn('pride',self.hero()['runtime'])
    def test_human_approved_substitution_in_water_uses_new_attribute_and_skill(self):
        self.setup_hero();self.game.action(self.ps,dict(action='characterAbility',op='requestAdaptation',character=self.cid,skill='endure',replacement='survive',note='Использую знание течения'))
        token=self.hero()['runtime']['adaptation']['id'];self.game.action(self.gs,dict(action='characterAbility',op='approveAdaptation',character=self.cid,request=token))
        self.game.action(self.gs,dict(action='waterExposure',op='configure',character=self.cid,phase='afloat',metalArmor=False,note='Река',modifier=0))
        e=self.hero()['runtime']['waterExposure']
        with patch('water_exposure.die',return_value=2):v=self.game.action(self.ps,dict(action='waterExposure',op='roll',character=self.cid,exposure=e['id'],adaptation=token))
        self.assertEqual(v['waterCheck']['roll']['attribute'],'wit');self.assertEqual(v['waterCheck']['roll']['skill'],'survive');self.assertEqual(self.hero()['runtime']['wp'],2)
        v=self.use_pride(v['waterCheck']);self.assertEqual(v['waterCheck']['roll']['hits'],4)
    def test_affliction_pride_compares_against_potency_not_only_zero(self):
        self.setup_hero();self.game.action(self.gs,dict(action='affliction',op='configure',character=self.cid,kind='disease',potency=3,note='Заразный источник'))
        a=self.hero()['runtime']['afflictions'][0];c=self.hero();n=c['runtime']['current']['str']+c['sheet']['skills'].get('endure',0)
        with patch('afflictions.die',side_effect=[6]+[2]*(n-1)+[6,6,6]):v=self.game.action(self.ps,dict(action='affliction',op='roll',character=self.cid,affliction=a['id']))
        p=v['afflictionCheck'];self.assertEqual(p['roll']['hits'],1);self.assertTrue(p['roll']['prideAvailable'])
        v=self.use_pride(p,8);self.assertEqual(v['afflictionCheck']['roll']['hits'],3);self.assertFalse(self.hero()['runtime']['pride']['lost'])
        self.game.action(self.ps,dict(action='affliction',op='accept',character=self.cid,roll=p['id']));self.assertEqual(self.hero()['runtime']['afflictions'][0]['phase'],'resolved')

    def test_journey_replay_keeps_pride_result_and_once_per_session(self):
        import journey_risk
        from campaign_rules import state
        self.setup_hero();room=self.game.room(self.gs['room']);t=state(room)
        t.update(party=[self.cid],plans={self.cid:dict(job='forageFood',role='none',modifier=0,gear=0)},route=[],season='summer',interactiveRisk=True)
        with patch('campaign_rules.secrets.randbelow',return_value=1):journey_risk.resolve(room)
        self.game.save(room);p=self.game.view(self.ps)['journeyRisk']
        v=self.use_pride(p);self.assertEqual(v['journeyRisk']['roll']['hits'],4)
        v=self.game.action(self.ps,dict(action='travelRisk',roll=p['id'],push=False))
        while self.game.view(self.gs).get('journeyRisk'):
            next_check=self.game.view(self.gs)['journeyRisk'];v=self.game.action(self.gs,dict(action='travelRisk',roll=next_check['id'],push=False))
        self.assertNotIn('journeyRisk',v);self.assertEqual(self.hero()['runtime']['pride']['usedSession'],v['journey']['session'])
        rolls=v['journey']['history'][-1]['rolls'];self.assertEqual(rolls[0]['hits'],4);self.assertEqual(rolls[0]['pride']['value'],12)

    def test_journey_dwarf_can_repeat_before_accept_without_double_cost(self):
        import journey_risk
        from campaign_rules import state
        self.setup_hero('dwarf');room=self.game.room(self.gs['room']);t=state(room)
        t.update(party=[self.cid],plans={self.cid:dict(job='forageFood',role='none',modifier=0,gear=0)},route=[],season='summer',interactiveRisk=True)
        with patch('campaign_rules.secrets.randbelow',return_value=1):journey_risk.resolve(room)
        self.game.save(room);p=self.game.view(self.ps)['journeyRisk']
        with patch('campaign_rules.secrets.randbelow',return_value=1):self.game.action(self.ps,dict(action='travelRisk',roll=p['id'],push=True))
        with patch('campaign_rules.secrets.randbelow',return_value=1):v=self.game.action(self.ps,dict(action='travelRisk',roll=p['id'],push=True,kinRepeat=True,kinAttempt=0))
        self.assertEqual(self.hero()['runtime']['wp'],2);self.assertEqual(v['journeyRisk']['roll']['kinPushes'],1)
        self.game.action(self.ps,dict(action='travelRisk',roll=p['id'],push=False));self.assertEqual(self.hero()['runtime']['wp'],2)

    def test_firewalker_suppresses_cold_and_does_not_accumulate_overdue_checks(self):
        self.setup_hero();self.game.action(self.gs,dict(action='coldExposure',op='configure',character=self.cid,intervalHours=1,note='Стужа'))
        room=self.game.room(self.gs['room']);c=next(c for c in room['characters'] if c['id']==self.cid)
        c['runtime']['magicEffects']=[dict(id='heat',kind='fireproof',until=300)];self.game.save(room)
        v=self.game.view(self.gs);self.assertFalse(v['coldTargets'][0]['exposure']['due']);self.assertTrue(v['coldTargets'][0]['exposure']['protected'])
        self.game.action(self.gs,dict(action='injury',op='advance',minutes=120,note='Защита магии'))
        self.assertEqual(self.hero()['runtime']['coldExposure']['nextAt'],180)

    def test_legacy_pending_journey_migrates_without_changing_original_dice(self):
        import journey_risk
        from campaign_rules import state
        self.setup_hero();room=self.game.room(self.gs['room']);t=state(room)
        t.update(party=[self.cid],plans={self.cid:dict(job='forageFood',role='none',modifier=0,gear=0)},route=[],season='summer',interactiveRisk=True)
        with patch('campaign_rules.secrets.randbelow',return_value=1):journey_risk.resolve(room)
        p=room['journeyRisk'];original=room['diceRolls'][0]['groups'];room['journeyRisk']={k:p[k] for k in ('id','actor','private','attribute')};room['journeyResolution']['choices']=[];self.game.save(room)
        with patch('campaign_rules.secrets.randbelow',return_value=1):v=self.game.action(self.ps,dict(action='travelRisk',roll=p['id'],push=True))
        self.assertEqual(v['diceRolls'][0]['groups'],original);self.assertTrue(v['journeyRisk']['roll']['pushed'])

    def test_human_scout_substitution_and_pushing_remain_private(self):
        import journey_risk
        from campaign_rules import state
        self.setup_hero();room=self.game.room(self.gs['room']);c=next(c for c in room['characters'] if c['id']==self.cid)
        c['runtime']['adaptation']=dict(id='swap',skill='scout',replacement='survive',status='approved',note='Знание местности')
        t=state(room);t.update(party=[self.cid],plans={self.cid:dict(job='rest',role='none',modifier=0,gear=0)},route=[],season='summer',interactiveRisk=True)
        with patch('campaign_rules.secrets.randbelow',return_value=1):journey_risk.resolve(room)
        self.game.save(room);p=self.game.view(self.gs)['journeyRisk'];self.assertEqual(p['roll']['skill'],'survive');self.assertTrue(p['private'])
        with patch('campaign_rules.secrets.randbelow',return_value=1):self.game.action(self.gs,dict(action='travelRisk',roll=p['id'],push=True))
        v=self.game.view(self.ps);self.assertFalse(v['diceRolls']);self.assertEqual(v['journeyRisk'],{'waiting':True})

if __name__=='__main__':unittest.main()
