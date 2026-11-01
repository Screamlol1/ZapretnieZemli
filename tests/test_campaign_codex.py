import copy
import unittest
import json
import threading
import urllib.request
import urllib.error
import uuid
from unittest.mock import patch
import test_server as support
import campaign_codex as codex

class CampaignCodexTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown

    def send(self,s=None,**data):
        s=s or self.gs
        return self.game.action(s,dict(action='campaignCodex',version=self.game.view(s)['codex']['version'],**data))

    def test_recipient_secrets_graph_and_persistence(self):
        owner=self.ps['owner']
        self.send(op='save',entry=dict(kind='faction',title='Тайный союз',secret='PRIVATE',visibility='gm'))
        hidden=self.game.view(self.gs)['codex']['entries'][0]['id']
        self.send(op='save',entry=dict(kind='handout',title='Письмо',text='Публичная часть',secret='PRIVATE',visibility='owners',recipients=[owner]))
        public=self.game.view(self.ps)['codex']['entries'][0]
        self.assertNotIn('secret',public);self.assertNotIn('recipients',public)
        self.send(op='relation',**{'from':hidden,'to':public['id']},label='Улика')
        self.assertEqual(self.game.view(self.ps)['codex']['relations'],[])
        self.send(op='save',id=public['id'],entry=dict(kind='handout',title='Письмо',visibility='gm'))
        self.assertEqual(self.game.view(self.ps)['codex']['entries'],[])
        self.assertEqual(len(self.game.room(self.gs['room'])['codex']['entries']),2)

    def test_player_notes_permissions_stale_versions_and_delete_edges(self):
        self.send(self.ps,op='save',entry=dict(kind='clue',title='<script>Улика</script>',visibility='all'))
        item=self.game.view(self.ps)['codex']['entries'][0]
        with self.assertRaises(PermissionError):self.send(self.ps,op='save',entry=dict(kind='faction',title='Нельзя'))
        with self.assertRaises(ValueError):self.game.action(self.ps,dict(action='campaignCodex',version=0,op='delete',id=item['id']))
        self.assertEqual(self.game.view(self.ps)['codex']['entries'][0]['title'],'<script>Улика</script>')
        self.send(self.ps,op='delete',id=item['id']);self.assertEqual(self.game.view(self.ps)['codex']['entries'],[])

    def test_gm_only_overrides_original_authorship_for_text_media_and_writes(self):
        png='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aC1cAAAAASUVORK5CYII='
        self.send(self.ps,op='save',entry=dict(kind='note',title='Заметка игрока',visibility='owners'))
        entry=self.game.view(self.ps)['codex']['entries'][0]
        for kind in ('note','handout'):
            self.send(op='save',id=entry['id'],entry=dict(kind=kind,title='Теперь только Мастер',visibility='gm',**(dict(image=png) if kind=='handout' else {})))
            self.assertEqual(self.game.view(self.ps)['codex']['entries'],[])
            before=copy.deepcopy(self.game.room(self.gs['room']))
            with self.assertRaises(PermissionError):codex.media(before,self.ps,entry['id'])
            with self.assertRaises(PermissionError):self.send(self.ps,op='save',id=entry['id'],entry=dict(kind='note',title='Попытка раскрыть',visibility='all'))
            with self.assertRaises(PermissionError):self.send(self.ps,op='delete',id=entry['id'])
            self.assertEqual(self.game.room(self.gs['room']),before)
        self.assertEqual(codex.media(self.game.room(self.gs['room']),self.gs,entry['id'])['image'],png)
        for visibility in ('owners','all'):
            self.send(op='save',id=entry['id'],entry=dict(kind='note',title='Вернуть автору',visibility=visibility,removeImage=True))
            public=self.game.view(self.ps)['codex']['entries'][0]
            self.assertTrue(public['canEdit']);self.assertEqual(public['author'],self.ps['owner'])

    def test_invalid_media_and_recipients_are_atomic(self):
        before=copy.deepcopy(self.game.room(self.gs['room']))
        for entry in [dict(kind='handout',title='X',image='data:image/svg+xml,<svg/>'),dict(kind='note',title='X',recipients=['unknown']),dict(kind='note',title='X',tags=['x'*31])]:
            with self.assertRaises(ValueError):self.send(op='save',entry=entry)
        self.assertEqual(self.game.room(self.gs['room']),before)

    def test_media_authorization_revoke_and_receipt_survive_restart(self):
        png='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aC1cAAAAASUVORK5CYII='
        data=dict(action='campaignCodex',op='save',version=0,requestId=str(uuid.uuid4()),entry=dict(kind='handout',title='Личное письмо',image=png,visibility='owners',recipients=[self.ps['owner']]))
        self.game.action(self.gs,data);self.game.action(self.gs,data)
        self.assertEqual(len(self.game.view(self.gs)['codex']['entries']),1)
        entry=self.game.view(self.ps)['codex']['entries'][0]
        self.assertNotIn('imageData',entry);self.assertTrue(entry['hasImage'])
        self.game.db.close();self.game=support.Game(self.path)
        self.game.action(self.gs,data)
        self.assertEqual(codex.media(self.game.room(self.gs['room']),self.ps,entry['id'])['image'],png)
        other=self.game.login(dict(name='Другой',code=self.gm['code'],key=self.gm['playerKey']))
        self.game.sessions[self.player['token']]=self.ps
        server=support.ThreadingHTTPServer(('127.0.0.1',0),support.make_handler(self.game));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            url=f'http://127.0.0.1:{server.server_port}/api/codex-media?id='+entry['id']
            with urllib.request.urlopen(urllib.request.Request(url,headers={'Authorization':self.player['token']})) as r:self.assertEqual(json.load(r)['image'],png)
            for token in ('',other['token']):
                with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(urllib.request.Request(url,headers={'Authorization':token}))
                self.assertIn(error.exception.code,(401,403))
                error.exception.close()
            self.send(op='save',id=entry['id'],entry=dict(kind='handout',title='Личное письмо',visibility='gm'))
            with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(urllib.request.Request(url,headers={'Authorization':self.player['token']}))
            error.exception.close()
        finally:server.shutdown();server.server_close();thread.join()

    def test_checkpoint_invalidates_old_library_and_rules_forms(self):
        import save_points
        self.send(op='save',entry=dict(kind='note',title='До отката',visibility='gm'))
        checkpoint=save_points.apply(self.game,self.gs,dict(operation='create',scope='campaign',label='Начало'))
        old=self.game.view(self.gs)
        self.send(op='save',entry=dict(kind='note',title='После',visibility='gm'))
        restored=save_points.apply(self.game,self.gs,dict(operation='restore',scope='campaign',id=checkpoint['id'],revision=self.game.view(self.gs)['revision'],confirmed=True))['state']
        self.assertEqual([e['title'] for e in restored['codex']['entries']],['До отката'])
        self.assertGreater(restored['codex']['version'],old['codex']['version'])
        self.assertGreater(restored['rulePassport']['revision'],old['rulePassport']['revision'])
        with self.assertRaises(ValueError):self.game.action(self.gs,dict(action='campaignCodex',op='save',version=old['codex']['version'],entry=dict(kind='note',title='Устаревшее')))

    def test_legacy_checkpoint_without_codex_or_passport_invalidates_zero_version_forms(self):
        import save_points
        checkpoint=save_points.apply(self.game,self.gs,dict(operation='create',scope='campaign',label='Старая версия'))
        legacy=checkpoint['document']
        legacy['state'].pop('codex',None);legacy['state'].pop('rulePassport',None)
        self.game.db.execute('UPDATE checkpoints SET data=? WHERE id=?',(json.dumps(legacy),checkpoint['id']));self.game.db.commit()
        self.send(op='save',entry=dict(kind='note',title='После сохранения',visibility='gm'))
        before=self.game.view(self.gs)
        restored=save_points.apply(self.game,self.gs,dict(operation='restore',scope='campaign',id=checkpoint['id'],revision=before['revision'],confirmed=True))['state']
        self.assertEqual(restored['codex']['entries'],[])
        self.assertGreater(restored['codex']['version'],before['codex']['version'])
        self.assertGreater(restored['rulePassport']['revision'],before['rulePassport']['revision'])
        with self.assertRaises(ValueError):self.game.action(self.gs,dict(action='campaignCodex',op='save',version=0,entry=dict(kind='note',title='Старая форма',visibility='gm')))
        with self.assertRaises(ValueError):self.game.action(self.gs,dict(action='rulePassport',op='configure',revision=0,modules=restored['rulePassport']['modules'],note='Старая форма'))

    def test_failed_account_sync_rolls_back_codex_and_receipt_then_retry_once(self):
        import action_receipts
        before=copy.deepcopy(self.game.room(self.gs['room']))
        data=dict(action='campaignCodex',op='save',version=0,requestId=str(uuid.uuid4()),entry=dict(kind='note',title='Атомарная запись',visibility='gm'))
        with patch.object(self.game.accounts,'sync',side_effect=RuntimeError('injected save failure')):
            with self.assertRaises(RuntimeError):self.game.action(self.gs,data)
        self.assertEqual(self.game.room(self.gs['room']),before)
        self.assertEqual(action_receipts.status(self.game.db,self.gs,data['requestId']),'missing')
        self.game.action(self.gs,data);self.game.action(self.gs,data)
        self.assertEqual(len(self.game.view(self.gs)['codex']['entries']),1)
        self.assertEqual(action_receipts.status(self.game.db,self.gs,data['requestId']),'applied')

