"""Private, portable snapshots. Never place the output in a public/source directory."""
import argparse
import hashlib
import json
import secrets
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


def snapshot(database, reference_root, output):
    database = Path(database).resolve()
    if not database.is_file():
        raise FileNotFoundError(database)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    destination = output / (stamp + '-' + secrets.token_hex(4))
    destination.mkdir(mode=0o700)
    # COMPLETE.json is written last. An interrupted directory is not a valid backup.
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as source:
        with closing(sqlite3.connect(destination / 'campaigns.sqlite')) as target:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise ValueError('Backup integrity check failed')
    uploads = database.parent / 'map-images'
    if uploads.is_dir():
        for path in uploads.glob('*.png'):
            if path.is_symlink():
                raise ValueError('Symlink in uploaded maps')
            folder = destination / 'map-images'
            folder.mkdir(exist_ok=True)
            shutil.copyfile(path, folder / path.name)
    # Only runtime map assets; do not copy books, credentials or unrelated files.
    if reference_root is not None:
        for name in ('forbidden-lands.jpg', 'forbidden-lands-terrain.json'):
            path = Path(reference_root) / name
            if path.is_file():
                folder = destination / 'local-assets'
                folder.mkdir(exist_ok=True)
                shutil.copyfile(path, folder / name)
    files = {
        path.relative_to(destination).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in destination.rglob('*') if path.is_file()
    }
    (destination / 'COMPLETE.json').write_text(
        json.dumps({'version': 1, 'createdUtc': stamp, 'sha256': files}, indent=2),
        encoding='utf-8',
    )
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--reference-root', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(snapshot(args.database, args.reference_root, args.output))
