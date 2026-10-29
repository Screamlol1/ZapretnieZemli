import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import injuries as rules
from injuries_data import TABLES,lookup


class InjuryRulesTests(unittest.TestCase):
    def setUp(self):
        self.gm=dict(role='gm',owner='gm');self.player=dict(role='player',owner='p')
        def hero(cid,owner):
            return dict(id=cid,name=cid,kind='pc',owner=owner,hidden=False,
                        sheet=dict(attrs=dict(str=4,agi=3,wit=3,emp=4),skills=dict(heal=1,perform=1),kin='human'),
                        runtime=dict(current=dict(str=4,agi=3,wit=3,emp=4),wp=3))
        self.healer=hero('healer','p');self.target=hero('target','other')
        self.room=dict(id='test',characters=[self.healer,self.target],items=[],log=[],journey=dict(day=1,quarter=0,phase='planning'))

    def assign(self,table='slash',result=51,target=None):
        c=target or self.target
        with patch('injuries.die',return_value=2):
            return rules.apply(self.room,self.gm,dict(op='assign',character=c['id'],table=table,result=result))

    def treat(self,purpose='save',injury=None,**extra):
        data=dict(op='treat',healer='healer',target='target',purpose=purpose,nearby=True,injury=(injury or {}).get('id'))
        data.update(extra)
        return rules.apply(self.room,self.player,data)

    def finish(self,op='accept'):
        return rules.apply(self.room,self.player,dict(op=op,roll=self.room['treatment']['roll']['id']))

    def test_every_valid_d66_has_exactly_one_rule(self):
        for table,rows in TABLES.items():
            for a in range(1,7):
                for b in range(1,7):
                    result=a*10+b
                    self.assertEqual(sum(r['lo']<=result<=r['hi'] for r in rows),1,(table,result))
                    self.assertEqual(lookup(table,result)['name'],next(r['name'] for r in rows if r['lo']<=result<=r['hi']))
        for invalid in (10,17,20,67,77,True,'11'):
            with self.assertRaises(ValueError):lookup('slash',invalid)

    def test_broken_attack_queues_injury_and_natural_recovery(self):
        before=rules.snapshot(self.room);self.target['runtime']['current']['str']=0
        with patch('injuries.die',return_value=2):rules.reconcile(self.room,before,dict(action='combatManual'))
        self.assertEqual(self.target['runtime']['injuries'][0]['status'],'pending')
        self.assertEqual(self.target['runtime']['brokenRecovery']['str']['due'],120)
        rules.advance(self.room,119);self.assertEqual(self.target['runtime']['current']['str'],0)
        rules.advance(self.room,1);self.assertEqual(self.target['runtime']['current']['str'],1)

    def test_push_and_conditions_never_create_critical(self):
        for action in ('characterPush','travelAdvance','inventoryRepair','opposedPush'):
            room=copy.deepcopy(self.room);c=room['characters'][0]
            room['items']=[dict(id='tool',location=dict(kind='character',id=c['id']))]
            room['opposedChecks']=[dict(id='opposed',attacker=dict(character=c['id']))]
            before=rules.snapshot(room);c['runtime']['current']['str']=0
            data=dict(action=action,character=c['id'],op='push',id='tool' if action=='inventoryRepair' else 'opposed')
            rules.reconcile(room,before,data)
            self.assertFalse(c['runtime'].get('injuries'),action)
            self.assertIn('str',c['runtime']['brokenRecovery'])

    def test_orc_recovers_but_attack_injury_remains(self):
        before=rules.snapshot(self.room)
        self.room['combat']=dict(injuryEvents=[dict(character='target',attribute='str',table='slash',source='attack')])
        rules.reconcile(self.room,before,dict(action='combatAction',command=dict(action='risk',push=False)))
        self.assertEqual(self.target['runtime']['injuries'][0]['table'],'slash')
        self.assertNotIn('injuryEvents',self.room['combat'])

    def test_replay_injury_event_is_deduplicated_and_live_injury_is_restored_to_unit(self):
        self.room['combat']=dict(units=[dict(id='target',injuries=[])])
        event=dict(id='roll:0',character='target',attribute='str',table='slash',source='attack')
        before=rules.snapshot(self.room);self.target['runtime']['current']['str']=0;self.room['combat']['injuryEvents']=[event]
        rules.reconcile(self.room,before,dict(action='combatAction',command=dict(action='slash')))
        self.assertEqual(len(self.target['runtime']['injuries']),1)
        before=rules.snapshot(self.room);self.target['runtime']['current']['str']=1;self.room['combat']['units'][0]['injuries']=[];self.room['combat']['injuryEvents']=[event]
        rules.reconcile(self.room,before,dict(action='combatAction',command=dict(action='risk',push=False)))
        self.assertEqual(len(self.target['runtime']['injuries']),1)
        self.assertEqual(len(self.room['combat']['units'][0]['injuries']),1)
        self.room['combat']['injuryEvents']=[dict(event,id='different:0',source='axeTalent')];before=rules.snapshot(self.room)
        rules.reconcile(self.room,before,dict(action='combatAction',command=dict(action='slash')))
        self.assertEqual(len(self.target['runtime']['injuries']),2)

    def test_generic_orc_is_immediate_and_does_not_clear_trauma(self):
        self.target['sheet']['kin']='orc';before=rules.snapshot(self.room);self.target['runtime']['current']['str']=0
        rules.reconcile(self.room,before,dict(action='runtime'))
        rules.apply(self.room,self.gm,dict(op='orcRecover',character='target',attribute='str',wp=2))
        self.assertEqual(self.target['runtime']['current']['str'],2)
        self.assertEqual(self.target['runtime']['wp'],1)
        self.assertEqual(len(self.target['runtime']['injuries']),1)
        before=rules.snapshot(self.room);self.target['runtime']['current']['str']=0;rules.reconcile(self.room,before,dict(action='runtime'))
        rules.advance(self.room,1)
        with self.assertRaises(ValueError):rules.apply(self.room,self.gm,dict(op='orcRecover',character='target',attribute='str',wp=1))

    def test_prey_ends_when_target_breaks_and_healing_does_not_restore_it(self):
        self.healer['runtime']['prey']=dict(target='target',bonus=2,days=2,markedDay=1)
        self.room['combat']=dict(units=[dict(id='healer',prey=copy.deepcopy(self.healer['runtime']['prey']))])
        before=rules.snapshot(self.room);self.target['runtime']['current']['agi']=0;rules.reconcile(self.room,before,dict(action='runtime'))
        self.assertNotIn('prey',self.healer['runtime']);self.assertNotIn('prey',self.room['combat']['units'][0])
        before=rules.snapshot(self.room);self.target['runtime']['current']['agi']=3;rules.reconcile(self.room,before,dict(action='injury',op='accept'))
        self.assertNotIn('prey',self.healer['runtime'])

    def test_prey_ends_for_broken_monster_and_immediately_recovered_orc_but_not_axe_critical(self):
        self.healer['runtime']['prey']=dict(target='target',bonus=2)
        self.room['combat']=dict(injuryEvents=[dict(id='axe:0',character='target',attribute='str',table='slash',source='axeTalent')])
        before=rules.snapshot(self.room);rules.reconcile(self.room,before,dict(action='combatAction',command=dict(action='slash')))
        self.assertIn('prey',self.healer['runtime'])
        self.room['combat']['injuryEvents']=[dict(id='orc:0',character='target',attribute='str',table='slash',source='attack')]
        before=rules.snapshot(self.room);rules.reconcile(self.room,before,dict(action='combatAction',command=dict(action='risk',push=False)))
        self.assertNotIn('prey',self.healer['runtime'])
        monster=dict(id='monster',name='Чудовище',kind='monster',runtime=dict(current=dict(str=5,agi=3,wit=1,emp=1)))
        self.room['characters'].append(monster);self.healer['runtime']['prey']=dict(target='monster',bonus=1)
        before=rules.snapshot(self.room);monster['runtime']['current']['str']=0;rules.reconcile(self.room,before,dict(action='combatManual'))
        self.assertNotIn('prey',self.healer['runtime'])

    def test_life_saving_is_separate_from_recovery_and_care(self):
        self.target['runtime']['current']['str']=0;i=self.assign()
        with patch('injuries.die',return_value=6):self.treat(injury=i)
        self.assertFalse(i['stabilized']);self.finish()
        self.assertTrue(i['stabilized']);self.assertEqual(self.target['runtime']['current']['str'],0)
        with patch('injuries.die',return_value=6):self.treat('recover',attribute='str')
        self.finish();self.assertEqual(self.target['runtime']['current']['str'],4)
        before=i['healAt'];rules.advance(self.room,60)
        with patch('injuries.die',return_value=6):self.treat('care',injury=i)
        self.finish();self.assertEqual(i['healAt'],60+(before-60)/2)
        with self.assertRaises(ValueError):self.treat('care',injury=i)

    def test_failed_attempt_cannot_repeat_and_other_healer_can(self):
        i=self.assign()
        with patch('injuries.die',return_value=2):self.treat(injury=i)
        self.finish()
        with self.assertRaises(ValueError):self.treat(injury=i)
        self.target['runtime']['current']['str']=1
        with patch('injuries.die',return_value=6):rules.apply(self.room,self.gm,dict(op='treat',healer='target',target='target',purpose='save',injury=i['id'],nearby=True))
        self.assertEqual(len(self.room['treatment']['roll']['penalty']),2)

    def test_mental_recovery_uses_performance(self):
        self.target['runtime']['current']['wit']=0;self.healer['sheet']['skills']['perform']=3
        with patch('injuries.die',return_value=6):self.treat('recover',attribute='wit')
        self.assertEqual(self.room['treatment']['roll']['skill'],'perform')
        self.assertEqual(len(self.room['treatment']['roll']['skillDice']),3)
        self.finish();self.assertEqual(self.target['runtime']['current']['wit'],3)

    def test_push_damages_empathy_and_tool_gives_wp_and_finalizes(self):
        i=self.assign();self.room['items']=[dict(id='bandage',name='Повязки',quantity=1,location=dict(kind='character',id='healer'),bonus=1,wear=0,version=1)]
        with patch('injuries.die',return_value=2):self.treat(injury=i,tool='bandage')
        with patch('injuries.die',return_value=1):self.finish('push')
        self.assertEqual(self.healer['runtime']['current']['emp'],0)
        self.assertEqual(self.healer['runtime']['wp'],7)
        self.assertEqual(self.room['items'][0]['wear'],1)
        self.assertNotIn('treatment',self.room)
        self.assertFalse(i['stabilized'])

    def test_private_targets_and_private_roll_redacted(self):
        self.target['hidden']=True;i=self.assign()
        with self.assertRaises(PermissionError):self.treat(injury=i)
        with patch('injuries.die',return_value=6):rules.apply(self.room,self.gm,dict(op='treat',healer='healer',target='target',purpose='save',injury=i['id'],nearby=True,visibility='hidden'))
        view=copy.deepcopy(self.room);rules.redact(view,self.player)
        self.assertEqual(view['treatment'],dict(waiting=True))
        self.assertEqual([c['id'] for c in view['medicalTargets']],['healer'])
        with self.assertRaises(PermissionError):self.finish()

    def test_unauthorized_actor_or_extra_modifiers_rejected(self):
        i=self.assign()
        with self.assertRaises(PermissionError):rules.apply(self.room,dict(role='player',owner='third'),dict(op='treat',healer='healer',target='target',purpose='save',injury=i['id'],nearby=True))
        with self.assertRaises(ValueError):self.treat(injury=i,modifier=2)
        with self.assertRaises(ValueError):self.treat(injury=i,nearby=False)
        with self.assertRaises(PermissionError):rules.apply(self.room,self.player,dict(op='assign',character='target',table='slash',result=11))

    def test_lethal_expiry_requires_resolution_not_free_late_healing(self):
        i=self.assign();rules.advance(self.room,120)
        self.assertTrue(i['overdue']);self.assertFalse(self.target['runtime'].get('dead'))
        with self.assertRaises(ValueError):self.treat(injury=i)
        rules.apply(self.room,self.gm,dict(op='resolve',character='target',injury=i['id'],outcome='dead',note='Два часа прошли, помощи не было'))
        self.assertTrue(self.target['runtime']['dead'])

    def test_elapsed_days_heal_while_permanent_injury_stays(self):
        temporary=self.assign('blunt',41);permanent=self.assign('slash',45)
        permanent['stabilized']=True;rules.advance(self.room,4*1440)
        self.assertEqual(temporary['status'],'healed');self.assertEqual(permanent['status'],'active')
        self.assertTrue(permanent['mechanics']['runSlow'])
        self.assertEqual(rules.modifiers(self.target,'melee','str'),0)

    def test_neck_paralysis_becomes_permanent_without_care(self):
        i=self.assign('blunt',64)
        self.assertTrue(i['mechanics']['paralyzed']);self.assertFalse(i['mechanics']['incapacitated'])
        rules.advance(self.room,6*1440)
        self.assertTrue(i['permanent']);self.assertEqual(i['status'],'active')

    def test_elf_meditation_requires_elapsed_time_and_gm_confirmation(self):
        c=self.healer;c['sheet']['kin']='elf';c['runtime']['current']['str']=1;i=self.assign('blunt',41,c)
        rules.apply(self.room,self.player,dict(op='meditate',character='healer'))
        self.assertEqual(c['runtime']['wp'],2)
        with self.assertRaises(ValueError):rules.apply(self.room,self.gm,dict(op='meditationFinish',character='healer',undisturbed=True))
        rules.advance(self.room,360)
        with self.assertRaises(PermissionError):rules.apply(self.room,self.player,dict(op='meditationFinish',character='healer',undisturbed=True))
        rules.apply(self.room,self.gm,dict(op='meditationFinish',character='healer',undisturbed=True))
        self.assertEqual(c['runtime']['current'],c['sheet']['attrs']);self.assertEqual(i['status'],'healed')

    def test_elf_errata_does_not_regrow_lost_limb(self):
        c=self.healer;c['sheet']['kin']='elf';i=self.assign('slash',55,c);i['stabilized']=True
        rules.apply(self.room,self.player,dict(op='meditate',character='healer'));rules.advance(self.room,360)
        rules.apply(self.room,self.gm,dict(op='meditationFinish',character='healer',undisturbed=True))
        self.assertEqual(i['status'],'active');self.assertTrue(i['mechanics']['noTwoHand']);self.assertTrue(i['stabilized'])

    def test_successful_save_cannot_push_for_no_extra_effect(self):
        i=self.assign()
        with patch('injuries.die',side_effect=[6,2,2,2,2]):self.treat(injury=i)
        self.assertEqual(self.room['treatment']['roll']['hits'],1)
        self.assertFalse(self.room['treatment']['roll']['pushAvailable'])
        with self.assertRaises(ValueError):self.finish('push')
        self.finish();self.assertTrue(i['stabilized'])

    def test_combat_aid_requires_turn_slow_action_and_adjacent_target(self):
        self.target['runtime']['current']['str']=0
        self.room['combat']=dict(phase='combat',order=['healer','target'],turn=0,units=[dict(id='healer',q=0,r=0,slow=1),dict(id='target',q=3,r=0,slow=0)])
        with self.assertRaises(ValueError):self.treat('recover',attribute='str')
        self.room['combat']['units'][1]['q']=1
        with patch('injuries.die',return_value=6):self.treat('recover',attribute='str')
        self.assertEqual(self.room['combat']['units'][0]['slow'],0)
        self.finish();self.assertEqual(self.room['combat']['units'][1]['str'],4)

    def test_journey_clock_advances_once_at_quarter_and_not_wall_time(self):
        before=rules.snapshot(self.room);self.room['journey']['quarter']=1
        rules.reconcile(self.room,before,dict(action='travelComplete'))
        self.assertEqual(self.room['medicalClock'],360)
        before=rules.snapshot(self.room);rules.reconcile(self.room,before,dict(action='chat'))
        self.assertEqual(self.room['medicalClock'],360)


if __name__=='__main__':unittest.main()
