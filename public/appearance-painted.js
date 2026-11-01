import {spriteURL as atlasURL,framePlacement} from './appearance-legacy.js';
import {equipmentShapes} from './appearance-rig.js';

// Hand positions are calibrated against the existing four-row painted atlases.
const hands={
 human:[[120,112],[127,111],[132,69],[129,35]],
 dwarf:[[126,126],[129,126],[135,103],[132,79]],
 elf:[[120,112],[126,116],[135,69],[137,41]],
 halfelf:[[120,112],[126,116],[135,69],[137,41]],
 halfling:[[106,135],[126,132],[134,106],[132,92]],
 wolfkin:[[125,112],[129,112],[139,79],[140,47]],
 orc:[[123,117],[134,118],[136,79],[137,63]],
 goblin:[[125,136],[131,135],[138,108],[140,94]],
};
export async function paintedSVG(actor,v,options){
 const pose=options.pose,monster=actor.kind==='monster'||actor.monster,rowPose=({shoot:'strike',block:'strike',dodge:'walk',fall:'idle'})[pose]||pose,row={idle:0,walk:1,strike:2,cast:3}[rowPose]||0,frame=await atlasURL({...actor,visual:v},rowPose),kin=actor.sheet?.kin||actor.kin||'human',raw=(hands[kin]||hands.human)[row],f=framePlacement(actor,rowPose),p=[f.ox+raw[0]*f.unit*f.scale,f.oy+(f.legacyY-f.sy+raw[1]*f.unit)*f.scale];
 const hand=pose==='cast'?'none':v.mainHand,off=pose==='cast'?'none':v.offHand;
 const gear=monster?'':`<g transform="translate(${p[0]} ${p[1]}) scale(.88) rotate(${pose==='shoot'?0:row===2?-65:8})">${equipmentShapes(hand)}</g><g transform="translate(${p[0]-60} ${p[1]+(row===2?13:-2)}) scale(.88) rotate(-12)">${equipmentShapes(off)}</g>`;
 const colors={cloth:/^#[0-9a-f]{6}$/i.test(v.cloth)?v.cloth:'#a37942'},rotate={idle:0,walk:0,strike:-9,shoot:-5,block:8,dodge:12,cast:-3,fall:73}[pose],animated=options.animate&&pose!=='idle',direction=options.direction||v.direction;
 const movement=animated?`<animateTransform attributeName="transform" type="rotate" values="0;${rotate||-3};${pose==='fall'?rotate:0}" dur="${pose==='walk'?.7:1}s" repeatCount="${pose==='walk'?'indefinite':'1'}" fill="freeze"/>`:'';
 return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${pose==='fall'?'10 0 220 160':'0 0 160 160'}" data-pose="${pose}" data-style="painted"><defs><linearGradient id="steel"><stop stop-color="#46524b"/><stop offset=".45" stop-color="#c3c5ac"/><stop offset="1" stop-color="#47534c"/></linearGradient><linearGradient id="cloth"><stop stop-color="${colors.cloth}"/><stop offset="1" stop-color="#3d3e2f"/></linearGradient></defs><g transform="${direction==='left'?'translate(160 0) scale(-1 1)':''}"><g transform="translate(80 125)"><g transform="rotate(${options.animate?0:rotate})">${movement}<g transform="translate(-80 -125)"><image href="${frame}" x="0" y="0" width="160" height="160"/>${gear}</g></g></g></g></svg>`;
}
