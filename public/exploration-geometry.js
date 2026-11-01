export function discovered(map,f){const e=map.exploration;return !f.secret&&(!e?.enabled||e.discovered?.includes(f.id));}
export function contains(f,x,y){const cx=f.x+f.w/2,cy=f.y+f.h/2,a=-(f.rotation||0)*Math.PI/180,dx=x-cx,dy=y-cy,px=cx+dx*Math.cos(a)-dy*Math.sin(a),py=cy+dx*Math.sin(a)+dy*Math.cos(a);return px>=f.x&&px<=f.x+f.w&&py>=f.y&&py<=f.y+f.h;}
export const visiblePoint=(map,x,y)=>!map.exploration?.enabled||map.features.some(f=>discovered(map,f)&&contains(f,x,y));
const cross=(a,b,c)=>(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
export function intersects(a,b,c,d){return cross(a,b,c)*cross(a,b,d)<0&&cross(c,d,a)*cross(c,d,b)<0;}
export function doorSegment(map,p){
 const lengths=p.points.slice(1).map((v,i)=>Math.hypot(v[0]-p.points[i][0],v[1]-p.points[i][1]));let distance=lengths.reduce((a,b)=>a+b,0)/2;
 for(let i=0;i<lengths.length;i++){const length=lengths[i];if(distance>length){distance-=length;continue;}const a=p.points[i],b=p.points[i+1],ratio=length?distance/length:0,x=a[0]+(b[0]-a[0])*ratio,y=a[1]+(b[1]-a[1])*ratio,dx=length?(b[0]-a[0])/length:1,dy=length?(b[1]-a[1])/length:0,w=map.cellSize/map.metersPerCell*2;return {x,y,a:[x-dy*w,y+dx*w],b:[x+dy*w,y-dx*w]};}
 return {x:0,y:0,a:[0,0],b:[0,0]};
}
export function measure(map,a,b){
 const distance=Math.hypot(a[0]-b[0],a[1]-b[1])*map.metersPerCell/map.cellSize;
 const obstacles=map.paths.filter(p=>{if(['wall','palisade'].includes(p.style))return p.points.some((v,i)=>i>0&&intersects(a,b,p.points[i-1],v));if(p.style==='passage'&&['closed','locked'].includes(map.exploration?.doors?.[p.id])){const d=doorSegment(map,p);return intersects(a,b,d.a,d.b);}return false;});
 const light=(map.exploration?.lights||[]).some(l=>!l.expired&&Math.hypot(b[0]-l.x,b[1]-l.y)*map.metersPerCell/map.cellSize<=l.radius);
 return {distance:Math.round(distance*10)/10,blocked:obstacles.length>0,dark:!!map.exploration?.dark&&!light};
}
export function explorationOverlay(m){
 const e=m.exploration;if(!e)return '';const unit=m.cellSize/m.metersPerCell;
 const holes=m.features.filter(f=>discovered(m,f)).map(f=>`<rect x="${f.x}" y="${f.y}" width="${f.w}" height="${f.h}" transform="rotate(${f.rotation||0} ${f.x+f.w/2} ${f.y+f.h/2})" fill="black"/>`).join('')+m.paths.map(p=>`<polyline points="${p.points.map(v=>v.join(',')).join(' ')}" fill="none" stroke="black" stroke-width="${Math.max(unit*3,p.width||4)}"/>`).join('');
 const lights=(e.lights||[]).filter(l=>!l.expired).map(l=>`<circle cx="${l.x}" cy="${l.y}" r="${l.radius*unit}" fill="black"/>`).join('');
 const doors=m.paths.filter(p=>e.doors?.[p.id]&&e.doors[p.id]!=='open').map(p=>{const {x,y,a,b}=doorSegment(m,p);return `<g><path d="M${a.join(' ')}L${b.join(' ')}" stroke="#c8a779" stroke-width="4"/><circle cx="${x}" cy="${y}" r="8" fill="${e.doors[p.id]==='locked'?'#a85338':'#78623d'}" stroke="#f6e2ab"/><path d="M${x-3} ${y-5}v10m6-10v10" stroke="#fff1cc" stroke-width="2"/></g>`;}).join('');
 return `<g pointer-events="none"><defs><mask id="exploration-fog"><rect width="100%" height="100%" fill="white"/>${holes}</mask><mask id="exploration-dark"><rect width="100%" height="100%" fill="white"/>${lights}</mask></defs>${e.dark?`<rect width="${m.width}" height="${m.height}" fill="#08151e" opacity=".62" mask="url(#exploration-dark)"/>`:''}${e.enabled?`<rect width="${m.width}" height="${m.height}" fill="#18241f" opacity="${m.settings?'.74':'1'}" mask="url(#exploration-fog)"/>`:''}${doors}${(e.lights||[]).filter(l=>!l.expired).map(l=>`<circle cx="${l.x}" cy="${l.y}" r="4" fill="#ffe593" stroke="#b58031"/>`).join('')}</g>`;
}
