const DEFAULTS=Object.freeze({mode:'windowed',width:1440,height:1000,zoom:100,rememberWindow:true,confirmExit:true});
function preferences(raw={},strict=false){
 if(!raw||typeof raw!=='object'||Array.isArray(raw))throw Error('Некорректные настройки.');
 const out={...DEFAULTS};
 for(const [key,value] of Object.entries(raw)){
  const valid=key==='mode'?['windowed','fullscreen','borderless'].includes(value):key==='width'?Number.isInteger(value)&&value>=760&&value<=7680:key==='height'?Number.isInteger(value)&&value>=600&&value<=4320:key==='zoom'?Number.isInteger(value)&&value>=75&&value<=150&&value%5===0:['rememberWindow','confirmExit'].includes(key)?typeof value==='boolean':false;
  if(valid)out[key]=value;else if(strict)throw Error('Недопустимое значение настройки: '+key);
 }
 return out;
}
function fitBounds(raw,area){
 const width=Math.min(area.width,Math.max(Math.min(760,area.width),Number.isFinite(raw?.width)?Math.round(raw.width):DEFAULTS.width));
 const height=Math.min(area.height,Math.max(Math.min(600,area.height),Number.isFinite(raw?.height)?Math.round(raw.height):DEFAULTS.height));
 const x=Number.isFinite(raw?.x)?Math.round(raw.x):area.x+Math.round((area.width-width)/2),y=Number.isFinite(raw?.y)?Math.round(raw.y):area.y+Math.round((area.height-height)/2);
 return {x:Math.max(area.x,Math.min(x,area.x+area.width-width)),y:Math.max(area.y,Math.min(y,area.y+area.height-height)),width,height};
}
function screenChanged(a,b){return a.mode!==b.mode||(b.mode==='windowed'&&(a.width!==b.width||a.height!==b.height));}
module.exports={DEFAULTS,preferences,fitBounds,screenChanged};
