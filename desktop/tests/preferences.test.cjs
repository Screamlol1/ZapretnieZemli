const test=require('node:test'),assert=require('node:assert/strict');
const {preferences,fitBounds,screenChanged,DEFAULTS}=require('../preferences.cjs');
test('Stored settings tolerate old/corrupt values; IPC updates reject invalid fields',()=>{
 assert.deepEqual(preferences({}),DEFAULTS);
 assert.deepEqual(preferences({mode:'unsafe',zoom:10000,width:-1}),DEFAULTS);
 for(const patch of [{mode:'unsafe'},{zoom:74},{zoom:101},{width:NaN},{height:Infinity},{confirmExit:'false'},{file:'C:/Windows'}])assert.throws(()=>preferences(patch,true));
 assert.equal(preferences({mode:'borderless',zoom:125,confirmExit:false},true).confirmExit,false);
});
test('Window remains visible after monitor removal, negative coordinates and small displays',()=>{
 assert.deepEqual(fitBounds({x:5000,y:-2000,width:4000,height:2000},{x:0,y:0,width:1366,height:728}),{x:0,y:0,width:1366,height:728});
 assert.deepEqual(fitBounds({x:-2000,y:10,width:800,height:600},{x:-1920,y:0,width:1920,height:1080}),{x:-1920,y:10,width:800,height:600});
 assert.deepEqual(fitBounds({}, {x:0,y:0,width:640,height:480}),{x:0,y:0,width:640,height:480});
 assert.equal(screenChanged(DEFAULTS,{...DEFAULTS,zoom:125}),false);
 assert.equal(screenChanged(DEFAULTS,{...DEFAULTS,mode:'fullscreen'}),true);
 assert.equal(screenChanged(DEFAULTS,{...DEFAULTS,width:1280}),true);
});
