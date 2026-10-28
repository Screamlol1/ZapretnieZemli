export const atlasURL='/assets/location-atlas-v1.png';
export const locationArt=[
 ['thatch','Дом с соломенной крышей'],['shingle','Деревянный дом'],['tile','Дом с черепичной крышей'],['barn','Амбар'],['tavern','Таверна'],['smithy','Кузница'],
 ['chapel','Каменная часовня'],['manor','Дом старосты'],['keep','Донжон'],['tower','Каменная башня'],['gate','Ворота'],['ruin','Разрушенный дом'],
 ['tent','Походная палатка'],['pavilion','Шатёр'],['supplies','Ящики и бочки'],['well','Колодец'],['market','Торговые ряды'],['fire','Костёр'],
 ['bridge','Деревянный мост'],['oak','Лиственное дерево'],['pine','Хвойное дерево'],['rocks','Камни'],['room','Каменный зал'],['cave','Пещерный зал']
];
const crops=[[23, 50, 213, 188], [254, 45, 205, 203], [488, 20, 208, 235], [738, 61, 248, 186], [1013, 29, 261, 229], [1293, 31, 225, 220], [34, 267, 191, 255], [247, 272, 234, 248], [499, 272, 216, 248], [764, 267, 187, 255], [986, 303, 295, 210], [1297, 301, 220, 225], [22, 538, 220, 219], [257, 536, 231, 221], [510, 562, 224, 180], [769, 543, 178, 211], [986, 526, 307, 214], [1322, 549, 179, 194], [22, 817, 216, 146], [256, 763, 232, 239], [509, 761, 222, 241], [747, 776, 234, 233], [1016, 775, 235, 215], [1293, 761, 219, 238]];
const escape=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function featureArt(f){
 if(locationArt.some(([id])=>id===f.art))return f.art;
 if(f.style==='building'){
  for(const [word,id] of [['Таверна','tavern'],['Кузница','smithy'],['старосты','manor'],['Святилище','chapel'],['Амбар','barn'],['Склад','barn'],['Торговый','market']])if(f.label.includes(word))return id;
  return ['thatch','shingle','tile'][Math.abs(Math.round(f.x+f.y))%3];
 }
 return ({supply:'supplies',square:'market',tent:f.label.includes('вожака')?'pavilion':'tent'})[f.style]||f.style;
}
export function artDefinition(href=atlasURL,id='location-art-atlas'){return `<image id="${id}" width="1536" height="1024" href="${escape(href)}"/>${crops.map(([x,y,w,h],i)=>`<clipPath id="${id}-crop-${i}"><rect x="${x}" y="${y}" width="${w}" height="${h}"/></clipPath>`).join('')}`;}
export function artSprite(art,x,y,w,h,id='location-art-atlas',stretch=false){
 const index=locationArt.findIndex(([key])=>key===art);if(index<0)return '';
 const [sx,sy,sw,sh]=crops[index];
 return `<svg x="${x}" y="${y}" width="${w}" height="${h}" viewBox="${sx} ${sy} ${sw} ${sh}" preserveAspectRatio="${stretch?'none':'xMidYMid meet'}" overflow="hidden" pointer-events="none"><g clip-path="url(#${id}-crop-${index})"><use href="#${id}"/></g></svg>`;
}
let previewSerial=0;
export function artPreview(id){const namespace='location-art-preview-'+(++previewSerial);return `<svg viewBox="0 0 160 120" width="160" height="120" aria-hidden="true"><defs>${artDefinition(atlasURL,namespace)}</defs>${artSprite(id,0,0,160,120,namespace)}</svg>`;}
let exportAtlas;
export async function embeddedAtlas(){
 if(!exportAtlas)exportAtlas=fetch(atlasURL).then(r=>{if(!r.ok)throw Error('Не удалось загрузить иллюстрации для экспорта.');return r.blob();}).then(blob=>new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(Error('Не удалось подготовить иллюстрации.'));reader.readAsDataURL(blob);})).catch(e=>{exportAtlas=null;throw e;});
 return exportAtlas;
}
