import copy
import json
import unittest
from unittest.mock import patch
import test_server as support


class ChangeHistoryTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown
    make_pc=support.CampaignTests.make_pc
    make_npc=support.CampaignTests.make_npc
    def room(self):return self.game.room(self.gs['room'])
    def latest(self,action=None):return next(e for e in reversed(self.room()['changeHistory']) if not action or e['action']==action)
    def undo(self,entry,session=None,**overrides):return self.game.action(session or self.gs,dict(action='changeUndo',id=entry['id'],revision=self.room()['revision'],note='Исправляю ошибочный выбор',**overrides))
    def paint(self,x,y,terrain='forest'):return self.game.action(self.gs,dict(action='paint',map='world',x=x,y=y,terrain=terrain,hidden=False))

    def test_undo_independent_map_edit_preserves_other_cell_and_survives_restart(self):
        self.paint(1,0);first=self.latest();self.paint(2,0,'hills')
        self.game.db.close();self.game=support.Game(self.path,reference_root=self.path.parent/'local-assets')
        self.undo(first)
        room=self.room();self.assertNotIn('1,0',room['maps']['world']);self.assertEqual(room['maps']['world']['2,0']['terrain'],'hills')
        with self.assertRaisesRegex(ValueError,'Уже отменено'):self.undo(first)

    def test_same_object_later_change_and_stale_commands_are_rejected_atomically(self):
        self.paint(1,0);first=self.latest();old_revision=self.room()['revision'];self.paint(1,0,'hills');before=copy.deepcopy(self.room()['maps'])
        with self.assertRaisesRegex(ValueError,'История изменилась'):
            self.game.action(self.gs,dict(action='changeUndo',id=first['id'],revision=old_revision,note='Старый запрос'))
        with self.assertRaisesRegex(ValueError,'позднее'):self.undo(first)
        self.assertEqual(self.room()['maps'],before)

    def test_private_before_after_and_permission_do_not_leak_to_players(self):
        self.game.action(self.gs,dict(action='mapLocation',x=1,y=0,label='Тайный храм',note='Публичный текст',gmNote='SECRET-HISTORY-TRAP',siteType='ruin',siteHidden=True));entry=self.latest()
        gm=self.game.view(self.gs);player=self.game.view(self.ps)
        self.assertIn('SECRET-HISTORY-TRAP',json.dumps(gm,ensure_ascii=False));self.assertNotIn('SECRET-HISTORY-TRAP',json.dumps(player,ensure_ascii=False))
        self.assertNotIn('changeHistory',player);self.assertNotIn('changeVersions',gm);self.assertNotIn('patches',gm['changeHistory'][-1]);self.assertNotIn('dependencies',gm['changeHistory'][-1])
        with self.assertRaises(PermissionError):self.undo(entry,session=self.ps)

    def test_new_external_character_reference_blocks_removing_hero(self):
        cid=self.make_pc()['id'];created=self.latest('character')
        self.game.action(self.gs,dict(action='token',map='world',x=1,y=0,characterId=cid,name='Герой'))
        with self.assertRaisesRegex(ValueError,'связанные'):self.undo(created)
        self.assertTrue(any(c['id']==cid for c in self.room()['characters']));self.assertEqual(self.room()['tokens'][0]['characterId'],cid)

    def test_inventory_open_is_dependency_even_though_not_an_audited_action(self):
        cid=self.make_pc()['id'];created=self.latest('character')
        self.game.action(self.ps,dict(action='inventoryOpen',character=cid))
        with self.assertRaises(ValueError):self.undo(created)
        self.assertTrue(self.room()['items']);self.assertTrue(self.room()['characters'])

    def test_consuming_item_in_later_check_blocks_undo_even_if_item_version_unchanged(self):
        cid=self.make_pc()['id'];self.game.action(self.ps,dict(action='inventoryOpen',character=cid))
        item=next(i for i in self.room()['items'] if i['location'].get('id')==cid and i['bonus']>0)
        self.game.action(self.gs,dict(action='itemWear',id=item['id'],version=item['version'],wear=0,note='Проверка состояния'))
        entry=self.latest('itemWear')
        # Ensure the action has a real reversible item change.
        if not entry['patches']:
            item=next(i for i in self.room()['items'] if i['id']==item['id'])
            self.game.action(self.gs,dict(action='itemWear',id=item['id'],version=item['version'],wear=1,note='Повреждение'))
            entry=self.latest('itemWear')
        item=next(i for i in self.room()['items'] if i['id']==item['id'])
        with patch('skill_checks.die',return_value=6):
            view=self.game.action(self.ps,dict(action='characterRoll',character=cid,skill='melee',revision=self.room()['revision'],item=item['id'],itemVersion=item['version']))
        check=next(c for c in view['characters'] if c['id']==cid)['runtime']['lastCheck']
        self.game.action(self.ps,dict(action='characterAccept',character=cid,roll=check['id']))
        with self.assertRaisesRegex(ValueError,'связанные'):self.undo(entry)

    def test_stale_check_does_not_lock_all_history_but_live_check_does(self):
        cid=self.make_pc()['id']
        with patch('skill_checks.die',return_value=2):self.game.action(self.ps,dict(action='characterRoll',character=cid,skill='heal',revision=self.room()['revision']))
        self.paint(1,0);self.assertFalse(self.game.view(self.gs)['changeHistory'][-1]['canUndo'])
        room=self.room();next(c for c in room['characters'] if c['id']==cid)['runtime']['wp']=1;self.game.save(room)
        self.paint(2,0);entry=self.latest();self.assertTrue(self.game.view(self.gs)['changeHistory'][-1]['canUndo']);self.undo(entry)
        self.assertNotIn('2,0',self.room()['maps']['world'])
