"""Private desktop child process; its stdin belongs exclusively to the launcher."""
import argparse
import json
import os
from pathlib import Path
import sys
import threading

base=Path(__file__).resolve().parent
game_root=base/'game' if (base/'game'/'server.py').is_file() else base.parent
sys.path.insert(0,str(game_root))
sys.dont_write_bytecode=True
from server import Game, ThreadingHTTPServer, make_handler, LOCK
from backup import snapshot


def main():
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);p.add_argument('--port',type=int,default=8791)
    a=p.parse_args();a.data.mkdir(parents=True,exist_ok=True)
    db=a.data/'campaigns.sqlite';refs=a.data/'local-assets';refs.mkdir(exist_ok=True)
    game=Game(db,reference_root=refs)
    try:http=ThreadingHTTPServer(('127.0.0.1',a.port),make_handler(game,public_test=True))
    except OSError:
        http=ThreadingHTTPServer(('127.0.0.1',0),make_handler(game,public_test=True))
    def emit(value):print(json.dumps(value,ensure_ascii=False),flush=True)
    def commands():
        for line in sys.stdin:
            command=None
            try:
                command=json.loads(line)
                if command.get('op')=='stop':break
                if command.get('op')=='backup':
                    with LOCK:folder=snapshot(db,refs,command['output'])
                    emit(dict(type='backup',id=command.get('id'),path=str(folder)))
            except Exception as e:emit(dict(type='error',id=command.get('id') if isinstance(command,dict) else None,message=str(e)))
        # A crashed/closed launcher closes the pipe too: do not orphan a host.
        http.shutdown()
    threading.Thread(target=commands,daemon=True).start()
    emit(dict(type='ready',url=f'http://127.0.0.1:{http.server_port}/',pid=os.getpid()))
    try:http.serve_forever(poll_interval=.2)
    finally:
        http.server_close()
        with LOCK:game.db.close()


if __name__=='__main__':main()
