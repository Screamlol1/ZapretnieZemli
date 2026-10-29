import copy
import json
import subprocess
import tempfile
import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]))
from server import Game
from save_points import apply as saves


class ProgressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sheet=json.loads(subprocess.check_output(['node','--input-type=module','-e',"import {blank} from './public/tools/rules.js';const s=blank();s.name='Герой';s.skills.melee=3;s.skills.heal=1;console.log(JSON.stringify(s));"],cwd=Path(__file__).parents[1],text=True,encoding='utf-8'))

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'game.sqlite';self.game=Game(self.path)
        accounts=self.game.accounts
        def account(login):
            token,_=accounts.auth('register',dict(login=login,password='test password long enough'))
            return accounts.authenticate(token)
        self.ga=account('master');self.pa=account('player')
        gm=accounts.campaign(self.ga,dict(title='Развитие'),True);self.code=gm['code'];self.gm=self.game.session(gm['token'])
        player=accounts.campaign(self.pa,dict(code=self.code,key=gm['playerKey']));self.player=self.game.session(player['token'])
        self.game.action(self.player,dict(action='character',id='hero',sheet=self.sheet))
        self.lid=accounts.character(self.pa,dict(action='capture',code=self.code,character='hero'))['id']

    def tearDown(self):self.game.db.close();self.tmp.cleanup()
    def hero(self):return next(c for c in self.game.room(self.code)['characters'] if c['id']=='hero')
    def act(self,operation,actor=None,**data):
        revision=self.hero()['sheet'].get('progression',{}).get('revision',0)
        return self.game.action(actor or self.gm,dict(action='characterProgression',id='hero',revision=revision,operation=operation,**data))
    def start(self,amount=100):
        self.act('award',amount=amount,note='Итоги прошлых встреч')
        self.act('rest',confirmed=True,allowed=True,note='Отдых в цитадели')

    def test_player_advances_past_creation_caps_library_and_restart(self):
        self.start()
        self.act('advance',actor=self.player,skill='melee');self.act('advance',actor=self.player,skill='melee')
        self.act('advance',actor=self.player,skill='heal')
        p=self.hero()['sheet']['progression'];self.assertEqual(p['spent'],55)
        self.assertEqual(self.hero()['sheet']['skills']['melee'],5)
        with self.assertRaisesRegex(ValueError,'Максимальный'):self.act('advance',actor=self.player,skill='melee')
        saved=self.game.accounts.dashboard(self.pa)['characters'][0]
        self.assertEqual(saved['sheet'],self.hero()['sheet'])
        edited=copy.deepcopy(saved['sheet']);edited['notes']='Новая заметка'
        self.game.accounts.character(self.pa,dict(action='save',id=self.lid,version=saved['version'],sheet=edited))
        self.assertEqual(self.hero()['sheet']['progression']['spent'],55)
        self.game.db.close();self.game=Game(self.path)
        self.assertEqual(self.hero()['sheet']['skills']['heal'],2)

    def test_xp_permissions_stale_commands_and_editor_forgery(self):
        with self.assertRaises(PermissionError):self.act('award',actor=self.player,amount=100,note='Попытка')
        self.start(20);revision=self.hero()['sheet']['progression']['revision']
        self.act('advance',actor=self.player,skill='melee')
        with self.assertRaisesRegex(ValueError,'изменилось'):
            self.game.action(self.player,dict(action='characterProgression',id='hero',revision=revision,operation='advance',skill='melee'))
        with self.assertRaisesRegex(ValueError,'Недостаточно'):self.act('advance',actor=self.player,skill='melee')
        original=copy.deepcopy(self.hero()['sheet'])
        for change in ('earned','drop','base','talent','old'):
            fake=copy.deepcopy(original)
            if change=='earned':fake['progression']['earned']+=1
            if change=='drop':fake=copy.deepcopy(self.sheet)
            if change=='base':fake['attrs']['str']+=1
            if change=='talent':fake['talents']['lucky']=1
            if change=='old':fake['progression']['revision']-=1
            with self.assertRaises((ValueError,PermissionError)):
                self.game.action(self.player,dict(action='character',id='hero',sheet=fake))
        self.assertEqual(self.hero()['sheet'],original)
        with self.assertRaises(PermissionError):self.game.action(self.player,dict(action='character',sheet=original))

    def test_learning_requires_confirmed_basis_and_rest_expires(self):
        self.act('award',amount=20,note='Итоги встречи')
        with self.assertRaisesRegex(ValueError,'отдыха'):self.act('advance',actor=self.player,skill='heal')
        self.act('rest',allowed=True,confirmed=True,note='Ночлег в трактире')
        with self.assertRaisesRegex(ValueError,'учителя'):self.act('advance',actor=self.player,skill='lore')
        with self.assertRaises(PermissionError):self.act('training',actor=self.player,skill='lore',method='teacher',confirmed=True,note='Учитель')
        self.act('training',skill='lore',method='teacher',confirmed=True,note='Четверть с учителем')
        self.act('advance',actor=self.player,skill='lore')
        self.assertEqual(self.hero()['sheet']['skills']['lore'],1)
        room=self.game.room(self.code);room['journey']['cycleId']='next';self.game.save(room)
        with self.assertRaisesRegex(ValueError,'отдыха'):self.act('advance',actor=self.player,skill='lore')

    def test_account_action_and_atomic_rejections_during_combat_or_checks(self):
        self.start()
        entry=self.game.accounts.dashboard(self.pa)['characters'][0]
        self.game.accounts.character(self.pa,dict(action='progression',id=self.lid,version=entry['version'],revision=entry['sheet']['progression']['revision'],operation='advance',skill='heal'))
        with self.assertRaisesRegex(ValueError,'другой вкладке'):
            self.game.accounts.character(self.pa,dict(action='progression',id=self.lid,version=entry['version'],operation='advance',skill='heal'))
        original=copy.deepcopy(self.hero()['sheet'])
        for combat in (True,False):
            room=self.game.room(self.code);room['combat']={'phase':'combat' if combat else 'finished'};room['journey']['phase']='planning' if combat else 'resolving';self.game.save(room)
            with self.assertRaisesRegex(ValueError,'Завершите'):self.act('advance',actor=self.player,skill='heal')
            self.assertEqual(self.hero()['sheet'],original)

    def test_restore_invalidates_progression_commands(self):
        self.start();point=saves(self.game,self.gm,dict(operation='create',scope='campaign',label='До развития'))
        self.act('advance',actor=self.player,skill='melee');old=self.hero()['sheet']['progression']['revision']
        room=self.game.room(self.code)
        saves(self.game,self.gm,dict(operation='restore',scope='campaign',id=point['id'],revision=room['revision'],confirmed=True))
        p=self.hero()['sheet']['progression'];self.assertGreater(p['revision'],old);self.assertIsNone(p['restCycle'])
        self.assertEqual(self.hero()['sheet']['skills']['melee'],3)

    def test_training_session_scope_and_other_owner_permissions(self):
        self.start()
        self.act('training',skill='lore',method='success',confirmed=True,note='Успех в текущей сессии')
        self.act('training',skill='craft',method='teacher',confirmed=True,note='Четверть обучения')
        room=self.game.room(self.code);room['journey']['session']+=1;self.game.save(room)
        with self.assertRaisesRegex(ValueError,'учителя'):self.act('advance',actor=self.player,skill='lore')
        self.act('advance',actor=self.player,skill='craft')
        foreign=dict(self.player,owner='someone_else')
        with self.assertRaises(PermissionError):self.act('advance',actor=foreign,skill='heal')
        self.assertEqual(self.hero()['sheet']['progression']['spent'],5)

    def test_talents_rank_three_additional_paths_and_library_roundtrip(self):
        self.start(100)
        with self.assertRaisesRegex(ValueError,'практики'):
            self.act('talentAdvance',actor=self.player,kind='talent',talent='defender')
        self.act('talentTraining',kind='talent',talent='defender',method='teacher',teacherRank=1,confirmed=True,note='Четверть с защитником')
        for _ in range(3):self.act('talentAdvance',actor=self.player,kind='talent',talent='defender')
        self.assertEqual(self.hero()['sheet']['talents']['defender'],3)
        self.assertEqual(self.hero()['sheet']['progression']['spent'],18)
        self.act('talentTraining',kind='path',talent='enemy',method='teacher',teacherRank=1,confirmed=True,note='Учитель пути врага')
        self.act('talentAdvance',actor=self.player,kind='path',talent='enemy')
        self.act('talentAdvance',actor=self.player,kind='path',talent='blade')
        self.assertEqual(self.hero()['sheet']['paths'],dict(blade=2,enemy=1))
        self.assertEqual(self.hero()['sheet']['pathRank'],2)
        saved=self.game.accounts.dashboard(self.pa)['characters'][0]
        self.assertEqual(saved['sheet'],self.hero()['sheet'])
        self.game.db.close();self.game=Game(self.path)
        self.assertEqual(self.hero()['sheet']['progression']['spent'],27)
        with self.assertRaisesRegex(ValueError,'Максимальный'):self.act('talentAdvance',actor=self.player,kind='talent',talent='defender')
        with self.assertRaises(ValueError):self.act('talentAdvance',actor=self.player,kind='path',talent='blood')

    def test_magic_teacher_rank_and_tripled_cost(self):
        sheet=copy.deepcopy(self.sheet);sheet.update(profession='druid',path='healing',gear=['staff']);sheet['skills']={k:0 for k in sheet['skills']}
        self.game.action(self.player,dict(action='character',id='hero',sheet=sheet))
        self.start(100)
        self.act('talentAdvance',actor=self.player,kind='path',talent='healing')
        self.assertEqual(self.hero()['sheet']['progression']['spent'],18)
        with self.assertRaisesRegex(ValueError,'более высоким'):
            self.act('talentTraining',kind='path',talent='healing',method='teacher',teacherRank=2,confirmed=True,note='Недостаточный ранг')
        self.act('talentTraining',kind='path',talent='healing',method='teacher',teacherRank=3,confirmed=True,note='Наставник исцеления')
        self.act('talentAdvance',actor=self.player,kind='path',talent='healing')
        self.assertEqual(self.hero()['sheet']['progression']['spent'],27)
        self.act('talentTraining',kind='path',talent='sight',method='practice',success=True,confirmed=True,note='Четверть практики, Разум: успех')
        self.act('talentAdvance',actor=self.player,kind='path',talent='sight')
        self.assertEqual(self.hero()['sheet']['progression']['spent'],36)

    def test_practice_failure_quarter_limit_and_permission(self):
        self.start(100)
        args=dict(kind='talent',talent='defender',method='practice',success=False,confirmed=True,note='Разум: ни одного успеха')
        with self.assertRaises(PermissionError):self.act('talentTraining',actor=self.player,**args)
        self.act('talentTraining',**args)
        with self.assertRaisesRegex(ValueError,'уже учтена'):self.act('talentTraining',**{**args,'success':True})
        with self.assertRaisesRegex(ValueError,'практики'):self.act('talentAdvance',actor=self.player,kind='talent',talent='defender')
        room=self.game.room(self.code);room['journey']['cycleId']='new-quarter';self.game.save(room)
        self.act('talentTraining',**{**args,'success':True})
        self.act('rest',confirmed=True,allowed=True,note='Отдых после практики')
        self.act('talentAdvance',actor=self.player,kind='talent',talent='defender')
        with self.assertRaisesRegex(ValueError,'развития'):
            forged=copy.deepcopy(self.hero()['sheet']);forged['paths']['enemy']=3
            self.game.action(self.player,dict(action='character',id='hero',sheet=forged))
