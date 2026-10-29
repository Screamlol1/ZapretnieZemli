import json
import unittest
from unittest.mock import patch
import test_server as support
from equipment_rules import combat_gear


class RepairTests(unittest.TestCase):
    setUp = support.CampaignTests.setUp
    tearDown = support.CampaignTests.tearDown
    make_pc = support.CampaignTests.make_pc
    make_npc = support.CampaignTests.make_npc

    def setup_item(self, bonus=3, wear=2, armor=0, hidden=False):
        c = self.make_npc(True) if hidden else self.make_pc()
        self.game.action(self.gs, dict(action='inventoryOpen', character=c['id']))
        raw = dict(name='Ремонтируемый меч', kind='armor' if armor else 'weapon', bonus=bonus, armor=armor,
                   combatProfile='' if armor else 'sword', damage=2, quantity=1, weight=1, artifactDie='D8')
        i = self.game.action(self.gs, dict(action='itemCreate', location=dict(kind='character', id=c['id']), item=raw))['items'][-1]
        self.game.action(self.gs, dict(action='itemWear', id=i['id'], version=i['version'], wear=wear, note='Износ после боя'))
        room = self.game.room(self.gs['room'])
        hero = next(x for x in room['characters'] if x['id'] == c['id'])
        hero['runtime']['current']['str'] = 2
        hero['sheet']['skills']['craft'] = 2
        hero['equipment']['armor' if armor else 'weapon'] = i['id']
        self.game.save(room)
        self.cid, self.iid = c['id'], i['id']
        return c, self.item()

    def item(self):
        return next(i for i in self.game.view(self.gs)['items'] if i['id'] == self.iid)

    def cmd(self, op, session=None, **values):
        i = self.item()
        return self.game.action(session or self.ps, dict(action='inventoryRepair', id=i['id'], version=i['version'],
                                                        op=op, roll=i.get('repair', {}).get('roll', {}).get('id'), **values))

    def approve(self, **values):
        return self.cmd('approve', self.gs, conditionsConfirmed=True, note='Четыре часа в кузнице; нужные достоинства проверены', **values)

    def roll(self, values=None, session=None, **kwargs):
        with patch('inventory_repair.die', side_effect=values or [2]*30):
            return self.cmd('roll', session, **kwargs)

    def test_owner_rolls_after_gm_approval_success_and_result_survive_restart(self):
        self.setup_item()
        self.cmd('request', note='Починить меч')
        with self.assertRaises(PermissionError):
            self.cmd('approve', conditionsConfirmed=True, note='Сам разрешил')
        with self.assertRaises(ValueError):
            self.roll()
        self.approve()
        self.roll([6,2,2,2])
        self.assertEqual(self.item()['wear'], 2)
        self.cmd('accept')
        i = self.item()
        self.assertEqual((i['bonus'], i['wear'], i['lastRepair']['restored']), (3,1,1))
        self.assertNotIn('repair', i)
        self.game.db.close()
        self.game = support.Game(self.path, reference_root=self.path.parent/'local-assets')
        self.assertEqual(self.item()['lastRepair']['restored'], 1)
        self.approve()
        self.roll([6,6,6,6])
        self.cmd('accept')
        self.assertEqual((self.item()['bonus'], self.item()['wear']), (3,0))
        with self.assertRaises(ValueError):
            self.cmd('request')

    def test_failed_repair_changes_permanent_combat_maximum(self):
        self.setup_item()
        self.approve()
        self.roll()
        self.cmd('accept')
        i = self.item()
        self.assertEqual((i['bonus'],i['wear']), (1,0))
        room = self.game.room(self.gs['room'])
        c = next(c for c in room['characters'] if c['id']==self.cid)
        self.assertEqual(combat_gear(room,c)['slots']['weapon']['bonus'],1)
        self.assertEqual((i['damage'],i['combatProfile'],i['artifactDie']), (2,'sword','D8'))
        self.game.action(self.gs,dict(action='itemWear',id=i['id'],version=i['version'],wear=1,note='Новый износ'))
        self.approve(); self.roll([6,6,6,6]); self.cmd('accept')
        self.assertEqual((self.item()['bonus'],self.item()['wear']), (1,0))

    def test_armor_and_destroyed_equipment(self):
        self.setup_item(bonus=0,armor=5,wear=2)
        self.approve(); self.roll(); self.cmd('accept')
        self.assertEqual((self.item()['armor'],self.item()['wear']), (3,0))
        i = self.item()
        self.game.action(self.gs,dict(action='itemWear',id=i['id'],version=i['version'],wear=3,note='Поломка'))
        self.approve(); self.roll()
        i = self.item(); command=dict(action='inventoryRepair',op='accept',id=i['id'],version=i['version'],roll=i['repair']['roll']['id'])
        self.game.action(self.ps,command)
        view=self.game.view(self.ps)
        self.assertNotIn(self.iid,[i['id'] for i in view['items']])
        c=next(c for c in view['characters'] if c['id']==self.cid)
        self.assertNotIn('armor',c['equipment'])
        self.assertTrue(c['runtime']['lastRepair']['destroyed'])
        with self.assertRaises(ValueError):self.game.action(self.ps,command)

    def test_push_preserves_skill_penalty_pools_holds_and_wears_only_tool(self):
        self.setup_item(bonus=5,wear=4)
        tool=self.game.action(self.gs,dict(action='itemCreate',location=dict(kind='character',id=self.cid),item=dict(name='Инструмент',bonus=2,artifactDie='D10',weight=1)))['items'][-1]
        self.approve(tool=tool['id'],modifier=-1,artifacts=[8,12])
        # 2 base, full 2 skill, 2 gear, 1 independent penalty, D10+D8+D12.
        self.roll([1,2,6,2,1,2,2,8,3,12])
        r=self.item()['repair']['roll']
        self.assertEqual((len(r['skillDice']),len(r['penalty']),len(r['artifacts'])),(2,1,3))
        before=next(c for c in self.game.view(self.ps)['characters'] if c['id']==self.cid)['runtime']
        with patch('inventory_repair.die',side_effect=[6,6,6,6,6]):self.cmd('push')
        view=self.game.view(self.ps);c=next(c for c in view['characters'] if c['id']==self.cid)
        self.assertEqual(c['runtime']['current']['str'],before['current']['str']-1)
        self.assertEqual(c['runtime']['wp'],before['wp']+1)
        self.assertEqual(next(i for i in view['items'] if i['id']==tool['id'])['wear'],1)
        self.assertEqual(self.item()['wear'],0)
        groups=view['diceRolls'][-1]['groups']
        self.assertTrue(any(g.get('held') and any(g['held']) for g in groups))
        with self.assertRaises(ValueError):self.cmd('push')

    def test_approval_fixes_composition_and_rejects_changed_item_or_tool(self):
        self.setup_item()
        tool=self.game.action(self.gs,dict(action='itemCreate',location=dict(kind='character',id=self.cid),item=dict(name='Инструмент',bonus=1)))['items'][-1]
        self.approve(tool=tool['id'],modifier=-2)
        self.game.action(self.ps,dict(action='itemAppearance',id=tool['id'],version=tool['version'],art='warhammer'))
        with self.assertRaises(ValueError):self.roll()
        self.approve(tool=tool['id'],modifier=-2)
        self.roll(modifier=10,artifacts=[12]*10,tool='forged')
        r=self.item()['repair']['roll']
        self.assertEqual((len(r['skillDice']),len(r['penalty']),len(r['artifacts']),len(r['gear'])),(2,2,0,1))
        self.cmd('accept')
        i=self.item()
        self.game.action(self.gs,dict(action='itemWear',id=i['id'],version=i['version'],wear=1,note='Новый износ'))
        self.approve()
        i=self.item()
        self.game.action(self.ps,dict(action='itemAppearance',id=i['id'],version=i['version'],art='sword'))
        with self.assertRaises(ValueError):self.roll()

    def test_pending_decision_locks_inventory_and_checks_but_can_be_accepted(self):
        self.setup_item();self.approve();self.roll()
        i=self.item()
        with self.assertRaises(ValueError):self.cmd('cancel')
        with self.assertRaises(ValueError):self.cmd('request')
        with self.assertRaises(ValueError):self.cmd('approve',self.gs,conditionsConfirmed=True,note='Повтор')
        for command in [dict(action='itemAppearance',id=i['id'],version=i['version'],art='sword'),
                        dict(action='characterRoll',character=self.cid,skill='craft',revision=self.game.view(self.ps)['revision']),
                        dict(action='itemCreate',location=i['location'],item=dict(name='Обход'))]:
            with self.assertRaises(ValueError):self.game.action(self.ps,command)
        # Even if an old saved state was externally changed, accepting its fixed
        # original result remains possible; pushing must not use a new sheet.
        room=self.game.room(self.gs['room']);c=next(c for c in room['characters'] if c['id']==self.cid)
        c['runtime']['wp']+=1;self.game.save(room)
        with self.assertRaises(ValueError):self.cmd('push')
        self.cmd('accept')
        self.assertNotIn('repair',self.item())

    def test_private_roll_and_hidden_npc_do_not_leak(self):
        self.setup_item();self.approve()
        with self.assertRaises(PermissionError):self.roll(visibility='hidden')
        self.roll(session=self.gs,visibility='hidden')
        public=next(i for i in self.game.view(self.ps)['items'] if i['id']==self.iid)
        self.assertEqual(public['repair'],dict(status='rolled',character=self.cid,waiting=True))
        self.assertNotIn('Ремесло · ремонт',json.dumps(self.game.view(self.ps),ensure_ascii=False))
        with self.assertRaises(PermissionError):self.cmd('accept')
        self.cmd('accept',self.gs)
        public=next(i for i in self.game.view(self.ps)['items'] if i['id']==self.iid)
        self.assertNotIn('lastRepair',public)
        self.setup_item(hidden=True)
        self.approve();self.roll(session=self.gs);self.cmd('accept',self.gs)
        view=self.game.view(self.ps)
        self.assertNotIn(self.iid,json.dumps(view))
        npc=next(c for c in self.game.view(self.gs)['characters'] if c['id']==self.cid)
        self.assertNotIn('lastRepair',npc['runtime'])

    def test_permissions_conditions_stack_and_self_tool_validation(self):
        self.setup_item()
        with self.assertRaises(ValueError):self.cmd('approve',self.gs,note='Без подтверждения')
        with self.assertRaises(ValueError):self.cmd('approve',self.gs,conditionsConfirmed=True,note='')
        with self.assertRaises(ValueError):self.approve(tool=self.iid)
        other=self.game.login(dict(name='Другой',code=self.gm['code'],key=self.gm['playerKey']))
        with self.assertRaises(PermissionError):self.cmd('request',self.game.session(other['token']))
        room=self.game.room(self.gs['room']);next(i for i in room['items'] if i['id']==self.iid)['quantity']=2;self.game.save(room)
        with self.assertRaises(ValueError):self.cmd('request')

    def test_direct_gm_roll_and_stale_command_are_atomic(self):
        self.setup_item()
        self.roll(session=self.gs,conditionsConfirmed=True,note='Время и условия подтверждены')
        i=self.item()
        cmd=dict(action='inventoryRepair',op='accept',id=i['id'],version=i['version']-1,roll=i['repair']['roll']['id'])
        with self.assertRaises(ValueError):self.game.action(self.ps,cmd)
        self.assertEqual(self.item()['repair']['status'],'rolled')
        self.cmd('accept')

    def test_pending_repair_guards_sheet_battle_and_journey_mutations(self):
        self.setup_item();self.approve();self.roll()
        for action in ('character','actor','runtime','deleteCharacter','assignCharacter','characterProgression'):
            with self.subTest(action=action),self.assertRaisesRegex(ValueError,'ремонт'):
                self.game.action(self.gs,dict(action=action,id=self.cid))
        for command in (dict(action='combatCreate',units=[dict(id=self.cid)]),
                        dict(action='travelSetup',party=[self.cid]),dict(action='travelPlan',id=self.cid)):
            with self.assertRaisesRegex(ValueError,'ремонт'):self.game.action(self.gs,command)
        room=self.game.room(self.gs['room']);room['journey']['party']=[self.cid];self.game.save(room)
        with self.assertRaisesRegex(ValueError,'ремонт'):self.game.action(self.gs,dict(action='travelAdvance'))
        self.cmd('accept')

    def test_npc_push_never_grants_willpower_and_requires_closed_combat(self):
        self.setup_item(hidden=True);self.approve();self.roll([1,2,2,2],self.gs)
        before=next(c for c in self.game.view(self.gs)['characters'] if c['id']==self.cid)['runtime'].get('wp',0)
        with patch('inventory_repair.die',return_value=6):self.cmd('push',self.gs)
        self.assertEqual(next(c for c in self.game.view(self.gs)['characters'] if c['id']==self.cid)['runtime'].get('wp',0),before)
        i=self.item();self.game.action(self.gs,dict(action='itemWear',id=i['id'],version=i['version'],wear=1,note='Износ'))
        room=self.game.room(self.gs['room']);room['combat']={'phase':'setup','units':[]};room['combatOwners']={self.cid:'gm'};self.game.save(room)
        with self.assertRaisesRegex(ValueError,'бой'):self.cmd('request',self.gs)

    def test_all_held_dice_require_accepting_without_another_push(self):
        self.setup_item();self.approve();self.roll([1,6,6,6])
        with self.assertRaisesRegex(ValueError,'Нет костей'):self.cmd('push')
        self.cmd('accept')
        self.assertEqual(self.item()['wear'],0)
