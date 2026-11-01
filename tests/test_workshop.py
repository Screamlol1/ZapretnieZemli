import json
import unittest
import test_server as support

class WorkshopTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown

    def draft(self,kind='event',**fields):
        return dict(kind=kind,fields=dict(title='Тестовая заготовка',description='Видимый текст',secret='SECRET-WORKSHOP',**fields),locked=['title'],tables={},trace={})
    def save(self,draft=None):
        return self.game.action(self.gs,dict(action='workshopSave',draft=draft or self.draft()))['workshop'][-1]
    def publish(self,e,**data):return self.game.action(self.gs,dict(action='workshopPublish',id=e['id'],version=e['version'],**data))

    def test_library_is_private_and_player_cannot_mutate(self):
        e=self.save();self.assertNotIn('workshop',self.game.view(self.ps))
        for action in ('workshopSave','workshopDelete','workshopPublish'):
            with self.assertRaises(PermissionError):self.game.action(self.ps,dict(action=action,draft=self.draft(),id=e['id'],version=e['version']))
        self.assertNotIn('SECRET-WORKSHOP',json.dumps(self.game.view(self.ps)))

    def test_manual_values_custom_tables_and_versions(self):
        draft=self.draft();draft['tables']['title']=dict(name='Моя таблица',source='Таблица Мастера',dice='D66',rows='11-36 | Первый\n41-66 | Второй')
        e=self.save(draft);self.assertEqual(e['fields']['title'],'Тестовая заготовка');self.assertEqual(e['tables'],draft['tables'])
        self.game.action(self.gs,dict(action='workshopSave',id=e['id'],version=e['version'],draft=draft))
        with self.assertRaises(ValueError):self.publish(e)
        for rows in ('11-16 | Неполная','11-66 | Всё\n21-26 | Повтор','11-67 | Лишнее'):
            draft['tables']['title']['rows']=rows
            with self.assertRaises(ValueError):self.save(draft)

    def test_event_is_pending_private_and_invalidates_completion(self):
        e=self.save();room=self.game.room(self.gs['room']);room['journey'].update(completed={'gm':True},gmReady=True);self.game.save(room)
        v=self.publish(e);self.assertFalse(v['journey']['gmReady']);self.assertEqual(v['journey']['completed'],{})
        self.assertIn('SECRET-WORKSHOP',v['journey']['pending'][-1]['note'])
        player=self.game.view(self.ps);self.assertEqual(player['journey']['pending'],[]);self.assertNotIn('SECRET-WORKSHOP',json.dumps(player))
        fresh=v['workshop'][-1]
        with self.assertRaises(ValueError):self.publish(fresh)

    def test_map_place_is_hidden_and_existing_place_is_not_overwritten(self):
        e=self.save(self.draft('settlement',size='Посёлок на 50 жителей'));v=self.publish(e,x=2,y=3)
        cell=v['maps']['world']['2,3'];self.assertTrue(cell['siteHidden']);self.assertEqual(cell['note'],'Видимый текст')
        self.assertNotIn('SECRET-WORKSHOP',json.dumps(self.game.view(self.ps)))
        other=self.save(self.draft('ruin'))
        with self.assertRaises(ValueError):self.publish(other,x=2,y=3)
        self.assertEqual(self.game.view(self.gs)['maps']['world']['2,3']['siteType'],'settlement')

    def test_monster_saved_once_and_uses_actor_validation(self):
        e=self.save(self.draft('monster'))
        actor=dict(kind='monster',name='Чудовище теста',hidden=True,monster=dict(strength=10,agility=3,armor=2,notes='secret',attacks=[dict(name='Укус',dice=8,damage=1,range=1,type='physical',parry=False,dodge=True,note='')]*6))
        command=dict(action='actor',actor=actor,workshopId=e['id'],workshopVersion=e['version'])
        result=self.game.action(self.gs,command);self.assertEqual(result['characters'][-1]['monster']['strength'],10)
        self.assertEqual(result['workshop'][-1]['published']['id'],result['characters'][-1]['id'])
        with self.assertRaises(ValueError):self.game.action(self.gs,command)
        self.assertNotIn('Чудовище теста',json.dumps(self.game.view(self.ps),ensure_ascii=False))

    def test_library_deletion_does_not_remove_created_place(self):
        e=self.save(self.draft('ruin'));v=self.publish(e,x=1,y=1);e=v['workshop'][-1]
        v=self.game.action(self.gs,dict(action='workshopDelete',id=e['id'],version=e['version']))
        self.assertEqual(v['workshop'],[]);self.assertEqual(v['maps']['world']['1,1']['siteType'],'ruin')
