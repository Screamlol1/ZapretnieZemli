"""Local-only provisioning of a new administrator; no web bootstrap endpoint."""
import argparse
import json
import secrets
from pathlib import Path
from server import Game


def main():
    parser=argparse.ArgumentParser(description='Create a new administrator and write credentials to a private local file.')
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--login',required=True)
    parser.add_argument('--name',default='Администратор')
    parser.add_argument('--credentials-file',type=Path,required=True)
    args=parser.parse_args()
    if args.credentials_file.exists():raise SystemExit('Credentials file already exists; refusing to overwrite it.')
    game=Game(args.database)
    try:
        password=secrets.token_urlsafe(24)
        token,result=game.accounts.auth('register',dict(login=args.login,name=args.name,password=password))
        account=game.accounts.authenticate(token)
        game.db.execute('UPDATE accounts SET admin=1 WHERE id=?',(account['id'],));game.db.commit()
        game.accounts.logout(token)
        game.admin.audit(account['id'],account['id'],'bootstrap','Создание администратора локальной командой')
        args.credentials_file.parent.mkdir(parents=True,exist_ok=True)
        args.credentials_file.write_text(json.dumps(dict(login=args.login,password=password,recovery=result['recovery']),ensure_ascii=False,indent=2),encoding='utf-8')
        print('Administrator created. Credentials saved to the specified private file.')
    finally:game.db.close()


if __name__=='__main__':main()
