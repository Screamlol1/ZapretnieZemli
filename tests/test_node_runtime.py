import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import unquote

sys.path.insert(0,str(Path(__file__).parents[1]))
import node_runtime
from server import Game
import progression


class NodeRuntimeTests(unittest.TestCase):
    def test_explicit_runtime_does_not_depend_on_path_or_working_directory(self):
        node=Path(shutil.which('node')).resolve()
        with tempfile.TemporaryDirectory(prefix='ЗЗ runtime ~ ') as folder:
            script=Path(folder)/'скрипт с пробелами.mjs'
            script.write_text("process.stdout.write(JSON.stringify({text:process.argv[2],file:import.meta.url}));",encoding='utf-8')
            with patch.dict(os.environ,{'ZZ_NODE':str(node),'PATH':''}):
                result=node_runtime.run_node([str(script),'Сохранённый герой & карта'],cwd=folder,text=True,capture_output=True,encoding='utf-8',check=True,timeout=8)
            data=json.loads(result.stdout)
            self.assertEqual(data['text'],'Сохранённый герой & карта')
            # Node and pathlib may encode '~' differently (Windows short paths).
            # Compare the same decoded file URL while retaining the path check.
            self.assertEqual(unquote(data['file']),unquote(script.as_uri()))

    def test_windows_console_is_hidden_and_existing_flags_are_preserved(self):
        with patch.dict(os.environ,{},clear=True),patch.object(node_runtime.os,'name','nt'),patch.object(subprocess,'CREATE_NO_WINDOW',0x08000000,create=True),patch('node_runtime.subprocess.run') as run:
            run.return_value='result'
            self.assertEqual(node_runtime.run_node(['--version'],capture_output=True,creationflags=0x20),'result')
            command=run.call_args.args[0];options=run.call_args.kwargs
            self.assertEqual(command,['node','--version'])
            self.assertEqual(options['creationflags'],0x08000020)
            self.assertTrue(options['capture_output']);self.assertFalse(options.get('shell'))

    def test_non_windows_does_not_receive_windows_process_flags(self):
        with patch.dict(os.environ,{},clear=True),patch.object(node_runtime.os,'name','posix'),patch('node_runtime.subprocess.run') as run:
            node_runtime.run_node(['--version'])
            self.assertNotIn('creationflags',run.call_args.kwargs)

    def test_malformed_runtime_is_not_interpreted_as_a_shell_command(self):
        with patch('node_runtime.subprocess.run') as run:
            with patch.dict(os.environ,{'ZZ_NODE':'relative/node.exe'}):
                with self.assertRaises(OSError):node_runtime.run_node(['--version'])
            with self.assertRaises(ValueError):node_runtime.run_node(['--version'],shell=True)
            with self.assertRaises(TypeError):node_runtime.run_node('--version & whoami')
            run.assert_not_called()

    def test_campaign_validation_inventory_actor_combat_and_catalog_without_path(self):
        node=Path(shutil.which('node')).resolve();root=Path(__file__).parents[1]
        blank=node_runtime.run_node(['--input-type=module','-e',"import {blank} from './public/tools/rules.js';process.stdout.write(JSON.stringify({...blank(),name:'Герой Windows'}));"],cwd=root,text=True,capture_output=True,encoding='utf-8',check=True,timeout=8)
        sheet=json.loads(blank.stdout)
        with tempfile.TemporaryDirectory(prefix='ЗЗ данные ') as folder:
            database=Path(folder)/'campaigns.sqlite';game=Game(database,reference_root=Path(folder)/'local-assets')
            try:
                gm=game.login(dict(name='Мастер'),True);gs=game.session(gm['token'])
                login=game.login(dict(name='Игрок',code=gm['code'],key=gm['playerKey']));ps=game.session(login['token'])
                with patch.dict(os.environ,{'ZZ_NODE':str(node),'PATH':''}):
                    v=game.action(ps,dict(action='character',id='windows-hero',sheet=sheet))
                    v=game.action(ps,dict(action='inventoryOpen',character='windows-hero'))
                    hero=next(c for c in v['characters'] if c['id']=='windows-hero')
                    self.assertTrue(hero['inventoryInitialized']);self.assertIn('coins',hero['runtime'])
                    v=game.action(gs,dict(action='actor',actor=dict(kind='npc',name='Стражник',hidden=False,kin='human',profession='fighter',attrs=dict(str=4,agi=3,wit=2,emp=2),skills={key:0 for key in progression.SKILLS},gear=['broadsword'])))
                    npc=next(c for c in v['characters'] if c['kind']=='npc')
                    v=game.action(gs,dict(action='combatCreate',units=[dict(id='windows-hero',team='A'),dict(id=npc['id'],team='B')]))
                    self.assertEqual(len(v['combat']['units']),2)
                    progression.catalog.cache_clear();self.assertTrue(progression.catalog()['general'])
                self.assertTrue(database.is_file());self.assertFalse((Path(folder)/'node_modules').exists())
            finally:
                progression.catalog.cache_clear();game.db.close()


if __name__=='__main__':unittest.main()
