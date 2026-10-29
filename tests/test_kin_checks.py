import copy
import unittest
from unittest.mock import patch
import test_server as support


class KinCheckTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown
    make_pc=support.CampaignTests.make_pc
    make_npc=support.CampaignTests.make_npc

    def hero(self,kin='human',wp=3):
        c=self.make_pc();room=self.game.room(self.gs['room']);c=next(x for x in room['characters'] if x['id']==c['id'])
        c['sheet']['kin']=kin;c['sheet']['attrs']=dict(str=4,agi=3,wit=3,emp=3);c['sheet']['skills'].update(might=1,lore=2,stealth=1)
        c['runtime'].update(current=copy.deepcopy(c['sheet']['attrs']),wp=wp);self.cid=c['id'];self.game.save(room)
        return self.current()

    def current(self,gm=False):return next(c for c in self.game.view(self.gs if gm else self.ps)['characters'] if c['id']==self.cid)
    def power(self,op,session=None,**data):
        if op=='goblinSuccess':data.setdefault('darkConfirmed',True)
        return self.game.action(session or self.ps,dict(action='characterAbility',character=self.cid,op=op,**data))
    def roll(self,skill='might',**data):
        return self.game.action(self.ps,dict(action='characterRoll',character=self.cid,skill=skill,revision=self.game.view(self.ps)['revision'],**data))
    def push(self,repeat=False):
        r=self.current()['runtime']['lastCheck']
        return self.game.action(self.ps,dict(action='characterPush',character=self.cid,roll=r['id'],kinRepeat=repeat,kinAttempt=r.get('kinPushes',0)))
    def accept(self):return self.game.action(self.ps,dict(action='characterAccept',character=self.cid,roll=self.current()['runtime']['lastCheck']['id']))

    def test_human_request_gm_approval_owner_roll_spends_once(self):
        self.hero();self.power('requestAdaptation',skill='might',replacement='lore',note='Использую знания о рычагах')
        p=self.current()['runtime']['adaptation'];self.assertEqual(p['status'],'requested');self.assertEqual(self.current()['runtime']['wp'],3)
        with self.assertRaises(PermissionError):self.power('approveAdaptation',request=p['id'])
        with self.assertRaises(ValueError):self.roll(adaptation=p['id'])
        self.power('approveAdaptation',self.gs,request=p['id'])
        with patch('skill_checks.die',return_value=2):self.roll(adaptation=p['id'])
        c=self.current();r=c['runtime']['lastCheck'];self.assertEqual((r['skill'],r['originalSkill'],r['attribute']),('lore','might','wit'))
        self.assertEqual((len(r['base']),len(r['skillDice']),c['runtime']['wp']),(3,2,2));self.assertNotIn('adaptation',c['runtime'])
        with self.assertRaises(ValueError):self.roll(adaptation=p['id'])
        self.assertEqual(self.current()['runtime']['wp'],2)

    def test_human_stale_approval_and_other_owner_rejected(self):
        self.hero();self.power('requestAdaptation',skill='might',replacement='lore',note='Первая заявка');old=self.current()['runtime']['adaptation']['id']
        self.power('requestAdaptation',skill='might',replacement='craft',note='Новая заявка');new=self.current()['runtime']['adaptation']['id']
        with self.assertRaises(ValueError):self.power('approveAdaptation',self.gs,request=old)
        other=self.game.login(dict(name='Другой игрок',code=self.gm['code'],key=self.gm['playerKey']));os=self.game.session(other['token'])
        with self.assertRaises(PermissionError):self.power('cancelAdaptation',os,request=new)
        self.power('approveAdaptation',self.gs,request=new)
        with self.assertRaises(PermissionError):self.game.action(os,dict(action='characterRoll',character=self.cid,skill='might',adaptation=new,revision=self.game.view(os)['revision']))

    def test_human_failed_roll_validation_does_not_spend_or_consume_approval(self):
        self.hero();self.power('requestAdaptation',skill='might',replacement='lore',note='Механический расчёт');p=self.current()['runtime']['adaptation']['id'];self.power('approveAdaptation',self.gs,request=p)
        with self.assertRaises(ValueError):self.roll(adaptation=p,item='not-owned')
        self.assertEqual(self.current()['runtime']['wp'],3);self.assertEqual(self.current()['runtime']['adaptation']['id'],p)
        room=self.game.room(self.gs['room']);next(c for c in room['characters'] if c['id']==self.cid)['runtime']['wp']=0;self.game.save(room)
        with self.assertRaises(ValueError):self.roll(adaptation=p)
        self.assertEqual(self.current()['runtime']['wp'],0)

    def test_goblin_successes_use_raw_net_and_accept_prevents_more(self):
        self.hero('goblin')
        # 3 base + 1 skill give no sixes, two penalty dice both give sixes.
        with patch('skill_checks.die',side_effect=[2,2,2,2,6,6]):self.roll('stealth',modifier=-2)
        r=self.current()['runtime']['lastCheck'];self.assertEqual(r['hits'],0)
        self.power('goblinSuccess',roll=r['id'],wp=1);self.assertEqual(self.current()['runtime']['lastCheck']['hits'],0)
        self.power('goblinSuccess',roll=r['id'],wp=2);c=self.current();self.assertEqual(c['runtime']['lastCheck']['hits'],1);self.assertEqual(c['runtime']['wp'],0)
        self.accept()
        with self.assertRaises(ValueError):self.power('goblinSuccess',roll=r['id'],wp=1)

    def test_goblin_wrong_skill_stale_character_and_private_check_protected(self):
        self.hero('goblin')
        with patch('skill_checks.die',return_value=2):self.roll('might')
        with self.assertRaises(ValueError):self.power('goblinSuccess',roll=self.current()['runtime']['lastCheck']['id'],wp=1)
        with patch('skill_checks.die',return_value=2):self.roll('stealth')
        r=self.current()['runtime']['lastCheck'];room=self.game.room(self.gs['room']);next(c for c in room['characters'] if c['id']==self.cid)['runtime']['current']['agi']-=1;self.game.save(room)
        with self.assertRaises(ValueError):self.power('goblinSuccess',roll=r['id'],wp=1)
        with patch('skill_checks.die',return_value=2):
            state=self.game.action(self.gs,dict(action='characterRoll',character=self.cid,skill='stealth',revision=self.game.view(self.gs)['revision'],visibility='hidden'))
        secret=state['gmChecks'][self.cid]
        with self.assertRaises(ValueError):self.power('goblinSuccess',roll=secret['id'],wp=1)
        self.power('goblinSuccess',self.gs,roll=secret['id'],wp=1)
        self.assertTrue(self.game.view(self.gs)['diceRolls'][-1]['private'])
        self.assertNotIn(secret['id'],str(self.game.view(self.ps)['diceRolls']))

    def test_goblin_requires_dark_environment_confirmation_without_spending_wp(self):
        self.hero('goblin')
        with patch('skill_checks.die',return_value=2):self.roll('stealth')
        r=self.current()['runtime']['lastCheck']
        with self.assertRaises(ValueError):self.power('goblinSuccess',roll=r['id'],wp=1,darkConfirmed=False)
        with self.assertRaises(ValueError):self.game.action(self.ps,dict(action='characterAbility',character=self.cid,op='goblinSuccess',roll=r['id'],wp=1))
        self.assertEqual(self.current()['runtime']['wp'],3)

    def test_dwarf_repeat_spends_wp_recounts_locked_ones_wear_then_accepts(self):
        self.hero('dwarf');self.game.action(self.ps,dict(action='inventoryOpen',character=self.cid))
        state=self.game.action(self.gs,dict(action='itemCreate',location=dict(kind='character',id=self.cid),item=dict(name='Инструмент',kind='gear',quantity=1,weight=1,bonus=3)))
        tool=state['items'][-1]
        # Base 1,2,2,2; skill 2; gear 1,2,2. Ones must remain on both pushes.
        with patch('skill_checks.die',side_effect=[1,2,2,2,2,1,2,2]):self.roll(item=tool['id'],itemVersion=tool['version'])
        with patch('skill_checks.die',return_value=2):self.push()
        c=self.current();self.assertEqual((c['runtime']['current']['str'],c['runtime']['wp']),(3,4))
        with patch('skill_checks.die',return_value=2):self.push(True)
        c=self.current();r=c['runtime']['lastCheck'];self.assertEqual((c['runtime']['current']['str'],c['runtime']['wp']),(2,4));self.assertEqual(r['kinPushes'],1)
        self.assertEqual(next(i for i in self.game.view(self.ps)['items'] if i['id']==tool['id'])['wear'],2)
        self.assertEqual(r['base'][0],1);self.assertEqual(r['gear'][0],1)
        self.accept();self.assertTrue(self.current()['runtime']['lastCheck']['accepted'])
        with self.assertRaises(ValueError):self.push(True)

    def test_non_dwarf_cannot_buy_repeat_and_foreign_owner_cannot_push(self):
        self.hero('human')
        with patch('skill_checks.die',return_value=2):self.roll();self.push()
        with self.assertRaises(ValueError):self.push(True)
        other=self.game.login(dict(name='Чужой',code=self.gm['code'],key=self.gm['playerKey']));os=self.game.session(other['token'])
        with self.assertRaises(PermissionError):self.game.action(os,dict(action='characterPush',character=self.cid,roll=self.current()['runtime']['lastCheck']['id'],kinRepeat=True))

    def test_dwarf_repeat_double_submit_is_rejected_before_second_wp_charge(self):
        self.hero('dwarf')
        with patch('skill_checks.die',return_value=2):self.roll();self.push()
        r=self.current()['runtime']['lastCheck'];cmd=dict(action='characterPush',character=self.cid,roll=r['id'],kinRepeat=True,kinAttempt=0)
        with patch('skill_checks.die',return_value=2):self.game.action(self.ps,cmd)
        after=copy.deepcopy(self.current()['runtime'])
        with self.assertRaises(ValueError):self.game.action(self.ps,cmd)
        self.assertEqual(self.current()['runtime'],after)

    def test_opposed_dwarf_repeat_then_stale_repeat_rejected_then_accept(self):
        self.hero('dwarf');npc=self.make_npc()
        v=self.game.action(self.ps,dict(action='opposedCreate',attacker=dict(character=self.cid,skill='might'),defender=dict(character=npc['id'],skill='might')));pair=v['opposedChecks'][-1]['id']
        with patch('skill_checks.die',return_value=2):
            self.game.action(self.ps,dict(action='opposedRoll',id=pair,side='attacker'))
            self.game.action(self.gs,dict(action='opposedRoll',id=pair,side='defender'))
            v=self.game.action(self.ps,dict(action='opposedPush',id=pair))
        self.assertFalse(v['opposedChecks'][-1]['done'])
        cmd=dict(action='opposedPush',id=pair,kinRepeat=True,kinAttempt=0)
        with patch('skill_checks.die',return_value=2):v=self.game.action(self.ps,cmd)
        self.assertFalse(v['opposedChecks'][-1]['done']);self.assertEqual(self.current()['runtime']['wp'],2)
        with self.assertRaises(ValueError):self.game.action(self.ps,cmd)
        v=self.game.action(self.ps,dict(action='opposedAccept',id=pair));self.assertTrue(v['opposedChecks'][-1]['done'])

    def test_positive_modifier_does_not_cancel_injury_penalty_dice(self):
        self.hero();room=self.game.room(self.gs['room']);c=next(c for c in room['characters'] if c['id']==self.cid)
        c['runtime']['injuries']=[dict(id='pain',status='active',name='Штраф проверки',mechanics=dict(modifiers=dict(might=-2)))];self.game.save(room)
        with patch('skill_checks.die',return_value=2):self.roll(modifier=3)
        r=self.current()['runtime']['lastCheck'];self.assertEqual(len(r['skillDice']),4);self.assertEqual(len(r['penalty']),2)

    def test_wolfkin_marks_visible_prey_rejects_hidden_and_releases_without_refund(self):
        self.hero('wolfkin');target=self.make_npc();hidden=self.make_npc(True)
        with self.assertRaises(ValueError):self.power('markPrey',target=target['id'],wp=2,confirmed=False)
        with self.assertRaises(ValueError):self.power('markPrey',target=hidden['id'],wp=2,confirmed=True)
        with self.assertRaises(ValueError):self.power('markPrey',target=self.cid,wp=2,confirmed=True)
        self.power('markPrey',target=target['id'],wp=2,confirmed=True)
        c=self.current();self.assertEqual(c['runtime']['wp'],1);self.assertEqual(c['runtime']['prey'],dict(target=target['id'],bonus=2,days=2,markedDay=1))
        with self.assertRaises(ValueError):self.power('markPrey',target=target['id'],wp=1,confirmed=True)
        self.assertEqual(self.current()['runtime']['wp'],1);self.assertEqual(self.current()['runtime']['prey'],c['runtime']['prey'])
        self.power('releasePrey');self.assertNotIn('prey',self.current()['runtime']);self.assertEqual(self.current()['runtime']['wp'],1)


if __name__=='__main__':unittest.main()
