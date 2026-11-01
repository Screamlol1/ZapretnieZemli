import assert from 'node:assert/strict';
import {playerPlan,locationSVG} from '../public/location-render.js';
import {measure,doorSegment} from '../public/exploration-geometry.js';
import {resultChanges} from '../public/play-feedback.js';
import {appearancePresets} from '../public/appearance.js';
const f=(id,x)=>({id,x,y:10,w:100,h:100,style:'room',shape:'rect',label:id,note:'',gmNote:'SECRET-'+id,secret:false});
const m={id:'m',title:'Plan',width:500,height:300,kind:'dungeon',cellSize:20,metersPerCell:2,features:[f('one',10),f('two',210)],paths:[{id:'hall',style:'passage',points:[[60,60],[260,60]],refs:['one','two']},{id:'secret-free-wall',style:'wall',points:[[350,200],[400,200]],refs:[]}],tokens:[{id:'hidden-token',characterId:'npc',x:250,y:50}],river:[],trees:[],settings:{seed:'PRIVATE-SEED'},exploration:{enabled:true,discovered:['one'],dark:true,doors:{hall:'closed','secret-free-wall':'locked'},lights:[{id:'lamp',x:50,y:50,radius:10},{id:'hidden-lamp',x:250,y:50,radius:10}]}};
const safe=playerPlan(m);assert.deepEqual(safe.features.map(f=>f.id),['one']);assert.equal(safe.paths.length,0);assert.equal(safe.tokens.length,0);assert.equal(safe.exploration.lights.length,1);assert.deepEqual(safe.exploration.doors,{});assert.ok(!JSON.stringify(safe).includes('SECRET'));assert.ok(!JSON.stringify(safe).includes('PRIVATE-SEED'));
const svg=locationSVG(m,{playerView:true});assert.ok(!svg.includes('hidden-token'));assert.ok(!svg.includes('secret-free-wall'));assert.ok(svg.includes('exploration-fog'));
assert.equal(measure(m,[60,60],[260,60]).distance,20);assert.equal(measure(m,[60,60],[260,60]).blocked,true,'Closed door crosses the corridor, not its centerline');
const opened=structuredClone(m);opened.exploration.doors.hall='open';assert.equal(measure(opened,[60,60],[260,60]).blocked,false);assert.equal(doorSegment(m,m.paths[0]).x,160);
const bent={...m.paths[0],points:[[0,0],[100,0],[100,100]]};assert.deepEqual(doorSegment(m,bent).x,100);
const before={characters:[{id:'c',name:'Hero',runtime:{current:{str:4},wp:2,resources:{food:8}}}],items:[]},after=structuredClone(before);after.characters[0].runtime.current.str=2;after.characters[0].runtime.wp=3;after.characters[0].runtime.resources.food=6;
assert.deepEqual(resultChanges(before,after).map(e=>e.kind),['damage','will','resource']);assert.deepEqual(resultChanges(after,after),[]);assert.deepEqual(resultChanges({characters:[],items:[]},after),[],'Initial/reconnected state is not an animation event');
for(const kin of ['human','elf','halfelf','dwarf','halfling','orc','wolfkin','goblin']){const p=appearancePresets({kind:'pc',kin});assert.equal(p.length,6);assert.equal(new Set(p.map(v=>JSON.stringify(v.visual))).size,6);for(const v of p)for(const key of ['skin','hair','cloak','cloth'])assert.match(v.visual[key],/^#[a-f0-9]{6}$/);}
console.log('Scene: fog export privacy, doors/range, result-derived feedback, eight-kin appearance presets passed');
