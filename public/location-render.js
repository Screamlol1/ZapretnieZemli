import {terrainPalette} from './location-themes.js';
import {locationPaths} from './location-paths.js';
import {artDefinition,artSprite,featureArt,atlasURL} from './location-art.js';
export const locationKinds={settlement:'Поселение',camp:'Лагерь',fortress:'Крепость',ruins:'Руины',dungeon:'Подземелье',cave:'Пещера'};
export const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function playerPlan(map){
 const visible=new Set(map.features.filter(f=>!f.secret).map(f=>f.id));
 const {settings,undoCount,...safe}=map;
 return {...safe,features:map.features.filter(f=>visible.has(f.id)).map(({gmNote,secret,...f})=>f),paths:map.paths.filter(p=>!p.secret&&p.refs.every(id=>visible.has(id))),tokens:(map.tokens||[]).filter(t=>!t.secret).map(({secret,...t})=>t)};
}
const rotated=(p,c,angle)=>{const a=angle*Math.PI/180,x=p[0]-c[0],y=p[1]-c[1];return [c[0]+x*Math.cos(a)-y*Math.sin(a),c[1]+x*Math.sin(a)+y*Math.cos(a)];};
const points=p=>p.map(a=>a.join(',')).join(' ');
export function passageDoors(map,f){
 const result=[],inside=([x,y])=>x>=f.x&&x<=f.x+f.w&&y>=f.y&&y<=f.y+f.h;
 for(const p of map.paths.filter(p=>p.style==='passage'&&p.refs.includes(f.id))){
  const center=[f.x+f.w/2,f.y+f.h/2],angle=f.rotation||0;
  const pts=(p.refs[0]===f.id&&p.refs.length>1?p.points:[...p.points].reverse()).map(p=>rotated(p,center,-angle));
  for(let i=1;i<pts.length;i++){
   const a=pts[i-1],b=pts[i];if(!inside(a)||inside(b))continue;
   const dx=b[0]-a[0],dy=b[1]-a[1];
   const tx=dx>0?(f.x+f.w-a[0])/dx:dx<0?(f.x-a[0])/dx:Infinity,ty=dy>0?(f.y+f.h-a[1])/dy:dy<0?(f.y-a[1])/dy:Infinity,t=Math.min(tx,ty);
   const [x,y]=rotated([a[0]+dx*t,a[1]+dy*t],center,angle),[vx,vy]=rotated([dx/Math.hypot(dx,dy),dy/Math.hypot(dx,dy)],[0,0],angle);result.push({x,y,dx:vx,dy:vy});break;
  }
 }
 return result;
}
export function locationSVG(map,{grid=false,labels=true,selected='',playerView=false,interactive=true,atlas=atlasURL}={}){
 const m=playerView?playerPlan(map):map,underground=['dungeon','cave'].includes(m.kind),palette=terrainPalette(m),bg=underground?'#666858':palette[0];
 const unit=m.cellSize/m.metersPerCell;
 const paths=locationPaths(m,interactive);
 const features=m.features.map((f,i)=>{
  const {x,y,w,h}=f,cx=x+w/2,cy=y+h/2;
  const hit=f.shape==='polygon'?`<polygon points="${points(f.points)}"/>`:f.shape==='ellipse'?`<ellipse cx="${cx}" cy="${cy}" rx="${w/2}" ry="${h/2}"/>`:`<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="2"/>`;
  const picture=artSprite(featureArt(f,m.culture),x,y,w,h,'location-art-atlas',['room','cave','bridge'].includes(f.style));
  const doors=underground?passageDoors(m,f).map(({x,y,dx,dy})=>`<path d="M${x-dx*unit*1.5} ${y-dy*unit*1.5}l${dx*unit*3} ${dy*unit*3}" stroke="url(#location-stone)" stroke-width="${3*unit}" pointer-events="none"/>`).join(''):'';
  const pinY=underground?cy:y+h+7;
  const pin=labels&&f.label?`<g pointer-events="none"><circle cx="${cx}" cy="${pinY}" r="8" fill="#f0e5c6" stroke="#534d38" stroke-width="1.2"/><text x="${cx}" y="${pinY+3}" text-anchor="middle" font-size="9" font-family="Georgia,serif" fill="#302f24">${i+1}</text></g>`:'';
  return `<g ${interactive?`data-location-feature="${esc(f.id)}" tabindex="0" role="button" aria-label="${esc(f.label||'Объект '+(i+1))}"`:''} opacity="${f.secret?0.55:1}" style="cursor:${interactive?'pointer':'default'}"><title>${esc(f.label||'Объект '+(i+1))}</title><g transform="rotate(${f.rotation||0} ${cx} ${cy})">${picture}<g fill="transparent" stroke="${f.id===selected?'#ecbd4b':'none'}" stroke-width="2" pointer-events="all">${hit}</g></g>${doors}${pin}</g>`;
 }).join('');
 const tokens=(m.tokens||[]).map(t=>{const r=Math.max(8,unit*(t.kind==='monster'?2:1)),color=t.kind==='monster'?'#a74938':t.kind==='pc'?'#315d53':'#7a6238';return `<g ${interactive?`data-location-token="${esc(t.id)}" tabindex="0" role="button" aria-label="${esc(t.name||'Персонаж')}"`:''} opacity="${t.secret?.5:1}"><title>${esc(t.name||'Персонаж')}${t.secret?' · скрыт':''}</title><g transform="rotate(${t.rotation||0} ${t.x} ${t.y})"><circle cx="${t.x}" cy="${t.y}" r="${r}" fill="${color}" stroke="#f2deb0" stroke-width="2"/>${t.image?`<image href="${esc(t.image)}" x="${t.x-r}" y="${t.y-r*2}" width="${r*2}" height="${r*3}" pointer-events="none"/>`:''}</g><text x="${t.x}" y="${t.y+r+12}" text-anchor="middle" font-size="11" font-family="Georgia,serif" fill="#241f16" stroke="#f2e7c9" stroke-width="3" paint-order="stroke" pointer-events="none">${esc(t.name||'Персонаж')}</text></g>`;}).join('');
 const entries=m.features.map((f,i)=>({number:i+1,label:f.label})).filter(f=>f.label),columns=m.width>=1000?3:2,columnWidth=(m.width-70)/columns,rows=Math.ceil(entries.length/columns),footer=(!interactive&&labels&&entries.length)?64+rows*42:0;
 const legend=footer?`<g font-family="Georgia,serif" fill="#343b2e"><rect y="${m.height}" width="${m.width}" height="${footer}" fill="#e4d8b9"/><text x="35" y="${m.height+28}" font-size="16">Места на плане</text>${entries.map((f,i)=>{const x=35+(i%columns)*columnWidth,y=m.height+53+Math.floor(i/columns)*42;const words=(f.number+'. '+f.label).match(/.{1,32}(?:\s|$)|.{1,32}/g)||[];return `<text x="${x}" y="${y}" font-size="12">${words.slice(0,3).map((line,j)=>`<tspan x="${x}" dy="${j?13:0}">${esc(line)}</tspan>`).join('')}</text>`;}).join('')}</g>`:'';
 return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${m.width} ${m.height+footer}" width="${m.width}" height="${m.height+footer}" role="img" aria-label="${esc(m.title)}"><title>${esc(m.title)}</title><defs>${artDefinition(atlas)}<pattern id="location-ground" width="46" height="46" patternUnits="userSpaceOnUse"><path d="M5 12l4 -2m20 25l5 -1M19 6l3 1" stroke="${palette[1]}" stroke-width="1"/><circle cx="13" cy="32" r="1.5" fill="${palette[2]}"/></pattern><pattern id="location-planks" width="12" height="12" patternUnits="userSpaceOnUse"><rect width="12" height="12" fill="#9b815b"/><path d="M0 0h12M6 0v12" stroke="#62533c" stroke-width=".8"/></pattern><pattern id="location-earth" width="24" height="24" patternUnits="userSpaceOnUse"><rect width="24" height="24" fill="#b7a077"/><path d="M2 8l4 -1m8 13l6 -2M10 4h3" stroke="#9b8967" stroke-width=".7"/><circle cx="18" cy="7" r="1" fill="#d3c196"/></pattern><pattern id="location-stone" width="${unit*2}" height="${unit*2}" patternUnits="userSpaceOnUse"><rect width="100%" height="100%" fill="#b0aa8e"/><path d="M0 0h${unit*2}v${unit}H0V0m${unit} 0v${unit}m${unit} 0v${unit}H0" fill="none" stroke="#716f5b" stroke-width=".7"/></pattern><pattern id="location-water" width="40" height="30" patternUnits="userSpaceOnUse"><rect width="40" height="30" fill="#7d9a95"/><path d="M2 8q6 -3 12 0m8 14q6 -3 12 0" fill="none" stroke="#abc0ad" stroke-width=".7"/></pattern><pattern id="location-grid" width="${m.cellSize}" height="${m.cellSize}" patternUnits="userSpaceOnUse"><path d="M${m.cellSize} 0H0V${m.cellSize}" fill="none" stroke="#514b39" stroke-opacity=".23" stroke-width=".8"/></pattern></defs><rect width="100%" height="100%" fill="${bg}"/>${!underground&&m.ground?'<rect width="100%" height="100%" fill="url(#location-ground)" pointer-events="none"/>':''}<rect x="12" y="12" width="${m.width-24}" height="${m.height-24}" fill="none" stroke="#746a4d" stroke-width="2"/><rect x="19" y="19" width="${m.width-38}" height="${m.height-38}" fill="none" stroke="#746a4d" stroke-opacity=".5"/>${m.river.length?`<polygon points="${points(m.river)}" fill="url(#location-water)" stroke="#536e69" stroke-width="2"/>`:''}${paths}${m.trees.map(([x,y,r],i)=>{const radius=r*10/m.metersPerCell;return artSprite(['highland','ash','sand'].includes(m.ground)?'rocks':i%3?'oak':'pine',x-radius,y-radius,radius*2,radius*2);}).join('')}${features}${tokens}${grid?'<rect width="100%" height="100%" fill="url(#location-grid)" pointer-events="none"/>':''}<g pointer-events="none" fill="#343b2e" font-family="Georgia,serif"><rect x="26" y="23" width="${Math.min(m.width-110,Math.max(160,m.title.length*10))}" height="31" rx="3" fill="#e4d8b9" fill-opacity=".88"/><rect x="26" y="${m.height-66}" width="185" height="43" rx="3" fill="#e4d8b9" fill-opacity=".88"/><text x="35" y="45" font-size="17">${esc(m.title)}</text><path d="M${m.width-40} 32l-8 24 8-5 8 5Z"/><text x="${m.width-40}" y="76" text-anchor="middle" font-size="12">С</text><path d="M35 ${m.height-36}h${m.cellSize*2}m-${m.cellSize*2} -4v8m${m.cellSize*2} -8v8" stroke="#343b2e" stroke-width="2"/><text x="35" y="${m.height-48}" font-size="11">${m.metersPerCell*2} м · схематичный план</text></g>${legend}</svg>`;
}
