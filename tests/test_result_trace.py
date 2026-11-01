import unittest
import copy
import uuid
import test_server as support
from result_trace import dice_calculation, record, snapshot, project


class CalculationTests(unittest.TestCase):
    def test_penalty_and_artifacts_keep_their_own_dice(self):
        event={'groups':[{'kind':'skill','label':'Навык','sides':6,'values':[6,6,2]}, {'kind':'penalty','label':'Штраф','sides':6,'values':[6,2],'negative':True}, {'kind':'artifact','label':'Артефакты','sides':12,'values':[12,10,8,6]}]}
        result=dice_calculation(event)
        self.assertEqual((result['positive'],result['negative'],result['net']),(12,1,11))
        self.assertEqual([r['count'] for r in result['rows']],[3,2,4])
        event['groups']=[{'kind':'table','label':'D66','sides':6,'values':[6,6]}]
        self.assertIsNone(dice_calculation(event)['net'])

    def test_resource_deltas_hide_unavailable_items_and_characters(self):
        room={'characters':[{'id':'hero','name':'Герой','runtime':{'current':{'str':4},'wp':0}},{'id':'hidden','name':'Секрет','runtime':{'current':{'str':4}}}],'items':[{'id':'secret-item','name':'SECRET','wear':0}],'diceRolls':[]}
        before=snapshot(room);room['characters'][0]['runtime']['wp']=1;room['characters'][1]['runtime']['current']['str']=3;room['items'][0]['wear']=1
        room['diceRolls']=[{'id':'roll','groups':[{'kind':'base','label':'Характеристика','sides':6,'values':[1,6],'held':[True,True]}]}]
        record(room,before,{})
        self.assertEqual(len(room['diceRolls'][0]['calculation']['effects']),3)
        room['characters']=room['characters'][:1];room['items']=[];project(room,{'role':'player'})
        self.assertEqual(room['diceRolls'][0]['calculation']['effects'],[{'kind':'character','id':'hero','name':'Герой','label':'Сила воли','delta':1}])


class CalculationReceiptTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown

    def test_retry_does_not_roll_or_record_twice(self):
        data=dict(action='roll',base=2,skill=2,gear=1,modifier=-1,requestId=str(uuid.uuid4()))
        first=self.game.action(self.ps,data);second=self.game.action(self.ps,data)
        self.assertEqual(first['diceRolls'],second['diceRolls'])
        self.assertEqual(len(second['diceRolls']),1)
        self.assertIn('calculation',second['diceRolls'][0])
