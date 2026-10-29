"""Server-boundary regressions for decisions, initiative and elf meditation."""
import copy
import unittest
from unittest.mock import patch

import test_server as support


class CombatPermissionTests(unittest.TestCase):
    setUp = support.CampaignTests.setUp
    tearDown = support.CampaignTests.tearDown
    make_pc = support.CampaignTests.make_pc
    make_npc = support.CampaignTests.make_npc

    def room(self):
        return self.game.room(self.gs['room'])

    def command(self, command, session=None):
        return self.game.action(session or self.gs, dict(
            action='combatAction', revision=self.room()['combatRevision'], command=command))

    def battle(self):
        pc, npc = self.make_pc(), self.make_npc()
        self.game.action(self.gs, dict(action='combatCreate', units=[
            dict(id=pc['id'], team='A'), dict(id=npc['id'], team='B')]))
        self.command(dict(action='start'))
        if self.room()['combat']['order'][self.room()['combat']['turn']] != pc['id']:
            self.command(dict(action='end'))
        return pc['id'], npc['id']

    def test_client_cannot_disable_interactive_attack_or_pending_decisions(self):
        pc, npc = self.battle()
        # Intercept the actual engine boundary: client flags must never select its
        # non-interactive auto-resolution path, including follow-up kin decisions.
        with patch.object(self.game, 'engine', side_effect=lambda data: copy.deepcopy(data['battle'])) as engine:
            for supplied in ({}, dict(interactive=False)):
                with self.subTest(stage='attack', supplied=supplied):
                    cmd = dict(action='slash', target=npc, **supplied)
                    original = copy.deepcopy(cmd)
                    self.command(cmd, self.ps)
                    self.assertIs(engine.call_args.args[0]['command']['interactive'], True)
                    self.assertEqual(cmd, original)
            for kind in ('attack', 'halfling', 'orc'):
                with self.subTest(stage=kind):
                    room = self.room()
                    room['combat']['pendingRisk'] = dict(id='decision-' + kind, actor=pc, kind=kind, private=False)
                    self.game.save(room)
                    self.command(dict(action='risk', roll='decision-' + kind, push=False, interactive=False), self.ps)
                    self.assertIs(engine.call_args.args[0]['command']['interactive'], True)
                    self.assertEqual(engine.call_args.args[0]['battle']['pendingRisk']['actor'], pc)
                    # Even the owning player cannot skip a pending choice with
                    # another command; a malformed request never reaches JS.
                    calls = engine.call_count
                    with self.assertRaisesRegex(ValueError, 'Сначала'):
                        self.command(dict(action='end', interactive=False), self.ps)
                    self.assertEqual(engine.call_count, calls)

    def test_manual_slow_action_spends_budget_and_closes_initiative_exchange(self):
        first = self.make_pc()
        pc, npc, ally = first['id'], self.make_npc()['id'], 'initiative-ally'
        self.game.action(self.ps, dict(action='character', id=ally,
                                      sheet={**first['sheet'], 'name': 'Второй герой'}))
        self.game.action(self.gs, dict(action='combatCreate', units=[
            dict(id=pc, team='A'), dict(id=ally, team='A'), dict(id=npc, team='B')]))
        self.command(dict(action='start'))
        self.command(dict(action='initiativeOffer', unit=pc, target=ally), self.ps)
        battle = self.room()['combat']
        actor = battle['order'][battle['turn']]

        def manual(slow, session=None):
            return self.game.action(session or self.gs, dict(
                action='combatManual', revision=self.room()['combatRevision'],
                actor=actor, target=npc, attribute='str', damage=0, wp=0,
                slow=slow, note='Решение без урона для проверки расхода действия'))

        with self.assertRaises(PermissionError):
            manual(True, self.ps)
        manual(False)
        battle = self.room()['combat']
        self.assertFalse(battle['roundStarted'])
        self.assertFalse(battle['activationStarted'])
        self.assertIn('initiativeOffer', battle)
        slow_before = next(u for u in battle['units'] if u['id'] == actor)['slow']
        cards_before = copy.deepcopy(battle['initiativeSlots'])
        manual(True)
        battle = self.room()['combat']
        self.assertTrue(battle['roundStarted'])
        self.assertTrue(battle['activationStarted'])
        self.assertNotIn('initiativeOffer', battle)
        self.assertEqual(next(u for u in battle['units'] if u['id'] == actor)['slow'], slow_before - 1)
        with self.assertRaisesRegex(ValueError, 'до первого действия'):
            self.command(dict(action='initiativeOffer', unit=pc, target=ally), self.ps)
        with self.assertRaises(ValueError):
            manual(True)
        self.assertEqual(self.room()['combat']['initiativeSlots'], cards_before)

    def travel(self, action, session=None, **data):
        t = self.room()['journey']
        s = session or self.gs
        return self.game.action(s, dict(
            action=action, revision=t['revision'],
            cycle=[t['day'], t['quarter'], t['cycleId']], phase=t['phase'],
            routeVersion=t['routeVersion'],
            planVersion=t['planVersions'].get(data.get('id'), 0),
            completionVersion=t['completionVersions'].get('gm' if s['role'] == 'gm' else s['owner'], 0),
            **data))

    def elf_party(self):
        pc = self.make_pc()
        sheet = copy.deepcopy(pc['sheet'])
        sheet['kin'] = 'elf'
        sheet['age'] = 'adult'
        self.game.action(self.ps, dict(action='character', id=pc['id'], sheet=sheet))
        room = self.room()
        next(c for c in room['characters'] if c['id'] == pc['id'])['runtime']['wp'] = 1
        self.game.save(room)
        self.travel('travelSetup', party=[pc['id']], x=0, y=0, season='summer')
        return pc['id']

    def meditate(self, cid):
        self.game.action(self.ps, dict(action='injury', op='meditate', character=cid))

    def test_meditating_elf_can_only_declare_rest_until_cancelled(self):
        cid = self.elf_party()
        self.meditate(cid)
        for s in (self.ps, self.gs):
            with self.subTest(role=s['role']):
                with self.assertRaisesRegex(ValueError, 'медитации'):
                    self.travel('travelPlan', session=s, id=cid, job='hike', role='lead')
        self.assertNotIn(cid, self.room()['journey']['plans'])
        self.travel('travelPlan', session=self.ps, id=cid, job='rest')
        self.assertEqual(self.room()['journey']['plans'][cid]['job'], 'rest')
        self.game.action(self.ps, dict(action='injury', op='meditationCancel', character=cid))
        self.travel('travelPlan', session=self.ps, id=cid, job='hike', role='lead')
        self.assertEqual(self.room()['journey']['plans'][cid]['job'], 'hike')
        pc = next(c for c in self.room()['characters'] if c['id'] == cid)
        self.assertEqual(pc['runtime']['wp'], 0)

    def test_meditation_started_after_plan_blocks_quarter_until_plan_is_rest(self):
        cid = self.elf_party()
        self.travel('travelPlan', session=self.ps, id=cid, job='hike', role='lead')
        self.meditate(cid)
        before = copy.deepcopy(self.room()['journey'])
        self.travel('travelReady', ready=True, path=[dict(x=1, y=0)])
        t = self.room()['journey']
        self.assertEqual(t['phase'], 'planning')
        self.assertFalse(t['gmReady'])
        self.assertIn('Медитирующий', t['blocker'])
        self.assertEqual((t['day'], t['quarter'], t['position']),
                         (before['day'], before['quarter'], before['position']))
        self.travel('travelPlan', session=self.ps, id=cid, job='rest')
        self.travel('travelReady', ready=True, path=[])
        self.assertEqual(self.room()['journey']['phase'], 'resolving')
        for event in list(self.room()['journey']['pending']):
            self.travel('travelResolve', id=event['id'], note='Стоянка прошла спокойно; эльфа не тревожили.')
        self.travel('travelComplete', session=self.ps, complete=True)
        self.travel('travelComplete', complete=True)
        t = self.room()['journey']
        self.assertEqual(t['quarter'], (before['quarter'] + 1) % 4)
        self.assertEqual(t['position'], before['position'])


if __name__ == '__main__':
    unittest.main()
