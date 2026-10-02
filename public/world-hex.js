// Existing campaigns keep their pointy, odd-row grid. Ravenland uses flat, odd-column hexes.
export let R=26, W=Math.sqrt(3)*R, COLS=24, ROWS=16;
export const extent={width:(COLS+.5)*W,height:(ROWS-1)*1.5*R+2*R};
let regional=false;
export function setLayout(kind){regional=kind==='ravenland';R=regional?31.82:26;W=Math.sqrt(3)*R;COLS=regional?41:24;ROWS=regional?25:16;Object.assign(extent,regional?{width:2039.2374,height:1474.3049}:{width:(COLS+.5)*W,height:(ROWS-1)*1.5*R+2*R});}
export const valid=({x,y})=>Number.isInteger(x)&&Number.isInteger(y)&&x>=0&&x<COLS&&y>=0&&y<ROWS&&(!regional||x%2===0||y<24);
export const label=({x,y})=>{if(!regional)return `${x+1}:${y+1}`;let n=x+1,a='';while(n){n--;a=String.fromCharCode(65+n%26)+a;n=Math.floor(n/26);}return `${a}${2*y+x%2+1}`;};
export function parseLabel(value){
 const match=String(value).trim().toUpperCase().match(regional?/^([A-Z]{1,2})([1-9][0-9]?)$/:/^([0-9]+)[: ,]([0-9]+)$/);
 if(!match)return null;
 const x=regional?[...match[1]].reduce((n,c)=>n*26+c.charCodeAt(0)-64,0)-1:Number(match[1])-1;
 const row=Number(match[2])-1,y=regional?(row-x%2)/2:row,p={x,y};return valid(p)?p:null;
}
export const center=({x,y})=>regional?{x:61.5+x*1.5*R,y:77.5+(y+x%2/2)*W}:{x:(x+.5+(y%2)/2)*W,y:R+y*1.5*R};
export function vertices(p){const c=center(p),v=regional?[[R,0],[R/2,W/2],[-R/2,W/2],[-R,0],[-R/2,-W/2],[R/2,-W/2]]:[[0,-R],[W/2,-R/2],[W/2,R/2],[0,R],[-W/2,R/2],[-W/2,-R/2]];return v.map(([x,y])=>[c.x+x,c.y+y]);}
export function adjacent(a,b){const dq=regional?b.x-a.x:b.x-(b.y-b.y%2)/2-a.x+(a.y-a.y%2)/2,dr=regional?b.y-(b.x-b.x%2)/2-a.y+(a.x-a.x%2)/2:b.y-a.y;return Math.max(Math.abs(dq),Math.abs(dr),Math.abs(dq+dr))===1;}
// Player Handbook, printed p.145: movement, forage and hunt modifiers.
export const terrainRules={plain:['Равнина',2,-1,1],forest:['Лес',2,1,1],darkforest:['Тёмный лес',1,-1,0],hills:['Холмы',2,0,0],mountain:['Горы',1,-2,-1],highmountain:['Высокие горы',0,null,null],water:['Озеро / река',0,null,0],marsh:['Болото',0,1,-1],rough:['Топь',1,-1,0],ruin:['Руины',1,-2,-1],road:['Дорога',2,-1,1],wall:['Преграда',0,null,null]};
export const terrainInfo=Object.fromEntries(Object.entries(terrainRules).map(([k,v])=>[k,v.slice(0,2)]));
export const terrainPalette={plain:'#867e4d',forest:'#515428',darkforest:'#343618',hills:'#91855b',mountain:'#8b8572',highmountain:'#817b66',water:'#52634d',marsh:'#76765f',rough:'#948a5a',ruin:'#77705c',road:'#ddc99c',wall:'#a69b87'};
export const movementText=k=>k==='highmountain'?'Непроходимо':k==='water'?'Нужна лодка или плот':k==='marsh'?'Нужен плот':k==='wall'?'Путь перекрыт':terrainInfo[k][1]===1?'Один гекс за четверть дня':'До двух гексов пешком или трёх верхом';

export function routeProblem(start,path,cells,mounted=false){
 if(path.length>3)return 'Не больше трёх гексов за четверть дня.';
 let prev=start,limit=mounted?3:2;const seen=new Set([`${start.x},${start.y}`]);
 for(const p of path){const key=`${p.x},${p.y}`,speed=terrainInfo[cells[key]?.terrain||'plain']?.[1];
  if(!Number.isInteger(p.x)||!Number.isInteger(p.y)||!valid(p))return 'Гекс вне карты.';
  if(regional&&!cells[key]?.terrain)return 'Сначала укажите местность гекса по легенде карты.';
  if(!adjacent(prev,p))return 'Продолжайте маршрут через соседний гекс.';
  if(seen.has(key))return 'Маршрут этой четверти не должен возвращаться в тот же гекс.';
  if(!speed)return movementText(cells[key]?.terrain||'plain')+'. Обычный переход сюда невозможен.';
  if(speed===1)limit=1;seen.add(key);prev=p;
 }
 return path.length>limit?'Трудная местность: один гекс за четверть дня.':null;
}
