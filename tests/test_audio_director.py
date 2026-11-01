import copy
import json
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
import test_server as support
import audio_director
import save_points


class AudioDirectorTests(unittest.TestCase):
    setUp=support.CampaignTests.setUp
    tearDown=support.CampaignTests.tearDown

    def call(self,session=None,**data):
        return self.game.action(session or self.gs,dict(action='audioDirector',**data))

    def test_old_room_defaults_permissions_invalids_and_stale_versions(self):
        expected=dict(version=0,ambient='auto',cues=[])
        self.assertEqual(self.game.view(self.gs)['audioDirector'],expected)
        self.assertEqual(self.game.view(self.ps)['audioDirector'],expected)
        before=self.game.room(self.gs['room'])
        for data in (dict(op='ambient',version=0,ambient='forest'),dict(op='cue',cue='bell')):
            with self.assertRaises(PermissionError):self.call(self.ps,**data)
        for data in (dict(op='unknown'),dict(op='ambient',version=True,ambient='forest'),
                     dict(op='ambient',version=0,ambient=[]),dict(op='ambient',version=0,ambient='https://sound.test/a.mp3'),
                     dict(op='cue',cue='auto'),dict(op='cue',cue={}),dict(op='cue',cue='https://sound.test/a.mp3')):
            with self.assertRaises(ValueError):self.call(**data)
        self.assertEqual(self.game.room(self.gs['room']),before)
        actual=self.call(op='ambient',version=0,ambient='forest')['audioDirector']
        self.assertEqual(actual,dict(version=1,ambient='forest',cues=[]))
        with self.assertRaises(ValueError):self.call(op='ambient',version=0,ambient='battle')
        self.assertEqual(self.game.view(self.ps)['audioDirector'],actual)

    def test_cues_are_bounded_public_ephemeral_and_not_game_history(self):
        before=copy.deepcopy(self.game.room(self.gs['room']))
        with patch('audio_director.time.time',return_value=1000) as clock:
            for i in range(14):
                clock.return_value=1000+i
                result=self.call(op='cue',cue='bell')
            stored=self.game.room(self.gs['room'])['audioDirector']
            self.assertEqual(len(stored['cues']),12)
            self.assertEqual(len(result['audioDirector']['cues']),9)
            event=result['audioDirector']['cues'][-1]
            self.assertEqual(set(event),{'id','type','at'})
            self.assertEqual(event['type'],'bell');self.assertEqual(event['at'],1013)
            self.assertEqual(result['audioDirector'],self.game.view(self.ps)['audioDirector'])
            self.assertNotIn('lastCueAt',result['audioDirector'])
            clock.return_value=1021.01
            self.assertEqual(self.game.view(self.ps)['audioDirector']['cues'],[])
            snapshot=save_points.capture(self.game.room(self.gs['room']),'campaign')
            self.assertEqual(snapshot['audioDirector']['cues'],[])
            self.assertNotIn('lastCueAt',snapshot['audioDirector'])
        after=self.game.room(self.gs['room'])
        self.assertEqual(after['log'],before['log'])
        self.assertEqual(after.get('changeHistory',[]),before.get('changeHistory',[]))

    def test_request_replay_precedes_cooldown_and_does_not_rebroadcast(self):
        request=dict(op='cue',cue='thunder',requestId=str(uuid.uuid4()))
        with patch('audio_director.time.time',return_value=1000) as clock:
            first=self.call(**request)
            self.assertEqual(self.call(**request)['audioDirector'],first['audioDirector'])
            self.assertEqual(self.game.room(self.gs['room'])['revision'],first['revision'])
            with self.assertRaises(ValueError):self.call(op='cue',cue='bell')
            with self.assertRaises(ValueError):self.call(**{**request,'cue':'bell'})
            clock.return_value=1000.79
            with self.assertRaises(ValueError):self.call(op='cue',cue='bell')
            clock.return_value=1000.81
            self.assertEqual(self.call(op='cue',cue='bell')['audioDirector']['version'],2)
            clock.return_value=1009
            replay=self.call(**request)
            self.assertEqual(replay['audioDirector']['cues'],[])
            self.assertEqual(replay['audioDirector']['version'],2)

    def test_ambience_and_request_receipts_survive_restart_without_cue_replay(self):
        with patch('audio_director.time.time',return_value=1000) as clock:
            self.call(op='ambient',version=0,ambient='tavern')
            request=dict(op='cue',cue='bell',requestId=str(uuid.uuid4()))
            self.call(**request)
            self.game.db.close();self.game=support.Game(self.path,reference_root=Path(self.tmp.name)/'local-assets')
            auth=self.game.reconnect(dict(code=self.gm['code'],resume=self.gm['resume']));self.gs=self.game.session(auth['token'])
            clock.return_value=1009
            state=self.call(**request)['audioDirector']
            self.assertEqual(state,dict(version=2,ambient='tavern',cues=[]))

    def test_restore_clears_cues_and_advances_version_beyond_both_timelines(self):
        with patch('audio_director.time.time',return_value=1000) as clock:
            self.call(op='ambient',version=0,ambient='forest')
            self.call(op='cue',cue='wolf')
            point=save_points.apply(self.game,self.gs,dict(operation='create',scope='campaign',label='Лес'))
            self.call(op='ambient',version=2,ambient='battle')
            clock.return_value=1001
            request=dict(op='cue',cue='metal',requestId=str(uuid.uuid4()))
            current=self.call(**request)
            restored=save_points.apply(self.game,self.gs,dict(operation='restore',scope='campaign',id=point['id'],confirmed=True,revision=current['revision']))['state']
            expected=dict(version=5,ambient='forest',cues=[])
            self.assertEqual(restored['audioDirector'],expected)
            self.assertEqual(self.call(**request)['audioDirector'],expected)
            with self.assertRaises(ValueError):self.call(op='ambient',version=4,ambient='silent')

    def test_presentational_controls_do_not_resolve_or_block_pending_checks(self):
        room=self.game.room(self.gs['room'])
        for key in ('afflictionCheck','expeditionCheck','waterCheck','coldCheck','treatment','journeyRisk'):
            room[key]=dict(id=key,private=True,actor='pending-actor')
        room['combat']=dict(phase='combat',round=1,units=[],pendingRisk=dict(id='battle-choice',private=True))
        room['magicCastings']=[dict(id='spell',status='rolled',private=True)]
        self.game.save(room)
        pending={key:copy.deepcopy(room[key]) for key in ('afflictionCheck','expeditionCheck','waterCheck','coldCheck','treatment','journeyRisk','combat','magicCastings')}
        self.assertEqual(self.call(op='ambient',version=0,ambient='silent')['audioDirector']['ambient'],'silent')
        self.assertEqual(self.call(op='cue',cue='magic')['audioDirector']['cues'][0]['type'],'magic')
        after=self.game.room(self.gs['room'])
        for key,value in pending.items():self.assertEqual(after[key],value,key)
        with self.assertRaises(PermissionError):self.call(self.ps,op='cue',cue='bell')
        with self.assertRaises(ValueError):self.game.action(self.gs,dict(action='event'))


if __name__=='__main__':unittest.main()
