import secrets
from dice_events import publish,pools
from dice_pools import result_text
from risk_rules import push,score

def apply(room,s,data):
    r=room.get('freeChecks',{}).get(s['owner'])
    if not r or r['id']!=data.get('roll') or r.get('done'):raise ValueError('Свободный бросок уже завершён или устарел.')
    if r['private'] and s['role']!='gm':raise PermissionError('Это скрытый бросок Мастера.')
    r['done']=True
    if data['action']=='freeAccept':return
    damage,wear=push(r,lambda n:secrets.randbelow(n)+1)
    result=result_text(*score(r))+f' Риск: урон характеристике {damage}, износ {wear}. Свободный бросок: внесите последствия в лист вручную.'
    publish(room,s['name'],'Пойти на риск · свободный бросок',pools(r),result,r['private'])
