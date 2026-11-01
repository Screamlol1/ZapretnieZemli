import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from backup import snapshot


class BackupTests(unittest.TestCase):
    def test_committed_database_maps_and_manifest_without_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / 'live.sqlite'
            source = sqlite3.connect(database)
            try:
                source.execute('PRAGMA journal_mode=WAL')
                source.execute('CREATE TABLE example (value TEXT)')
                source.execute("INSERT INTO example VALUES ('saved')")
                source.commit()
                (root / 'map-images').mkdir()
                (root / 'map-images' / 'map.png').write_bytes(b'uploaded map')
                (root / 'credentials.json').write_text('private credentials')
                reference = root / 'reference'
                reference.mkdir()
                (reference / 'forbidden-lands.jpg').write_bytes(b'reference map')
                (reference / 'book.pdf').write_bytes(b'private book')
                result = snapshot(database, reference, root / 'backups')
                manifest = json.loads((result / 'COMPLETE.json').read_text())
                self.assertEqual(set(manifest['sha256']), {
                    'campaigns.sqlite', 'map-images/map.png', 'local-assets/forbidden-lands.jpg',
                })
                for name, digest in manifest['sha256'].items():
                    self.assertEqual(hashlib.sha256((result / name).read_bytes()).hexdigest(), digest)
                restored = sqlite3.connect(result / 'campaigns.sqlite')
                try:
                    self.assertEqual(restored.execute('SELECT value FROM example').fetchall(), [('saved',)])
                finally:
                    restored.close()
                second = snapshot(database, None, root / 'backups')
                self.assertNotEqual(result, second)
            finally:
                source.close()

    def test_missing_source_does_not_create_an_empty_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(FileNotFoundError):
                snapshot(root / 'missing.sqlite', None, root / 'backups')
            self.assertEqual(list(root.iterdir()), [])

    def test_corrupt_database_never_gets_completion_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / 'broken.sqlite'
            database.write_bytes(b'not a database')
            with self.assertRaises(sqlite3.DatabaseError):
                snapshot(database, None, root / 'backups')
            self.assertEqual(list((root / 'backups').rglob('COMPLETE.json')), [])
