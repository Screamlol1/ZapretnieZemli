import unittest
import test_server as support


class ExpandedCombatTests(unittest.TestCase):
    setUp = support.CampaignTests.setUp
    tearDown = support.CampaignTests.tearDown
    make_pc = support.CampaignTests.make_pc
    make_npc = support.CampaignTests.make_npc

    def command(self, command, session=None):
        return self.game.action(session or self.gs, dict(action='combatAction', revision=self.game.view(self.gs)['combatRevision'], command=command))

    def test_ten_heroes_plus_grouped_enemies_and_authorization(self):
        first = self.make_pc()
        other = self.game.login(dict(name='Второй игрок', code=self.gm['code'], key=self.gm['playerKey']))
        ps2 = self.game.session(other['token'])
        heroes = [first['id']]
        for i in range(1, 10):
            cid = 'hero-' + str(i)
            self.game.action(self.ps if i < 5 else ps2, dict(action='character', id=cid, sheet={**first['sheet'], 'name': 'Герой ' + str(i)}))
            heroes.append(cid)
        enemies = [self.make_npc()['id'] for _ in range(3)]
        units = [dict(id=cid, team='A') for cid in heroes] + [dict(id=cid, team='B') for cid in enemies]
        v = self.game.action(self.gs, dict(action='combatCreate', units=units))
        self.assertEqual(len(v['combat']['units']), 13)
        with self.assertRaises(ValueError):
            self.command(dict(action='start', interactive=True))
        with self.assertRaises(PermissionError):
            self.command(dict(action='initiativeAutogroup'), self.ps)
        self.command(dict(action='initiativeAutogroup'))
        for cid in heroes[:2]:
            self.command(dict(action='initiativeConfigure', unit=cid, group='Союзники', activations=1, sharedHeroes=True))
        v = self.command(dict(action='start', interactive=True))
        self.assertEqual(len(v['combat']['initiativeSlots']), 10)
        self.assertEqual(len(v['combat']['order']), 13)
        self.assertEqual(len(set(s['card'] for s in v['combat']['initiativeSlots'])), 10)
        before = v['combat']['order']
        for _ in range(13):
            v = self.command(dict(action='end'))
        self.assertEqual(v['combat']['round'], 2)
        self.assertEqual(v['combat']['order'], before)
        # A PC cannot use the GM's group-order tool, even for their own hero.
        with self.assertRaises(PermissionError):
            self.command(dict(action='initiativeGroupNext', target=heroes[0]), self.ps)

    def test_npc_path_is_explicit_and_legacy_default_is_inert(self):
        pc = self.make_pc()
        npc = self.make_npc()
        self.assertEqual(npc['sheet']['pathRank'], 0)
        room = self.game.room(self.gs['room'])
        old = next(c for c in room['characters'] if c['id'] == npc['id'])
        old['sheet'].pop('npcTalentsConfigured')
        old['sheet']['pathRank'] = 1
        self.game.save(room)
        v = self.game.action(self.gs, dict(action='combatCreate', units=[dict(id=pc['id'], team='A'), dict(id=npc['id'], team='B')]))
        u = next(u for u in v['combat']['units'] if u['id'] == npc['id'])
        self.assertEqual(u['pathRank'], 0)
        self.assertEqual(u['paths'], {})

    def test_npc_talent_is_limited_to_one_activation_per_round(self):
        pc = self.make_pc()
        npc = self.make_npc()
        room = self.game.room(self.gs['room'])
        next(c for c in room['characters'] if c['id'] == npc['id'])['sheet']['kin'] = 'wolfkin'
        self.game.save(room)
        self.game.action(self.gs, dict(action='combatCreate', units=[dict(id=pc['id'], team='A'), dict(id=npc['id'], team='B')]))
        v = self.command(dict(action='start'))
        if v['combat']['order'][v['combat']['turn']] != npc['id']:
            self.command(dict(action='end'))
        ability = dict(action='kinAbility', unit=npc['id'], ability='prey', target=pc['id'], wp=1, visible=True)
        v = self.command(ability)
        u = next(u for u in v['combat']['units'] if u['id'] == npc['id'])
        self.assertEqual((u['prey']['bonus'], u['wp'], u['talentUsedRound']), (1, 0, 1))
        with self.assertRaises(ValueError):
            self.command(ability)

    def test_manual_orc_choice_is_immediate_and_owned(self):
        pc = self.make_pc()
        npc = self.make_npc()
        room = self.game.room(self.gs['room'])
        hero = next(c for c in room['characters'] if c['id'] == pc['id'])
        hero['sheet']['kin'] = 'orc'
        hero['runtime']['wp'] = 4
        self.game.save(room)
        self.game.action(self.gs, dict(action='combatCreate', units=[dict(id=pc['id'], team='A'), dict(id=npc['id'], team='B')]))
        self.command(dict(action='start'))
        def damage():
            return self.game.action(self.gs, dict(action='combatManual', revision=self.game.view(self.gs)['combatRevision'], actor=npc['id'], target=pc['id'], attribute='str', damage=99, note='Проверка ручного урона', slow=False))
        v = damage()
        self.assertEqual(v['combat']['manualOrcWindow'], dict(actor=pc['id'], attribute='str'))
        ability = dict(action='kinAbility', unit=pc['id'], ability='orc', attribute='str', wp=2)
        with self.assertRaises(ValueError):
            self.command({**ability, 'attribute': 'agi'}, self.ps)
        v = self.command(ability, self.ps)
        self.assertNotIn('manualOrcWindow', v['combat'])
        self.assertEqual(next(u for u in v['combat']['units'] if u['id'] == pc['id'])['str'], 2)
        damage()
        self.command(dict(action='defense', unit=npc['id'], value='none'))
        with self.assertRaises(ValueError):
            self.command(ability, self.ps)


if __name__ == '__main__':
    unittest.main()
