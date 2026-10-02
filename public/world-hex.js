// Pointy-top hexagons with odd rows shifted right, matching campaign_rules.adjacent.
export const R=26, W=Math.sqrt(3)*R, COLS=24, ROWS=16;
export const extent={width:(COLS+.5)*W,height:(ROWS-1)*1.5*R+2*R};
export const center=({x,y})=>({x:(x+.5+(y%2)/2)*W,y:R+y*1.5*R});
export function vertices(p){const c=center(p);return [[0,-R],[W/2,-R/2],[W/2,R/2],[0,R],[-W/2,R/2],[-W/2,-R/2]].map(([x,y])=>[c.x+x,c.y+y]);}
export function adjacent(a,b){const dq=b.x-(b.y-b.y%2)/2-a.x+(a.y-a.y%2)/2,dr=b.y-a.y;return Math.max(Math.abs(dq),Math.abs(dr),Math.abs(dq+dr))===1;}
export const terrainInfo={plain:['Равнина',2],forest:['Лес',2],darkforest:['Тёмный лес',1],hills:['Холмы',2],mountain:['Горы',1],highmountain:['Высокие горы',0],marsh:['Болото',0],water:['Вода',0],rough:['Трудная местность',1],ruin:['Руины',1],road:['Дорога',2],wall:['Преграда',0]};
export function routeProblem(start,path,cells,mounted=false){
 if(path.length>3)return 'Не больше трёх гексов за четверть дня.';
 let prev=start,limit=mounted?3:2;const seen=new Set([`${start.x},${start.y}`]);
 for(const p of path){const key=`${p.x},${p.y}`,speed=terrainInfo[cells[key]?.terrain||'plain']?.[1];
  if(!Number.isInteger(p.x)||!Number.isInteger(p.y)||p.x<0||p.x>=COLS||p.y<0||p.y>=ROWS)return 'Гекс вне карты.';
  if(!adjacent(prev,p))return 'Продолжайте маршрут через соседний гекс.';
  if(seen.has(key))return 'Маршрут этой четверти не должен возвращаться в тот же гекс.';
  if(!speed)return 'Нужна переправа или решение Мастера: обычный переход сюда невозможен.';
  if(speed===1)limit=1;seen.add(key);prev=p;
 }
 return path.length>limit?'Трудная местность: один гекс за четверть дня.':null;
}
