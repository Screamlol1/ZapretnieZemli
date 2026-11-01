"""Private local PDF search. The index and books never belong in a game release."""
import argparse
import hashlib
import json
import logging
import re
import sqlite3
from pathlib import Path

GROUPS=('official','errata','reforged','house')
ALIASES={'инициатива':'initiative','форсирование':'pushing','пойти на риск':'pushing',
         'встречная проверка':'opposed roll','путешествие':'journeys','голод':'hungry',
         'жажда':'thirsty','холод':'cold','воля':'willpower','магия':'magic',
         'критическая травма':'critical injury','цитадель':'stronghold'}


def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS books (id INTEGER PRIMARY KEY, path TEXT UNIQUE, title TEXT, group_name TEXT, sha256 TEXT, pages INTEGER)')
    db.execute('CREATE VIRTUAL TABLE IF NOT EXISTS pages USING fts5(book UNINDEXED, page UNINDEXED, content, tokenize="unicode61 remove_diacritics 2")')


def store_pages(db,path,title,group,checksum,pages):
    if group not in GROUPS:raise ValueError('Unknown rules group')
    with db:
        row=db.execute('SELECT id,sha256,title,group_name FROM books WHERE path=?',(str(path),)).fetchone()
        if row and row[1:]==(checksum,title,group):return False
        if row:
            identifier=row[0]
            db.execute('DELETE FROM pages WHERE book=?',(identifier,))
            db.execute('UPDATE books SET title=?,group_name=?,sha256=?,pages=? WHERE id=?',(title,group,checksum,len(pages),identifier))
        else:
            identifier=db.execute('INSERT INTO books(path,title,group_name,sha256,pages) VALUES(?,?,?,?,?)',(str(path),title,group,checksum,len(pages))).lastrowid
        db.executemany('INSERT INTO pages(book,page,content) VALUES(?,?,?)',[(identifier,i+1,text) for i,text in enumerate(pages) if text.strip()])
    return True


def index_pdf(db,path,title,group):
    try:from pypdf import PdfReader
    except ImportError:raise SystemExit('PDF import requires pypdf. Install the pinned dev-tools/requirements.txt in a development environment.')
    path=Path(path).resolve(strict=True)
    if path.suffix.lower()!='.pdf':raise ValueError('Use a PDF with a text layer')
    checksum=hashlib.sha256(path.read_bytes()).hexdigest()
    current=db.execute('SELECT id,sha256,title,group_name,pages FROM books WHERE path=?',(str(path),)).fetchone()
    if current and current[1:4]==(checksum,title or path.stem,group):
        return dict(title=current[2],group=group,pages=current[4],indexedPages=db.execute('SELECT count(*) FROM pages WHERE book=?',(current[0],)).fetchone()[0],updated=False)
    reader=PdfReader(path)
    if reader.is_encrypted and not reader.decrypt(''):raise ValueError('Password-protected PDF is not supported')
    pages=[page.extract_text() or '' for page in reader.pages]
    if not any(text.strip() for text in pages):raise ValueError('No text layer found. OCR is required; an empty index was not saved.')
    changed=store_pages(db,path,title or path.stem,group,checksum,pages)
    return dict(title=title or path.stem,group=group,pages=len(pages),indexedPages=sum(bool(t.strip()) for t in pages),updated=changed)


def search(db,query,group=None,limit=8):
    query=ALIASES.get(query.strip().lower(),query)
    # Generate FTS syntax from literal tokens; input cannot inject FTS operators.
    tokens=re.findall(r'\w+',query,flags=re.UNICODE)
    if not tokens or len(tokens)>20:raise ValueError('Enter 1–20 search terms')
    expression=' AND '.join('"'+token+'"*' for token in tokens)
    sql='''SELECT books.title,books.group_name,pages.page,snippet(pages,2,'[',']',' … ',36),books.path
           FROM pages JOIN (SELECT id,title,group_name,path FROM books) AS books ON books.id=pages.book WHERE pages MATCH ?'''
    params=[expression]
    if group:
        if group not in GROUPS:raise ValueError('Unknown rules group')
        sql+=' AND books.group_name=?';params.append(group)
    sql+=' ORDER BY bm25(pages),books.title,CAST(pages.page AS INTEGER) LIMIT ?';params.append(max(1,min(50,limit)))
    return [dict(title=r[0],group=r[1],pdfPage=int(r[2]),excerpt=r[3],path=r[4]) for r in db.execute(sql,params)]


def main():
    logging.getLogger('pypdf').setLevel(logging.ERROR)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,default=Path(__file__).resolve().parents[1]/'.cache/rules-index.sqlite')
    commands=parser.add_subparsers(dest='command',required=True)
    add=commands.add_parser('add');add.add_argument('pdf',type=Path);add.add_argument('--title');add.add_argument('--group',choices=GROUPS,required=True)
    find=commands.add_parser('search');find.add_argument('query');find.add_argument('--group',choices=GROUPS);find.add_argument('--limit',type=int,default=8)
    commands.add_parser('list')
    args=parser.parse_args()
    if args.command=='add':
        args.database.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(args.database) as db:
            initialize(db);result=index_pdf(db,args.pdf,args.title,args.group)
    else:
        with sqlite3.connect(args.database.resolve().as_uri()+'?mode=ro',uri=True) as db:
            result=search(db,args.query,args.group,args.limit) if args.command=='search' else [dict(title=r[0],group=r[1],pages=r[2]) for r in db.execute('SELECT title,group_name,pages FROM books ORDER BY title')]
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
