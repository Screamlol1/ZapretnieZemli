import unittest
import test_journey as support


class JournalTests(unittest.TestCase):
    setUp=support.JourneyTests.setUp
    tearDown=support.JourneyTests.tearDown
    act=support.JourneyTests.act

    def test_new_entries_have_server_date_and_old_entries_remain_undated(self):
        room=self.game.room(self.gm['room'])
        room['log']=[dict(name='Мастер',text='Старая запись')]
        self.game.save(room)
        view=self.act('chat',session=self.player,text='Привал',day=999,kind='decision')
        old,new=view['log']
        self.assertNotIn('day',old)
        self.assertEqual((new['kind'],new['day'],new['quarter']),('chat',1,0))
        self.assertIsInstance(new['time'],float)
        stamp=new['time']
        self.act('roll',base=2,skill=1,gear=0)
        again=self.game.view(self.player)['log']
        self.assertEqual(again[1]['time'],stamp)
        self.assertEqual(again[-1]['kind'],'check')

    def test_private_resolution_never_gets_a_public_journal_entry(self):
        self.act('travelEvent',location='journey')
        event=self.game.view(self.gm)['journey']['pending'][-1]
        self.act('travelResolve',id=event['id'],note='SECRET_JOURNAL_NOTE',reveal=False)
        self.assertNotIn('SECRET_JOURNAL_NOTE',str(self.game.view(self.player)))
        self.act('travelEvent',location='journey')
        event=self.game.view(self.gm)['journey']['pending'][-1]
        self.act('travelResolve',id=event['id'],note='Открытая развязка',reveal=True)
        entry=self.game.view(self.player)['log'][-1]
        self.assertEqual(entry['kind'],'decision')
        self.assertIn('Открытая развязка',entry['text'])
