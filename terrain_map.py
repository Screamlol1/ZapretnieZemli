"""Private reference terrain layer; campaign edits always take precedence."""
import hashlib
import json

KINDS={'plain','forest','darkforest','hills','mountain','highmountain','water','marsh','rough','ruin'}

def load_reference(directory):
    image=directory/'forbidden-lands.jpg';path=directory/'forbidden-lands-terrain.json'
    if not image.is_file() or not path.is_file():return {}
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
        if data['version']!=1 or data['layout']!='ravenland' or data['method']!='psd-hex-v1':return {}
        if data['imageSha256']!=hashlib.sha256(image.read_bytes()).hexdigest():return {}
        cells={}
        if len(data['cells'])>1005:return {}
        for key,cell in data['cells'].items():
            x,y=map(int,key.split(','))
            if key!=f'{x},{y}' or not 0<=x<41 or not 0<=y<25 or x%2 and y==24:return {}
            if cell.get('terrain') in KINDS:cells[key]={'terrain':cell['terrain'],'terrainOrigin':'reference'}
            elif cell.get('terrainUnknown') in ('mist','unmapped'):cells[key]={'terrainUnknown':cell['terrainUnknown'],'terrainOrigin':'reference'}
            else:return {}
        return cells
    except (ValueError,KeyError,TypeError,OSError):return {}

def cell_at(room,key):
    base=room.get('_worldBase',{}).get(key,{})
    override=room['maps']['world'].get(key,{})
    cell={**base,**override}
    if override.get('terrain'):
        cell.pop('terrainUnknown',None);cell['terrainOrigin']='manual'
    return cell

def effective_world(room):
    return {k:cell_at(room,k) for k in room.get('_worldBase',{}).keys()|room['maps']['world'].keys()}
