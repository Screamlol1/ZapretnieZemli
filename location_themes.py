"""Shared art catalogue; visual choices do not change tabletop movement rules."""
import json
from pathlib import Path

CULTURES = json.loads((Path(__file__).parent/'public/location-cultures.json').read_text(encoding='utf-8'))
BY_ID = {c['id']: c for c in CULTURES}
ART_IDS = tuple(a['id'] for c in CULTURES for a in c['assets'])
GROUNDS = ('auto', 'grass', 'forest', 'highland', 'marsh', 'ash', 'sand')
ROADS = ('auto', 'earth', 'stone', 'planks')


def style_settings(raw):
    if not isinstance(raw, dict):raise ValueError('Нужны настройки оформления.')
    culture=raw.get('culture','neutral');ground=raw.get('ground','auto');road=raw.get('roadSurface','auto')
    if not isinstance(culture,str) or culture not in ('neutral','mixed',*BY_ID):raise ValueError('Выберите народ из списка.')
    if ground not in GROUNDS or road not in ROADS:raise ValueError('Выберите покрытие земли и дорог из списка.')
    return dict(culture=culture,ground=ground,roadSurface=road)


def apply_style(plan, cfg):
    style=style_settings(cfg);culture=BY_ID.get(style['culture'])
    plan['culture']=style['culture']
    plan['ground']=style['ground'] if style['ground']!='auto' else culture['ground'] if culture else 'grass'
    plan['roadSurface']=style['roadSurface'] if style['roadSurface']!='auto' else culture['road'] if culture else 'earth'
    plan.setdefault('settings',{}).update(style)
    for f in plan['features']:
        # Manual art selections always take priority, including on mixed maps.
        if f.get('art'):continue
        if f['style']=='building':f.setdefault('themeRole','hall' if f.get('label') in ('Таверна','Дом старосты','Казарма') else 'home')
        elif f['style']=='square':f.setdefault('themeRole','landmark')
        elif f['style']=='tent':f.setdefault('themeRole','shelter')
        # Preserve authored names on existing maps and after manual edits.
        if culture and f.get('autoLabel') is not None and f['label']==f['autoLabel']:
            role=f.get('themeRole')
            if role=='shelter' and culture['id'] in ('wolfkin','goblin','aslene','ogre'):role='home'
            asset=next((a for a in culture['assets'] if a['role']==role),None)
            if asset:f['label']=f['autoLabel']=asset['label']
        elif style['culture']=='neutral' and f.get('autoLabel') is not None and f['label']==f['autoLabel']:
            f['label']=f['autoLabel']=f.get('baseLabel',f['label'])


def size_generated(plan):
    """Use catalogue footprints on new settlements; never resize an existing plan."""
    culture=BY_ID.get(plan['culture'])
    if not culture or plan['settings']['kind']!='settlement':return
    unit=plan['cellSize']/plan['metersPerCell']
    for f in plan['features']:
        asset=next((a for a in culture['assets'] if a['role']==f.get('themeRole')),None)
        if not asset:continue
        w,h=asset['width']*unit,asset['height']*unit
        x,y=f['x']+(f['w']-w)/2,f['y']+(f['h']-h)/2
        if 0<=x<=plan['width']-w and 0<=y<=plan['height']-h:f.update(x=x,y=y,w=w,h=h)
