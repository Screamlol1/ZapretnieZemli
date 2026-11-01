// Orthographic views of the actual polyhedra. All dice share one material palette.
const dot=(a,b)=>a.reduce((n,v,i)=>n+v*b[i],0),sub=(a,b)=>a.map((v,i)=>v-b[i]),cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const norm=a=>{const n=Math.hypot(...a);return a.map(v=>v/n);};
function hull(vertices){
 const faces=new Map();
 for(let i=0;i<vertices.length;i++)for(let j=i+1;j<vertices.length;j++)for(let k=j+1;k<vertices.length;k++){
  let n=cross(sub(vertices[j],vertices[i]),sub(vertices[k],vertices[i]));if(Math.hypot(...n)<1e-6)continue;n=norm(n);let h=dot(n,vertices[i]);
  const ds=vertices.map(v=>dot(n,v)-h);if(ds.some(v=>v>1e-6)&&ds.some(v=>v< -1e-6))continue;
  if(h<0){n=n.map(v=>-v);h=-h;}
  const ids=vertices.map((v,i)=>Math.abs(dot(n,v)-h)<1e-6?i:-1).filter(i=>i>=0),key=ids.join(',');if(faces.has(key))continue;
  const center=ids.reduce((a,i)=>a.map((v,k)=>v+vertices[i][k]/ids.length),[0,0,0]),x=norm(sub(vertices[ids[0]],center)),y=cross(n,x);
  ids.sort((i,j)=>Math.atan2(dot(sub(vertices[i],center),y),dot(sub(vertices[i],center),x))-Math.atan2(dot(sub(vertices[j],center),y),dot(sub(vertices[j],center),x)));
  faces.set(key,{ids,n,center});
 }
 return [...faces.values()];
}
const phi=(1+Math.sqrt(5))/2;
const d8=[[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,0,-1]];
const d10=[[0,0,1.35],[0,0,-1.35],...Array.from({length:10},(_,i)=>[Math.cos(i*Math.PI/5),Math.sin(i*Math.PI/5),(i%2?-1:1)*1.35*(1-Math.cos(Math.PI/5))/(1+Math.cos(Math.PI/5))])];
const d12=[];for(const a of [-1,1])for(const b of [-1,1]){for(const c of [-1,1])d12.push([a,b,c]);d12.push([0,a/phi,b*phi],[a/phi,b*phi,0],[a*phi,0,b/phi]);}
export const diceModels=Object.fromEntries([[8,d8],[10,d10],[12,d12]].map(([sides,vertices])=>[sides,{vertices:sides===10?vertices.map(([x,y,z])=>[x,z,y]):vertices,faces:hull(sides===10?vertices.map(([x,y,z])=>[x,z,y]):vertices)}]));
const rotate=([x,y,z])=>{const a=.52,b=.38;const X=x*Math.cos(a)+z*Math.sin(a),Z=z*Math.cos(a)-x*Math.sin(a);return [X,y*Math.cos(b)-Z*Math.sin(b),y*Math.sin(b)+Z*Math.cos(b)];};
export function polyhedralFace(sides,value){
 const model=diceModels[sides];if(!model)return String(value);
 const vs=model.vertices.map(rotate),radius=Math.max(...vs.map(v=>Math.max(Math.abs(v[0]),Math.abs(v[1])))),scale=43/radius;
 const faces=model.faces.map(f=>({...f,n:rotate(f.n),center:rotate(f.center)})).filter(f=>f.n[2]>.001).sort((a,b)=>a.center[2]-b.center[2]);
 const front=faces.reduce((a,b)=>a.n[2]>b.n[2]?a:b),point=v=>`${50+v[0]*scale},${50-v[1]*scale}`;
 return `<svg class="die-solid" data-polyhedron="${sides}" viewBox="0 0 100 100" aria-hidden="true">${faces.map(f=>`<polygon points="${f.ids.map(i=>point(vs[i])).join(' ')}" fill="var(--die-bg)"/><polygon points="${f.ids.map(i=>point(vs[i])).join(' ')}" fill="${f.n[0]<0?'#fff':'#000'}" fill-opacity="${(.07+Math.abs(f.n[0])*.23).toFixed(2)}"/>`).join('')}<text x="${50+front.center[0]*scale}" y="${50-front.center[1]*scale}" dominant-baseline="central" text-anchor="middle">${Number(value)}</text></svg>`;
}
