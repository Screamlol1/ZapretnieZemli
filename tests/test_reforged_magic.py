"""Catalog coverage, module permissions, simultaneous commitments and persistence."""
import copy
import unittest
from unittest.mock import patch
import test_server as support
import magic_rules as magic
import rule_passport as rules

class ReforgedTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown
    make_pc=support.CampaignTests.make_pc
    make_npc=support.CampaignTests.make_npc
    def room(self):return self.game.room(self.gs['room'])
    def act(self,op,s=None,**values):return self.game.action(s or self.gs,dict(action='magic',op=op,**values))
    def passport(self,op,s=None,**values):return self.game.action(s or self.gs,dict(action='rulePassport',op=op,**values))
    def enable(self,**modules):
        p=rules.ensure(self.room());return self.passport('configure',revision=p['revision'],modules={k:modules.get(k,False) for k in rules.MODULES},note='Изолированная проверка модулей.')
    def wizard(self,npc=False,school='healing',rank=3):
        c=self.make_npc() if npc else self.make_pc();room=self.room();c=next(x for x in room['characters'] if x['id']==c['id']);c['sheet'].update(paths={school:rank},path=school,pathRank=rank,npcTalentsConfigured=True);c['runtime']['wp']=10;self.game.save(room);return c
    def declare(self,c,spell='lightbringer',**values):
        data=dict(character=c['id'],spell=spell,target=c['id'],wp=1,safe=True,note='Условия проверяются Мастером.');data.update(values)
        return self.act('declare',**data)['magicCastings'][-1]['id']

    def test_coverage_and_reference_separation(self):
        c=magic.REFORGED;self.assertEqual((len(c['spells']),len(c['references']),len(c['coverage'])),(337,32,369));self.assertEqual(sum(s['source']=='Reforged Power 3.3' for s in c['spells']),246)
        self.assertEqual(len(magic.SPELLS),68)
        self.assertTrue(all(s['summary'] and s['page'] and s['resolution'] in ('review','automatic') for s in c['spells']))
        self.assertFalse(any(r['id'] in magic.ALL_SPELLS for r in c['references']))
        serenity=next(s for s in c['spells'] if s.get('baseSpellId')=='serenity');self.assertEqual(serenity['school'],'signs');self.assertEqual(serenity['origin'],'modified')
        self.assertEqual(magic.SPELLS['serenity']['school'],'healing')
        self.assertEqual(sum(s['en'].lower()=='combustion' for s in c['spells']),2)

    def test_modules_and_training_authorized_next_rank_only(self):
        c=self.wizard();spell='rp_healing_preserve'
        with self.assertRaisesRegex(ValueError,'включить'):self.declare(c,spell)
        with self.assertRaises(PermissionError):self.passport('configure',self.ps,revision=0,modules={k:True for k in rules.MODULES},note='Нет прав')
        self.enable(reforgedSpells=True)
        with self.assertRaisesRegex(ValueError,'следующий'):self.passport('requestTraining',self.ps,character=c['id'],school='nature',rank=2,note='Учитель и опыт записаны.')
        v=self.passport('requestTraining',self.ps,character=c['id'],school='nature',rank=1,note='Учитель, четверть работы, отдельное решение об опыте.');request=v['rulePassport']['trainingRequests'][-1]['id']
        with self.assertRaises(PermissionError):self.passport('decideTraining',self.ps,request=request,accept=True,confirmed=True,note='Не Мастер')
        self.passport('decideTraining',request=request,accept=True,confirmed=True,note='Друид изучил новую школу; стоимость учтена в листе.')
        self.assertEqual(magic.rank(self.room()['characters'][0],'nature'),1)
        with self.assertRaisesRegex(ValueError,'уже обработана'):self.passport('decideTraining',request=request,accept=True,confirmed=True,note='Повтор')

    def test_required_ingredient_no_power_bonus(self):
        self.enable(reforgedSpells=True);c=self.wizard(school='elements');spell='rp_elements_flaming_blade'
        with self.assertRaisesRegex(ValueError,'обязателен'):self.declare(c,spell)
        r=self.declare(c,spell,ingredientScene='Горящий факел на расстоянии руки.');self.act('approve',casting=r,confirmed=True)
        with patch('magic_rules.die',side_effect=AssertionError('safe cast')):v=self.act('cast',casting=r)
        self.assertEqual(v['magicCastings'][-1]['power'],1);self.assertEqual(v['magicCastings'][-1]['status'],'rolled')

    def test_reactions_hidden_commitments_atomic_costs_and_once(self):
        self.enable(magicReactions=True);c=self.wizard(school='sight');other=self.wizard(npc=True);self.act('pool',value=5)
        r=self.declare(c);self.act('approve',casting=r,confirmed=True,reactors=[other['id']])
        room=self.room();view=copy.deepcopy(room);magic.project(view,dict(role='player',owner='outsider'))
        self.assertNotIn('wp',view['magicCastings'][-1]);self.assertNotIn('formula',view['magicCastings'][-1])
        with self.assertRaisesRegex(ValueError,'подтверждение'):self.act('cast',casting=r)
        self.act('react',casting=r,character=other['id'],wp=1,safe=True)
        view=self.game.view(self.ps);response=view['magicCastings'][-1]['reactions'][0];self.assertEqual(set(response),{'character','status'})
        with self.assertRaises(ValueError):self.act('react',casting=r,character=other['id'],pass_=True)
        with patch('magic_rules.die',side_effect=AssertionError('safe cast')):v=self.act('cast',casting=r)
        cast=v['magicCastings'][-1];self.assertEqual((cast['rawPower'],cast['counterPower'],cast['power'],cast['status']),(1,1,0,'resolved'));self.assertEqual(self.room()['magicWillpower'],4);self.assertEqual(self.room()['characters'][0]['runtime']['wp'],9)
        self.assertFalse(self.room()['characters'][0]['runtime'].get('magicEffects'))
        with self.assertRaises(ValueError):self.act('cast',casting=r)

    def test_reactor_signature_change_spends_nothing(self):
        self.enable(magicReactions=True);c=self.wizard(school='sight');other=self.wizard(npc=True);self.act('pool',value=5)
        r=self.declare(c);self.act('approve',casting=r,confirmed=True,reactors=[other['id']]);self.act('react',casting=r,character=other['id'],wp=1,safe=True)
        room=self.room();room['characters'][1]['runtime']['current']['str']-=1;self.game.save(room)
        with self.assertRaisesRegex(ValueError,'изменились'):self.act('cast',casting=r)
        self.assertEqual(self.room()['magicWillpower'],5);self.assertEqual(self.room()['characters'][0]['runtime']['wp'],10)

    def test_durable_verdict_survives_restore_then_expires(self):
        self.enable(reforgedSpells=True);c=self.wizard();r=self.declare(c,'rp_healing_preserve');self.act('approve',casting=r,confirmed=True);self.act('cast',casting=r)
        self.act('resolve',casting=r,mode='manual',note='Предмет сохраняется 15 минут.',effects=[dict(character=c['id'],note='Не портится до конца срока.',unit='minutes',duration=15)])
        room=self.room();e=room['characters'][0]['runtime']['magicEffects'][0];original=e['id'];magic.restored(room);self.assertNotEqual(e['id'],original);self.assertEqual(e['note'],'Не портится до конца срока.')
        room['medicalClock']=14;magic.reconcile(room);self.assertEqual(len(room['characters'][0]['runtime']['magicEffects']),1)
        room['medicalClock']=15;magic.reconcile(room);self.assertFalse(room['characters'][0]['runtime']['magicEffects'])

    def test_epic_requires_material_note_and_gm_confirmation(self):
        self.enable(reforgedSpells=True,advancedMagic=True);c=self.wizard(school='healing',rank=5)
        with self.assertRaisesRegex(ValueError,'эпические'):self.declare(c,'rp_healing_restore_life',ingredientScene='Особые материалы')
        r=self.declare(c,'rp_healing_restore_life',ingredientScene='Особые материалы',epicComponents='Материалы на мощь 1, проверены по стр.110.')
        with self.assertRaisesRegex(ValueError,'Отдельно'):self.act('approve',casting=r,confirmed=True)
        self.act('approve',casting=r,confirmed=True,epicConfirmed=True)

if __name__=='__main__':unittest.main()
