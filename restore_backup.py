"""Offline desktop restore. The launcher must stop its own server first."""
import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

TARGETS=('campaigns.sqlite','map-images','local-assets')
JOURNAL='.restore-journal.json'


def _link(path):
    return path.is_symlink() or bool(getattr(path,'is_junction',lambda:False)())


def _sync_directory(path):
    """POSIX directory durability; Windows does not expose directory fsync here."""
    if os.name=='nt':return
    descriptor=os.open(path,os.O_RDONLY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)


def _write_json(path,doc):
    temporary=path.with_name(path.name+'.tmp')
    if _link(path) or _link(temporary):raise ValueError('Ссылка вместо журнала восстановления.')
    with temporary.open('w',encoding='utf-8') as out:
        json.dump(doc,out,ensure_ascii=False);out.flush();os.fsync(out.fileno())
    temporary.replace(path);_sync_directory(path.parent)


def _safe_tree(path,root):
    if not path.exists() and not _link(path):return
    if _link(path) or not path.resolve().is_relative_to(root.resolve()):raise ValueError('Небезопасный путь восстановления.')
    if path.is_dir():
        for child in path.iterdir():_safe_tree(child,root)


def _remove(path,parent):
    # Every deletion is a verified direct child of the caller's owned root.
    if path.parent.resolve()!=parent.resolve():raise ValueError('Небезопасная очистка восстановления.')
    _safe_tree(path,parent)
    if path.is_dir():shutil.rmtree(path)
    elif path.exists():path.unlink()
    _sync_directory(parent)


def _move(source,target):
    """One observable swap, also used by subprocess crash-injection tests."""
    source.replace(target);_sync_directory(source.parent);_sync_directory(target.parent)


def _closed(data):
    if any((data/('campaigns.sqlite'+suffix)).exists() for suffix in ('-wal','-shm','-journal')):
        raise ValueError('База ещё используется или не закрыта. Запустите и остановите свой сервер.')


def _cleanup_stage(stage):
    # Keep the ownership marker until all rollback data has been removed. This
    # makes cleanup itself restartable after process termination.
    if any(p.name not in ('new','previous','OWNER.json') for p in stage.iterdir()):raise ValueError('Посторонние файлы в каталоге восстановления.')
    for name in ('new','previous'):_remove(stage/name,stage)
    if (stage/'OWNER.json').exists():(stage/'OWNER.json').unlink()
    stage.rmdir();_sync_directory(stage.parent)


def restore_incomplete(data):
    """Run BEFORE Game/SQLite initialization. Recover old bytes or fail closed.

    The journal contains no arbitrary target paths. A stage must be a directly
    owned sibling with matching nonce/owner marker. Recovery is idempotent even
    when interrupted during its own moves.
    """
    data=Path(data).resolve(strict=True);marker=data/JOURNAL
    if not marker.exists() and not _link(marker):return False
    if _link(marker) or not marker.is_file() or marker.stat().st_size>8192:raise ValueError('Повреждён журнал восстановления; запуск базы остановлен.')
    _closed(data)
    doc=json.loads(marker.read_text(encoding='utf-8'))
    if not isinstance(doc,dict) or set(doc)!={'version','stage','nonce','phase','hadOld'} or doc.get('version')!=1 or doc.get('phase') not in ('installing','committed','rolled_back'):
        raise ValueError('Неизвестный журнал восстановления; запуск базы остановлен.')
    if not isinstance(doc['stage'],str) or not re.fullmatch(r'zz-restore-[A-Za-z0-9_-]{6,80}',doc['stage']) or not isinstance(doc['nonce'],str) or not re.fullmatch('[0-9a-f]{32}',doc['nonce']):
        raise ValueError('Небезопасный путь журнала восстановления.')
    if not isinstance(doc['hadOld'],dict) or set(doc['hadOld'])!=set(TARGETS) or any(type(v)!=bool for v in doc['hadOld'].values()):raise ValueError('Некорректные цели журнала восстановления.')
    stage=data.parent/doc['stage']
    if stage==data or _link(stage) or stage.exists() and stage.resolve().parent!=data.parent:raise ValueError('Небезопасный каталог восстановления.')
    if stage.exists():
        _safe_tree(stage,data.parent)
        owner=stage/'OWNER.json'
        cleaned=doc['phase']!='installing' and not any(stage.iterdir())
        if not cleaned and (not owner.is_file() or owner.stat().st_size>8192 or json.loads(owner.read_text(encoding='utf-8'))!={'data':str(data),'nonce':doc['nonce']}):
            raise ValueError('Каталог восстановления не принадлежит этой базе.')
    elif doc['phase']=='installing':raise ValueError('Прерванное восстановление потеряло исходные файлы; запуск базы остановлен.')
    for name in TARGETS:_safe_tree(data/name,data)
    if doc['phase']=='installing':
        previous=stage/'previous';new=stage/'new'
        if not previous.is_dir() or not new.is_dir():raise ValueError('Неполный каталог восстановления; запуск базы остановлен.')
        # Check every required original before removing any installed target.
        for name in TARGETS:
            if doc['hadOld'][name] and not (previous/name).exists() and not (data/name).exists():raise ValueError('Исходные файлы не найдены; запуск базы остановлен.')
        for name in reversed(TARGETS):
            target=data/name;old=previous/name
            if doc['hadOld'][name]:
                if old.exists():
                    _remove(target,data);_move(old,target)
                # If old is absent but target exists, it was never moved or a
                # prior recovery already returned it. Both mean keep original.
            else:_remove(target,data)
        doc['phase']='rolled_back';_write_json(marker,doc)
    if (doc['phase']=='committed' or doc['hadOld']['campaigns.sqlite']) and not (data/'campaigns.sqlite').is_file():raise ValueError('База не восстановлена; запуск пустой базы запрещён.')
    # Mark final state before cleanup: losing power during cleanup is harmless.
    if stage.exists():_cleanup_stage(stage)
    marker.unlink();_sync_directory(data)
    return True


