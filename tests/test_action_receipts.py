import concurrent.futures
import json
import threading
import unittest
import urllib.request
import urllib.error
import uuid
from unittest.mock import patch
import test_server as support


class ActionReceiptsTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown

    def command(self,**payload):return dict(requestId=str(uuid.uuid4()),**payload)
    def status(self,s,data):return self.game.action_status(s,dict(requestId=data['requestId']))

    def test_random_roll_retries_do_not_roll_again_and_return_current_view(self):
        data=self.command(action='roll',base=3,skill=1,gear=0,modifier=0)
        with patch('server.secrets.randbelow',return_value=5) as rng:
            first=self.game.action(self.ps,data)
            self.game.action(self.gs,dict(action='chat',text='После броска'))
            duplicate=self.game.action(self.ps,data)
        self.assertEqual(rng.call_count,4)
        self.assertEqual(duplicate['diceRolls'],first['diceRolls'])
        self.assertGreater(duplicate['revision'],first['revision'])
        self.assertEqual(self.status(self.ps,data)['status'],'applied')
        self.assertNotIn('gmKey',duplicate)
        self.assertNotIn('action_receipts',duplicate)

    def test_concurrent_duplicate_nonrandom_command_applies_once(self):
        data=self.command(action='chat',text='Одно сообщение')
        before=self.game.view(self.ps)['revision']
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.game.action(self.ps,data),range(2)))
        self.assertEqual(results[0]['revision'],before+1)
        self.assertEqual(results[1]['revision'],before+1)
        self.assertEqual(sum(e['text']=='Одно сообщение' for e in results[1]['log']),1)

    def test_collision_rejected_and_receipts_scoped_to_owner(self):
        data=self.command(action='chat',text='Первое')
        self.game.action(self.ps,data)
        with self.assertRaises(ValueError):self.game.action(self.ps,{**data,'text':'Подмена'})
        self.assertEqual(self.status(self.gs,data)['status'],'missing')
        self.game.action(self.gs,{**data,'text':'Другой владелец'})
        self.assertEqual(self.status(self.gs,data)['status'],'applied')

    def test_restart_and_resume_preserve_receipt_and_privacy(self):
        data=self.command(action='roll',base=1,visibility='hidden')
        first=self.game.action(self.gs,data)
        event=first['diceRolls'][-1]['id']
        self.game.db.close()
        self.game=support.Game(self.path,reference_root=self.path.parent/'local-assets')
        restored=self.game.reconnect(dict(code=self.gm['code'],resume=self.gm['resume']))
        self.gs=self.game.session(restored['token'])
        self.assertEqual(self.status(self.gs,data)['status'],'applied')
        self.assertEqual(self.game.action(self.gs,data)['diceRolls'][-1]['id'],event)
        player=self.game.reconnect(dict(code=self.player['code'],resume=self.player['resume']))
        self.ps=self.game.session(player['token'])
        status=self.status(self.ps,data)
        self.assertEqual(status['status'],'missing')
        self.assertFalse(status['state']['diceRolls'])

    def test_invalid_action_and_failed_save_leave_no_receipt_or_mutation(self):
        bad=self.command(action='paint',map='battle',x=1,y=1,terrain='wall')
        with self.assertRaises(PermissionError):self.game.action(self.ps,bad)
        self.assertEqual(self.status(self.ps,bad)['status'],'missing')
        data=self.command(action='chat',text='Не должно сохраниться')
        before=self.game.view(self.ps)['revision']
        # Failure after writing the room, before commit (during account sync).
        with patch.object(self.game.accounts,'sync',side_effect=RuntimeError('disk write failed')):
            with self.assertRaises(RuntimeError):self.game.action(self.ps,data)
        self.assertEqual(self.status(self.ps,data)['status'],'missing')
        self.assertEqual(self.game.view(self.ps)['revision'],before)
        self.game.action(self.ps,data)
        self.assertEqual(self.game.view(self.ps)['revision'],before+1)

    def test_canonical_payload_and_identifier_validation(self):
        data=self.command(action='chat',text='Один раз')
        first=self.game.action(self.ps,data)
        reordered=dict(reversed(list(data.items())))
        reordered['requestId']=data['requestId'].upper()
        self.assertEqual(self.game.action(self.ps,reordered)['revision'],first['revision'])
        for value in ('',None,12,'x'*100,'../../a'):
            with self.assertRaises(ValueError):self.game.action(self.ps,dict(action='chat',text='x',requestId=value))
            with self.assertRaises(ValueError):self.game.action_status(self.ps,dict(requestId=value))

    def test_http_status_requires_session_and_never_replays_command(self):
        server=support.ThreadingHTTPServer(('127.0.0.1',0),support.make_handler(self.game))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:'+str(server.server_port)
        data=self.command(action='chat',text='Проверка соединения')
        def post(path,payload,token=''):
            request=urllib.request.Request(base+'/api/'+path,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Authorization':token})
            with urllib.request.urlopen(request) as response:return json.load(response)
        try:
            with self.assertRaises(urllib.error.HTTPError) as error:post('action-status',dict(requestId=data['requestId']))
            self.assertEqual(error.exception.code,403)
            error.exception.close()
            before=post('action-status',dict(requestId=data['requestId']),self.player['token'])
            self.assertEqual(before['status'],'missing')
            first=post('action',data,self.player['token'])
            status=post('action-status',dict(requestId=data['requestId']),self.player['token'])
            self.assertEqual(status['status'],'applied')
            self.assertEqual(status['state']['revision'],first['revision'])
            self.assertEqual(post('action',data,self.player['token'])['revision'],first['revision'])
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
