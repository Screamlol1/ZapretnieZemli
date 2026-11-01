"""Durable action acknowledgements, committed in the same transaction as the room.

Only identifiers and payload digests are kept; private command contents never enter
the receipt table or responses. Receipts deliberately have no eviction timeout:
an old retry must never become a fresh action after restart or checkpoint restore.
"""
import hashlib
import json
import re
import time


def init(db):
    db.execute('''CREATE TABLE IF NOT EXISTS action_receipts (
        room TEXT NOT NULL, owner TEXT NOT NULL, request TEXT NOT NULL,
        digest TEXT NOT NULL, created REAL NOT NULL,
        PRIMARY KEY (room, owner, request)) WITHOUT ROWID''')
    db.commit()


def identifier(value):
    if not isinstance(value,str) or not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}',value):
        raise ValueError('Некорректный идентификатор действия.')
    return value.lower()


def prepare(db,s,data):
    if 'requestId' not in data:return None,False
    request=identifier(data['requestId'])
    payload={k:v for k,v in data.items() if k!='requestId'}
    digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    receipt=(s['room'],s['owner'],request,digest)
    row=db.execute('SELECT digest FROM action_receipts WHERE room=? AND owner=? AND request=?',receipt[:3]).fetchone()
    if row and row[0]!=digest:
        raise ValueError('Идентификатор уже использован для другого действия. Обновите состояние кампании.')
    return receipt,bool(row)


def insert(db,receipt):
    if receipt:db.execute('INSERT INTO action_receipts VALUES (?,?,?,?,?)',(*receipt,time.time()))


def status(db,s,request):
    request=identifier(request)
    row=db.execute('SELECT 1 FROM action_receipts WHERE room=? AND owner=? AND request=?',(s['room'],s['owner'],request)).fetchone()
    return 'applied' if row else 'missing'
