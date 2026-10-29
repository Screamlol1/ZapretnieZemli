import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {cultures,cultureAssets} from '../public/location-culture-data.js';
import {featureArt,artSprite,artDefinition} from '../public/location-art.js';
import {locationSVG} from '../public/location-render.js';
import {locationPaths} from '../public/location-paths.js';

assert.equal(new Set(cultureAssets.map(a=>a.id)).size,36);
for(const c of cultures)for(const a of c.assets){
 const [x,y,w,h]=a.crop;assert.ok(x>=0&&y>=0&&w>0&&h>0&&x+w<=1024&&y+h<=1536);
 const file=readFileSync(new URL(`../public/assets/location-cultures-${a.atlas}-v1.png`,import.meta.url));assert.equal(file.readUInt32BE(16),1024);assert.equal(file.readUInt32BE(20),1536);assert.equal(file[25],6);
 assert.equal(featureArt({id:'f1',style:'building',themeRole:a.role},c.id),a.id);
 assert.ok(artSprite(a.id,0,0,40,40).includes(`href="#location-art-atlas-${a.atlas}"`));
 assert.equal(featureArt({id:'f1',style:'building',art:'well',themeRole:a.role},c.id),'well');
}
const mixed=new Set(Array.from({length:30},(_,i)=>featureArt({id:'f'+i,style:'building',themeRole:'home'},'mixed')));assert.ok(mixed.size>=8);
assert.ok(!artDefinition({base:'data:base',a:'data:a',b:'data:b'}).includes('/assets/'));
const m={title:'Торг',width:760,height:560,kind:'settlement',cellSize:40,metersPerCell:10,culture:'saurian',ground:'marsh',roadSurface:'planks',features:[{id:'f',style:'building',themeRole:'home',x:10,y:10,w:40,h:40,label:'Хижина'}],paths:[{style:'road',refs:[],points:[[10,100],[200,100]]}],trees:[],river:[]};
const svg=locationSVG(m);assert.ok(svg.includes('href="#location-art-atlas-b"'));assert.ok(svg.includes('fill="url(#location-ground)"'));
const planks=locationPaths(m);assert.ok(planks.includes('url(#location-planks)'));assert.ok(planks.includes('M10 100L200 100'));
assert.ok(locationPaths({...m,roadSurface:'stone'}).includes('url(#location-stone)'));
assert.ok(locationPaths({...m,roadSurface:undefined}).includes('url(#location-earth)'));
console.log('Culture terrain: all art crops, mixed styles, manual overrides, surfaces and embedded atlas definitions passed.');
