import assert from 'node:assert/strict';
import {newBattle,attack,validateBattle} from '../public/tools/battle-rules.js';
import {monsterAttack} from '../monster-rules.mjs';
function fixture(){const b=newBattle('road',[{id:'a1',team:'A'},{id:'b1',team:'B'}]);b.phase='combat';b.round=1;b.order=['a1','b1'];b.units[0].q=3;b.units[0].r=3;b.units[1].q=4;b.units[1].r=3;b.units[1].armor=0;b.units[1].defense='none';return b;}
{
 const b=fixture(),u=b.units[0];u.monster={attacks:Array.from({length:6},()=>({name:'Удар',dice:2,damage:1,range:1,type:'physical',dodge:true,parry:false,note:''}))};u.maxStr=16;u.str=1;
 let rolls=0;monsterAttack(b,'b1',0,false,()=>{rolls++;return 6;});assert.equal(rolls,2);assert.equal(b.units[1].str,3);assert.equal(u.slow,0);validateBattle(b);
 assert.throws(()=>monsterAttack(b,'b1',0),/действия/);
}
{
 const b=fixture(),u=b.units[0];u.monster={attacks:[{name:'Рёв',dice:2,damage:1,range:3,type:'fear',note:''}]};
 assert.throws(()=>monsterAttack(b,'b1',0,true),/форсировать/);assert.equal(u.slow,1);
 monsterAttack(b,'b1',0,false,()=>6);assert.equal(b.units[1].wits,1);assert.equal(b.units[1].str,5);
}
{
 const b=fixture(),u=b.units[0];u.monster={attacks:[{name:'Рёв',dice:2,damage:1,range:3,type:'fear',note:''}]};b.units[1].monster={};
 assert.throws(()=>monsterAttack(b,'b1',0,false,()=>6),/невосприимчивы/);assert.equal(u.slow,1);
}
{
 const b=fixture(),u=b.units[0];attack(b,'b1','slash',{push:true},()=>1);
 assert.equal(u.wp,4,'Only four attribute ones give WP, not two gear ones');assert.equal(u.gear,0);
}
{
 const b=fixture(),u=b.units[0];u.weapon='bow';u.gear=2;const str=u.str;attack(b,'b1','shoot',{push:true},()=>1);
 assert.equal(u.str,str);assert.equal(u.agi,0);assert.equal(u.wp,3);
}
console.log('Monster attacks: fixed pools despite wounds, fear, no pushing, immunity; pushed attacks: attribute-specific damage and base-only WP passed.');
