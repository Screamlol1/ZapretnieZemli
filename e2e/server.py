"""Isolated E2E host. OS-assigned port, empty reference assets, stdin lifecycle."""
import argparse
import json
from pathlib import Path
import sys
import threading

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import Game,ThreadingHTTPServer,make_handler

parser=argparse.ArgumentParser()
parser.add_argument('--data',type=Path,required=True)
args=parser.parse_args()
game=Game(args.data/'campaigns.sqlite',reference_root=args.data/'reference')
http=ThreadingHTTPServer(('127.0.0.1',0),make_handler(game))
thread=threading.Thread(target=http.serve_forever,daemon=True)
thread.start()
print(json.dumps({'url':f'http://127.0.0.1:{http.server_port}/'}),flush=True)
try:
    # Closing the parent process also closes stdin: no orphan server on Ctrl+C.
    for line in sys.stdin:
        if line.strip()=='stop':break
finally:
    http.shutdown()
    http.server_close()
    thread.join(timeout=5)
    game.db.close()
