"""Import original terrain colors from the official Ravenland PSD HEX layer.

Read-only, standard-library importer. Downloads only metadata and one layer
using verified HTTP byte ranges, never the full 1.5 GB PSD. No image is edited.
The resulting JSON is private local data, bound to the installed JPEG hash.
"""
import argparse
import hashlib
import json
import math
import struct
import urllib.request
from collections import Counter
from pathlib import Path

SOURCE='https://www.dropbox.com/s/7datt0benf9f6y8/DALEN_103_ENG.psd?dl=1'
COLORS={(139,166,105):'forest',(95,117,69):'darkforest',(173,169,126):'hills',
        (164,160,150):'mountain',(178,129,105):'highmountain',(148,175,189):'water',
        (90,181,174):'marsh',(231,219,81):'rough',(90,101,181):'ruin'}
# Display colors sampled from the printed legend, not the hidden editing colors.
PALETTE=dict(plain='#867e4d',forest='#515428',darkforest='#343618',hills='#91855b',
             mountain='#8b8572',highmountain='#817b66',water='#52634d',marsh='#76765f',rough='#948a5a',ruin='#77705c')

def read_range(source,start,end):
    if not source.startswith('https://'):
        with Path(source).open('rb') as f:f.seek(start);return f.read(end-start+1)
    request=urllib.request.Request(source,headers={'Range':f'bytes={start}-{end}','User-Agent':'ForbiddenLandsTerrainImporter/1.0'})
    with urllib.request.urlopen(request,timeout=45) as response:
        if response.status!=206 or not response.headers.get('Content-Range','').startswith(f'bytes {start}-{end}/'):
            raise ValueError('Server must support exact byte ranges; refusing a full PSD download.')
        data=response.read(end-start+2)
    if len(data)!=end-start+1:raise ValueError('Incomplete PSD range.')
    return data

def layers(header):
    if header[:6]!=b'8BPS\x00\x01':raise ValueError('Expected a version 1 PSD.')
    channels,height,width,depth,mode=struct.unpack_from('>HIIHH',header,12)
    if depth!=8 or mode!=3:raise ValueError('Expected 8-bit RGB PSD.')
    u=lambda offset:struct.unpack_from('>I',header,offset)[0]
    pos=26;pos+=4+u(pos);pos+=4+u(pos);pos+=8
    count=abs(struct.unpack_from('>h',header,pos)[0]);pos+=2;result=[]
    for _ in range(count):
        rect=struct.unpack_from('>4i',header,pos);pos+=16
        count_channels=struct.unpack_from('>H',header,pos)[0];pos+=2;entries=[]
        for _ in range(count_channels):
            channel,size=struct.unpack_from('>hI',header,pos);pos+=6
            entries.append(dict(channel=channel,length=size))
        pos+=12;extra=u(pos);pos+=4;end=pos+extra
        pos+=4+u(pos);pos+=4+u(pos)
        size=header[pos];name=header[pos+1:pos+1+size].decode('latin1');pos=end
        result.append(dict(name=name,rect=rect,channels=entries))
    offset=pos
    for layer in result:
        for channel in layer['channels']:
            channel['offset']=offset;offset+=channel['length']
    return width,height,result

def unpack_row(data,width):
    result=bytearray();pos=0
    while pos<len(data):
        n=data[pos];pos+=1
        if n<128:result.extend(data[pos:pos+n+1]);pos+=n+1
        elif n>128:result.extend(data[pos:pos+1]*(257-n));pos+=1
        if len(result)>width:raise ValueError('Invalid RLE row.')
    if len(result)!=width:raise ValueError('Incomplete RLE row.')
    return result

def build(image,source):
    width,height,records=layers(read_range(source,0,8*1024*1024-1))
    if (width,height)!=(8563,6201):raise ValueError('Expected the original 8563 x 6201 Ravenland PSD, without cropping or rescaling.')
    layer=next(l for l in records if l['name']=='HEX')
    top,left,bottom,right=layer['rect'];h=bottom-top;w=right-left
    base=layer['channels'][0]['offset'];last=layer['channels'][-1]
    blob=read_range(source,base,last['offset']+last['length']-1)
    points={}
    for x in range(41):
        for y in range(25):
            if x%2 and y==24:continue
            xx=round((61.5+x*47.73)*width/2039.2374)-left
            yy=round((77.5+(y+x%2/2)*math.sqrt(3)*31.82)*height/1474.3049)-top
            if not 0<=xx<w or not 0<=yy<h:raise ValueError('PSD does not match Ravenland geometry.')
            points[f'{x},{y}']=(xx,yy)
    rows={}
    for channel in layer['channels']:
        b=blob[channel['offset']-base:channel['offset']-base+channel['length']]
        if struct.unpack_from('>H',b)[0]!=1:raise ValueError('Expected RLE channels.')
        sizes=struct.unpack_from('>'+str(h)+'H',b,2);offset=2+h*2;offsets=[]
        for size in sizes:offsets.append(offset);offset+=size
        rows[channel['channel']]={y:unpack_row(b[offsets[y]:offsets[y]+sizes[y]],w) for y in {p[1] for p in points.values()}}
    cells={}
    for key,(x,y) in points.items():
        rgb=tuple(rows[c][y][x] for c in (0,1,2));alpha=rows[-1][y][x]
        if alpha==0:terrain='plain'
        else:terrain=COLORS.get(rgb)
        if terrain:cells[key]=dict(terrain=terrain,terrainOrigin='reference')
        elif rgb in ((218,218,218),(255,255,255)):
            cells[key]=dict(terrainUnknown='mist' if rgb==(218,218,218) else 'unmapped',terrainOrigin='reference')
        else:raise ValueError(f'Unknown HEX color {rgb} at {key}; review the source before importing.')
    return dict(version=1,layout='ravenland',imageSha256=hashlib.sha256(image.read_bytes()).hexdigest(),
                method='psd-hex-v1',source=source,cells=cells,palette=PALETTE)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image',type=Path);parser.add_argument('--source',default=SOURCE)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();result=build(args.image,args.source)
    target=args.output or args.image.with_name('forbidden-lands-terrain.json')
    target.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(dict(cells=len(result['cells']),types=dict(Counter(c.get('terrain','unknown') for c in result['cells'].values())))))
