const coordinates=pts=>pts.map(p=>p.join(',')).join(' ');
export const lineWidth=(map,style)=>{
 const unit=map.cellSize/map.metersPerCell;
 return (style==='wall'?3:style==='palisade'?.7:style==='passage'?3:map.kind==='camp'?2:6)*unit;
};

// Paint every outline before the shared surface. Individual outlines must not
// cut across another segment at T joints, corners or crossings.
export function locationPaths(map,interactive=true){
 const unit=map.cellSize/map.metersPerCell,layers=[];
 const hidden=new Set(map.features.filter(f=>f.secret).map(f=>f.id));
 for(const secret of [true,false]){
  const surfaces=[];
  for(const style of ['road','passage','palisade','wall']){
   const paths=map.paths.filter(p=>p.style===style&&Boolean(p.secret||p.refs.some(id=>hidden.has(id)))===secret);
   if(!paths.length)continue;
   const d=paths.map(p=>'M'+p.points.map(a=>a.join(' ')).join('L')).join(' '),w=lineWidth(map,style);
   const stroke=(color,width,extra='')=>`<path d="${d}" fill="none" stroke="${color}" stroke-width="${width}" stroke-linecap="round" stroke-linejoin="round" ${extra}/>`;
   if(style==='wall')surfaces.push(stroke('#4c4a3c',w+2),stroke('#8d8a70',w+4,`stroke-dasharray="${unit} ${unit*2}" style="stroke-linecap:butt"`),stroke('url(#location-stone)',w));
   else if(style==='palisade')surfaces.push(stroke('#4e3724',w+1.5),stroke('#9b7950',w+3,`stroke-dasharray="${.3*unit} ${.25*unit}" style="stroke-linecap:butt"`),stroke('#83603d',w*.65));
   else surfaces.push(stroke(style==='passage'?'#55584b':'#98835d',w+2),stroke(`url(#${style==='passage'?'location-stone':map.roadSurface==='stone'?'location-stone':map.roadSurface==='planks'?'location-planks':'location-earth'})`,w));
  }
  if(surfaces.length)layers.push(`<g data-location-surface="${secret?'private':'public'}" opacity="${secret?.5:1}" pointer-events="none">${surfaces.join('')}</g>`);
 }
 const hits=interactive?map.paths.map((p,i)=>`<g data-location-path="${i}"><polyline points="${coordinates(p.points)}" fill="none" stroke="transparent" stroke-width="${Math.max(14,lineWidth(map,p.style)+4)}" stroke-linejoin="round" stroke-linecap="round" pointer-events="stroke"/><polyline class="location-path-outline" points="${coordinates(p.points)}" fill="none" stroke="transparent" stroke-width="3" stroke-linejoin="round" stroke-linecap="round" pointer-events="none"/></g>`).join(''):'';
 return layers.join('')+hits;
}

export function nearestLinePoint(paths,p,tolerance=12){
 let closest=null,distance=tolerance;
 for(const path of paths)for(const v of path.points){const d=Math.hypot(v[0]-p[0],v[1]-p[1]);if(d<distance){closest=[...v];distance=d;}}
 if(closest)return closest;
 for(const path of paths)for(let i=1;i<path.points.length;i++){
  const a=path.points[i-1],b=path.points[i],dx=b[0]-a[0],dy=b[1]-a[1],length=dx*dx+dy*dy;
  const t=length?Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/length)):0;
  const q=[a[0]+t*dx,a[1]+t*dy],d=Math.hypot(q[0]-p[0],q[1]-p[1]);
  if(d<distance){closest=q;distance=d;}
 }
 return closest;
}
