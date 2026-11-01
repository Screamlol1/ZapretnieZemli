import assert from 'node:assert/strict';
import {audioContextFor,projectedAudioFeed} from '../public/game-audio-state.js';
const room=()=>({id:'campaign',revision:1,me:{owner:'player',role:'player'},characters:[{id:'hero',name:'Герой'}],maps:{world:{'0,0':{terrain:'forest'}}},mapFog:{world:[]},locationMaps:[],journey:{position:{x:0,y:0}},diceRolls:[],combat:{phase:'setup',units:[{id:'hero',q:1,r:1}]}});
const roll=(id,privateRoll=false)=>({id,private:privateRoll,groups:[{kind:'base',values:[6]}]});
const feed=projectedAudioFeed(),s=room();s.diceRolls=[roll('old')];assert.deepEqual(feed(s).events,[],'History on initial connection is silent');
s.revision++;s.diceRolls.push(roll('fresh'));assert.deepEqual(feed(s).events.map(e=>e.type),['dice']);assert.deepEqual(feed(s).events,[],'Polling must not replay');assert.deepEqual(feed(s,'map').events,[],'Changing views must not replay');
s.revision++;s.diceRolls.push(roll('secret',true));assert.deepEqual(feed(s).events,[]);assert.ok(!audioContextFor(s).eventIds.some(id=>id.includes('secret')),'A player context cannot prime private IDs');
s.combat={phase:'combat',units:[{id:'hero',q:2,r:1}],event:{id:'private-hit',actor:'hero',kind:'strike',hitIds:['hero'],private:true}};assert.deepEqual(feed(s).events,[]);
s.combat.event={...s.combat.event,id:'legacy-without-privacy'};delete s.combat.event.private;assert.deepEqual(feed(s).events,[],'Legacy event without privacy metadata is silent for players');
s.revision++;s.combat.event={id:'public-hit',actor:'hero',kind:'strike',action:'slash',hitIds:['hero'],private:false};assert.deepEqual(feed(s).events.map(e=>e.type),['hit']);assert.deepEqual(feed(s).events,[]);
for(const action of ['punch','shoot','shove','monsterAttack','manual',undefined]){s.revision++;s.combat.event={id:'nonmetal-'+action,actor:'hero',kind:'strike',action,hitIds:['hero'],private:false};assert.deepEqual(feed(s).events,[],action+' must not use a metal weapon effect');}
s.characters.push({id:'beast',kind:'monster',name:'Чудовище'});
for(const [name,type] of [['Чудовище',null],['Серый волк','wolf'],['Древний дракон','monster']]){s.characters[1].name=name;s.revision++;s.combat.event={id:'beast-'+s.revision,actor:'beast',kind:'strike',action:'monsterAttack',hitIds:['hero'],private:false};assert.deepEqual(feed(s).events.map(e=>e.type),type?[type]:[]);}
s.revision++;s.combat.event={id:'step',actor:'hero',kind:'move',origin:{q:1,r:1},hitIds:[],private:false};assert.deepEqual(feed(s).events.map(e=>e.type),['footstep']);
s.revision++;s.combat.event={id:'pending-step',actor:'hero',kind:'move',origin:{q:2,r:1},hitIds:[],private:false};assert.deepEqual(feed(s).events,[],'An attempted but unapplied move is silent');
s.revision++;s.diceRolls.push({id:'cast-dice',groups:[{kind:'magic',values:[3]}]});s.combat.event={id:'cast',actor:'hero',kind:'cast',action:'cast',hitIds:['hero'],private:false};assert.deepEqual(feed(s).events.map(e=>e.type),['magic'],'A damaging spell and its dice share one magic cue without metal');
s.revision++;s.diceRolls.push({id:'safe-cast',groups:[]});s.magicCastings=[{id:'casting',event:'safe-cast',status:'resolved'}];assert.deepEqual(feed(s).events.map(e=>e.type),['magic'],'Safe casting with zero dice is still a real spell');
s.revision++;s.journey.position={x:1,y:0};s.maps.world['1,0']={terrain:'water'};assert.deepEqual(feed(s).events.map(e=>e.type),['footstep']);
s.revision++;s.journey.season='winter';s.journey.position={x:2,y:0};s.maps.world['2,0']={terrain:'forest'};assert.deepEqual(feed(s).events.map(e=>e.type),['snow-step'],'Winter travel uses snow steps');s.journey.position={x:1,y:0};feed(s);
s.mapFog.world=['1,0'];s.maps.world['1,0'].locationMapId='hidden';s.scene={map:'hidden'};s.locationMaps=[{id:'hidden',kind:'cave',revealed:false}];assert.equal(audioContextFor(s).terrain,'');assert.equal(audioContextFor(s).locationType,'');
const reloaded=projectedAudioFeed();assert.deepEqual(reloaded(s).events,[],'Reload cannot replay previous effects');
s.me={role:'gm',owner:'master'};assert.deepEqual(feed(s).events,[],'Changing ownership/role primes history');s.revision++;s.diceRolls.push(roll('gm-only',true));assert.equal(feed(s).events[0].private,true);
s.revision=0;assert.deepEqual(feed(s).events,[],'Older restored snapshots reset the feed silently');
console.log('Audio projection: initial/reload silence, public/private ownership, repeated polls, confirmed movement/hits, magic dedup and hidden terrain passed.');
