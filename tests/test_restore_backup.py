import unittest
import test_server as support
from pathlib import Path
import tempfile
import sqlite3
import json
import hashlib
import subprocess
import sys
from contextlib import closing
from backup import snapshot
from restore_backup import validate, restore, restore_incomplete, JOURNAL


class RestoreBackupTests(unittest.TestCase):
    def crash_fixture(self,root):
        data=root/'data';data.mkdir();db=data/'campaigns.sqlite'
        with closing(sqlite3.connect(db)) as con,con:
            con.execute('CREATE TABLE rooms(id TEXT PRIMARY KEY,data TEXT)');con.execute('INSERT INTO rooms VALUES (?,?)',('backup','{}'))
        for directory,name,body in [('map-images','a.png',b'backup-map'),('local-assets','forbidden-lands.jpg',b'backup-reference')]:
            (data/directory).mkdir();(data/directory/name).write_bytes(body)
        backup=snapshot(db,data/'local-assets',root/'backups')
        with closing(sqlite3.connect(db)) as con,con:con.execute("UPDATE rooms SET id='current'")
        (data/'map-images/a.png').write_bytes(b'current-map');(data/'local-assets/forbidden-lands.jpg').write_bytes(b'current-reference')
        original={str(p.relative_to(data)):p.read_bytes() for p in data.rglob('*') if p.is_file()}
        return data,backup,original

    def interrupt(self,data,backup,after,operation='restore'):
        script='''import os,sys
import restore_backup as r
move=r._move;count=0
def crash(source,target):
 global count
 move(source,target);count+=1
 if count==int(sys.argv[3]):os._exit(79)
r._move=crash
if sys.argv[4]=='restore':r.restore(sys.argv[2],sys.argv[1])
else:r.restore_incomplete(sys.argv[1])
'''
        result=subprocess.run([sys.executable,'-X','utf8','-c',script,str(data),str(backup),str(after),operation],cwd=Path(__file__).parents[1],capture_output=True,timeout=15)
        self.assertEqual(result.returncode,79,result.stderr.decode('utf-8',errors='replace'))

    def assert_original(self,data,original):
        for name,value in original.items():self.assertEqual((data/name).read_bytes(),value,name)
        self.assertFalse((data/JOURNAL).exists());self.assertFalse(list(data.parent.glob('zz-restore-*')))

    def test_restore_roundtrip_and_corruption_leaves_original_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=root/'data';data.mkdir();db=data/'campaigns.sqlite'
            with closing(sqlite3.connect(db)) as con, con:
                con.execute('CREATE TABLE rooms(id TEXT PRIMARY KEY,data TEXT)');con.execute('INSERT INTO rooms VALUES (?,?)',('original','{}'))
            (data/'map-images').mkdir();(data/'map-images'/'a.png').write_bytes(b'old-map')
            folder=snapshot(db,None,root/'backups')
            with closing(sqlite3.connect(db)) as con, con:con.execute("UPDATE rooms SET id='new'")
            (data/'map-images'/'a.png').write_bytes(b'new-map');(data/'server.log').write_text('keep')
            restore(folder,data)
            with closing(sqlite3.connect(db)) as con, con:self.assertEqual(con.execute('SELECT id FROM rooms').fetchone(),('original',))
            self.assertEqual((data/'map-images'/'a.png').read_bytes(),b'old-map');self.assertEqual((data/'server.log').read_text(),'keep')
            before=db.read_bytes();(folder/'map-images'/'a.png').write_bytes(b'broken')
            with self.assertRaisesRegex(ValueError,'сумма'):restore(folder,data)
            self.assertEqual(db.read_bytes(),before)

    def test_bad_paths_incomplete_database_and_live_wal_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=root/'data';data.mkdir();db=data/'campaigns.sqlite'
            with closing(sqlite3.connect(db)) as con, con:con.execute('CREATE TABLE rooms(id,data)')
            folder=snapshot(db,None,root/'backups');marker=folder/'COMPLETE.json';original=marker.read_text()
            doc=json.loads(original);doc['sha256']['../outside']='0'*64;marker.write_text(json.dumps(doc))
            with self.assertRaises(ValueError):validate(folder)
            marker.write_text(original);(data/'campaigns.sqlite-wal').write_bytes(b'active')
            with self.assertRaisesRegex(ValueError,'используется'):restore(folder,data)
            (data/'campaigns.sqlite-wal').unlink();marker.unlink()
            with self.assertRaises(FileNotFoundError):restore(folder,data)

    def test_process_death_after_every_swap_recovers_exact_original(self):
        for step in range(1,7):
            with self.subTest(swap=step),tempfile.TemporaryDirectory() as tmp:
                data,backup,original=self.crash_fixture(Path(tmp));self.interrupt(data,backup,step)
                self.assertTrue((data/JOURNAL).is_file());self.assertTrue(restore_incomplete(data));self.assert_original(data,original)
                self.assertFalse(restore_incomplete(data))

    def test_recovery_itself_is_restartable_after_every_move(self):
        for step in range(1,4):
            with self.subTest(recovery_move=step),tempfile.TemporaryDirectory() as tmp:
                data,backup,original=self.crash_fixture(Path(tmp));self.interrupt(data,backup,6);self.interrupt(data,backup,step,'recover')
                restore_incomplete(data);self.assert_original(data,original)

    def test_committed_journal_keeps_restored_data_after_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            data,backup,_=self.crash_fixture(Path(tmp))
            script='''import os,sys
import restore_backup as r
write=r._write_json
def crash(path,doc):
 write(path,doc)
 if doc.get('phase')=='committed':os._exit(79)
r._write_json=crash
r.restore(sys.argv[2],sys.argv[1])
'''
            result=subprocess.run([sys.executable,'-X','utf8','-c',script,str(data),str(backup)],cwd=Path(__file__).parents[1],capture_output=True,timeout=15);self.assertEqual(result.returncode,79)
            restore_incomplete(data)
            with closing(sqlite3.connect(data/'campaigns.sqlite')) as con:self.assertEqual(con.execute('SELECT id FROM rooms').fetchone(),('backup',))
            self.assertEqual((data/'map-images/a.png').read_bytes(),b'backup-map');self.assertFalse((data/JOURNAL).exists())

    def test_untrusted_journal_paths_and_missing_original_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            data,backup,original=self.crash_fixture(Path(tmp));self.interrupt(data,backup,1)
            marker=data/JOURNAL;doc=json.loads(marker.read_text());saved=doc.copy();doc['stage']='../outside';marker.write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError,'путь'):restore_incomplete(data)
            self.assertFalse((data/'campaigns.sqlite').exists())
            marker.write_text(json.dumps(saved));stage=data.parent/saved['stage'];(stage/'previous/campaigns.sqlite').unlink()
            with self.assertRaisesRegex(ValueError,'не найдены'):restore_incomplete(data)
            self.assertFalse((data/'campaigns.sqlite').exists())

    def test_stage_owner_mismatch_does_not_touch_original_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            data,backup,_=self.crash_fixture(Path(tmp));self.interrupt(data,backup,1)
            doc=json.loads((data/JOURNAL).read_text());stage=data.parent/doc['stage'];old=(stage/'previous/campaigns.sqlite').read_bytes()
            (stage/'OWNER.json').write_text(json.dumps({'data':str(data.parent/'other'),'nonce':doc['nonce']}))
            with self.assertRaisesRegex(ValueError,'не принадлежит'):restore_incomplete(data)
            self.assertEqual((stage/'previous/campaigns.sqlite').read_bytes(),old);self.assertFalse((data/'campaigns.sqlite').exists())

    def test_cleanup_interruption_keeps_committed_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            data,backup,_=self.crash_fixture(Path(tmp))
            script='''import os,sys
import restore_backup as r
def crash(stage):
 r._remove(stage/'new',stage);os._exit(79)
r._cleanup_stage=crash
r.restore(sys.argv[2],sys.argv[1])
'''
            result=subprocess.run([sys.executable,'-X','utf8','-c',script,str(data),str(backup)],cwd=Path(__file__).parents[1],capture_output=True,timeout=15);self.assertEqual(result.returncode,79)
            restore_incomplete(data)
            with closing(sqlite3.connect(data/'campaigns.sqlite')) as con:self.assertEqual(con.execute('SELECT id FROM rooms').fetchone(),('backup',))
            self.assertFalse((data/JOURNAL).exists())

    def test_desktop_boot_recovers_before_opening_database_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            data,backup,original=self.crash_fixture(Path(tmp));self.interrupt(data,backup,1)
            result=subprocess.run([sys.executable,'-X','utf8','desktop/desktop_server.py','--data',str(data),'--port','0'],cwd=Path(__file__).parents[1],input='{"op":"stop"}\n',text=True,encoding='utf-8',capture_output=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr);self.assertIn('"type": "ready"',result.stdout)
            with closing(sqlite3.connect(data/'campaigns.sqlite')) as con:self.assertEqual(con.execute('SELECT id FROM rooms').fetchone(),('current',))
            self.assertFalse((data/JOURNAL).exists())
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp)/'data';data.mkdir();(data/JOURNAL).write_text('{"version":999}')
            result=subprocess.run([sys.executable,'-X','utf8','desktop/desktop_server.py','--data',str(data),'--port','0'],cwd=Path(__file__).parents[1],input='',text=True,encoding='utf-8',capture_output=True,timeout=15)
            self.assertNotEqual(result.returncode,0);self.assertNotIn('"type": "ready"',result.stdout);self.assertFalse((data/'campaigns.sqlite').exists())