def validate(folder):
    folder = Path(folder).resolve(strict=True)
    marker = folder / 'COMPLETE.json'
    if marker.is_symlink() or marker.stat().st_size > 1000000:
        raise ValueError('Некорректный манифест копии.')
    doc = json.loads(marker.read_text(encoding='utf-8'))
    hashes = doc.get('sha256')
    if doc.get('version') != 1 or not isinstance(hashes, dict) or 'campaigns.sqlite' not in hashes or len(hashes) > 10000:
        raise ValueError('Это не завершённая резервная копия игры.')
    total = 0
    for name, digest in hashes.items():
        if not (name == 'campaigns.sqlite' or name in ('local-assets/forbidden-lands.jpg', 'local-assets/forbidden-lands-terrain.json') or re.fullmatch(r'map-images/[a-zA-Z0-9_-]+\.png', name)):
            raise ValueError('В копии есть неподдерживаемый путь.')
        file = folder / name
        if any(p.is_symlink() for p in [file, file.parent]) or not file.is_file() or not file.resolve().is_relative_to(folder):
            raise ValueError('Ссылки и отсутствующие файлы в копии запрещены.')
        total += file.stat().st_size
        if total > 2*1024**3 or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('Копия слишком велика или повреждена.')
        with file.open('rb') as source:
            if hashlib.file_digest(source, 'sha256').hexdigest() != digest:
                raise ValueError('Контрольная сумма копии не совпала: '+name)
    with closing(sqlite3.connect((folder/'campaigns.sqlite').as_uri()+'?mode=ro&immutable=1', uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('База данных повреждена.')
        row = db.execute("SELECT type FROM sqlite_master WHERE name='rooms'").fetchone()
        if row != ('table',):
            raise ValueError('Копия не содержит базы кампаний.')
        if not {'id','data'}.issubset({r[1] for r in db.execute('PRAGMA table_info(rooms)')}):
            raise ValueError('Несовместимая база кампаний.')
    return folder, hashes


def restore(folder, data):
    data = Path(data).resolve(strict=True)
    restore_incomplete(data)
    folder, hashes = validate(folder)
    if folder == data or folder.is_relative_to(data):
        raise ValueError('Выберите резервную копию вне папки текущих данных.')
    # A prior crash must be recovered by starting/stopping the owning server first.
    _closed(data)
    for name in TARGETS:_safe_tree(data/name,data)
    temporary=Path(tempfile.mkdtemp(prefix='zz-restore-',dir=data.parent))
    stage=temporary/'new';previous=temporary/'previous';stage.mkdir();previous.mkdir()
    nonce=secrets.token_hex(16);_write_json(temporary/'OWNER.json',{'data':str(data),'nonce':nonce})
    published=False
    try:
        for name in hashes:
            target=stage/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(folder/name,target)
            with target.open('r+b') as copied:os.fsync(copied.fileno())
        # Validate the exact staged bytes too, before touching the live data.
        shutil.copyfile(folder/'COMPLETE.json',stage/'COMPLETE.json');validate(stage)
        doc=dict(version=1,stage=temporary.name,nonce=nonce,phase='installing',hadOld={name:(data/name).exists() for name in TARGETS})
        _write_json(data/JOURNAL,doc);published=True
        try:
            for name in TARGETS:
                old=data/name; new=stage/name
                if old.exists():_move(old,previous/name)
                if new.exists():_move(new,old)
        except BaseException:
            restore_incomplete(data)
            raise
        doc['phase']='committed';_write_json(data/JOURNAL,doc)
        restore_incomplete(data)
    finally:
        # Never delete rollback material while a live journal still needs it.
        if not published and temporary.exists():_remove(temporary,data.parent)
    return {'restored':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--backup',required=True);parser.add_argument('--data');parser.add_argument('--validate',action='store_true')
    args=parser.parse_args()
    if args.validate:validate(args.backup);print(json.dumps({'valid':True}))
    elif args.data:print(json.dumps(restore(args.backup,args.data)))
    else:parser.error('--data is required for restore')
