import assert from 'node:assert/strict';
import {rigSVG,MORPHS,POSES} from '../public/appearance-rig.js';
import {displayEquipment,visualDefaults,spriteURL} from '../public/appearance.js';
import {appearanceEvents} from '../public/appearance-feedback.js';
const hero={id:'hero',visual:{style:'miniature'},sheet:{kin:'human',gear:['broadsword']}};
assert.equal(displayEquipment(hero).mainHand,'sword');
assert.equal(displayEquipment({...hero,inventoryInitialized:true}).mainHand,'none');
assert.equal(displayEquipment({...hero,inventoryInitialized:true,equipment:{weapon:'axe'}},[{id:'axe',combatProfile:'axe',location:{kind:'character',id:'stranger'}}]).mainHand,'none');
assert.equal(displayEquipment({...hero,inventoryInitialized:true,equipment:{weapon:'axe'}},[{id:'axe',combatProfile:'axe',location:{kind:'character',id:'hero'}}]).mainHand,'axe');
const models=new Set();for(const kin of Object.keys(MORPHS)){const actor={...hero,sheet:{kin}},svg=rigSVG(actor,visualDefaults(actor),{pose:'idle'});models.add(svg);assert.ok(svg.includes('data-kin="'+kin+'"'));}assert.equal(models.size,8);
for(const pose of POSES){const svg=rigSVG(hero,visualDefaults(hero),{pose,animate:true});assert.ok(svg.includes('data-pose="'+pose+'"'));if(pose!=='idle')assert.ok(svg.includes('animateTransform'));assert.ok(!rigSVG(hero,visualDefaults(hero),{pose,animate:false}).includes('animateTransform'));}
assert.notEqual(await spriteURL(hero),await spriteURL({...hero,visual:{...visualDefaults(hero),style:'miniature',hairStyle:'braid',beard:'full',mainHand:'axe'}}));
const before={characters:[{id:'hero',runtime:{current:{str:2}}}],locationMaps:[{id:'a',tokens:[{characterId:'hero',x:50,y:50}]}],magicCastings:[]};
assert.deepEqual(appearanceEvents(before,{...before,locationMaps:[{id:'a',tokens:[{characterId:'hero',x:40,y:50}]}]}),{hero:{pose:'walk',direction:'left'}});
assert.deepEqual(appearanceEvents(before,{...before,characters:[{id:'hero',runtime:{current:{str:0}}}]}),{hero:{pose:'fall'}});
assert.deepEqual(appearanceEvents(before,{...before,magicCastings:[{id:'cast',character:'hero',power:2,status:'rolled'}]}),{hero:{pose:'cast'}});
console.log('Appearance proportions, layers, equipment and animation transitions passed');
