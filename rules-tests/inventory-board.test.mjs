import assert from 'node:assert/strict';
import {itemArt,itemCrops,itemImage,itemPicture,itemArtData,catalogArt,artOptions} from '../public/inventory-art.js';
import {ITEMS} from '../public/tools/rules.js';
import {inventoryBag,equipmentTiles,resourceTiles} from '../public/inventory-board.js';
assert.equal(itemArt.length,96);assert.equal(itemCrops.length,96);
assert.equal(new Set(itemArt.map(([id])=>id)).size,itemArt.length);
for(const item of itemArtData.items){
 const [x,y,w,h]=item.crop,atlas=itemArtData.atlases[item.atlas];
 assert.ok(atlas&&x>=0&&y>=0&&w>0&&h>0&&x+w<=atlas.width&&y+h<=atlas.height,item.id+' crop');
 assert.ok(itemPicture(item.id).includes(atlas.src),item.id+' atlas');
 assert.ok(/^M[0-9L MZ]+$/.test(item.clip),item.id+' safe clipping outline');
 const first=itemPicture(item.id),second=itemPicture(item.id);
 assert.ok(first.includes('<clipPath')&&first.includes('clip-path="url(#'));
 assert.notEqual(first.match(/clipPath id="([^"]+)"/)[1],second.match(/clipPath id="([^"]+)"/)[1],'Repeated pictures need independent clip IDs');
 assert.equal(itemImage({art:item.id,name:'Предмет с авторским названием',combatProfile:'sword'}),item.id);
}
assert.deepEqual(Object.keys(catalogArt).sort(),Object.keys(ITEMS).sort(),'Every catalog entry needs an intentional illustration');
for(const [id,item] of Object.entries(ITEMS)){
 const expected=catalogArt[id];
 assert.ok(itemArt.some(([art])=>art===expected),id+' unknown image');
 assert.equal(itemImage(item),expected,id+' raw catalog object');
 assert.equal(itemImage({name:item.name}),expected,id+' legacy name without catalogId');
 assert.equal(itemImage({catalogId:id,name:'Именной подарок',combatProfile:'sword'}),expected,id+' renamed catalog entry');
 if(id!=='backpack')assert.notEqual(expected,'pack',id+' generic bag fallback');
}
for(const [name,expected] of [['Боевой молот орков','warhammer'],['Серебряный кистень','flail'],['Метательный нож дракона','throwingknife'],['Столовый нож великана','foodknife'],['Карта стрелковых позиций','map'],['Колчан со стрелами','quiver'],['Картина у мельницы','pack'],['Алебарда','halberd'],['Двуручный меч','greatsword'],['Тяжёлый арбалет','heavycrossbow'],['Спальный мешок','bedroll']])assert.equal(itemImage({name}),expected,name);
assert.equal(itemImage({art:'lantern',catalogId:'warhammer',name:'Молот'}),'lantern','Explicit image overrides canonical type');
assert.equal(itemImage({catalogId:'unknown',name:'Неведомый клинок',combatProfile:'greatsword'}),'greatsword');
assert.ok(artOptions('lantern').includes('<optgroup label="Оружие">'));
assert.equal((artOptions('').match(/<option value=/g)||[]).length,97);
assert.equal(itemImage({combatProfile:'crossbow'}),'crossbow');assert.equal(itemImage({name:'Верёвка'}),'rope');assert.equal(itemImage({kind:'armor',armorSlot:'helmet'}),'helmet');assert.equal(itemImage({art:'potion',combatProfile:'sword'}),'potion');assert.ok(itemPicture({art:'<script>'}).includes('inventory-atlas'));
const sword={id:'s',name:'<Клинок>',kind:'weapon',combatProfile:'sword',grip:'2Р',quantity:1,weight:2,wear:1,artifactDie:'D8'},rope={id:'r',name:'Верёвка',quantity:3,weight:.5,kind:'gear'},c={id:'hero',equipment:{weapon:'s'},runtime:{resources:{food:8,water:6,arrows:0,torches:12},consumed:{food:1}},load:{total:6.5,capacity:6,items:3.5,supplies:3,coins:0,overloaded:true}},s={me:{role:'player'},journey:{phase:'planning',party:[],day:1}};
const bag=inventoryBag(c,[sword,rope],s,true);assert.ok(!bag.includes('&lt;Клинок&gt;'));assert.ok(bag.includes('×3'));assert.ok(bag.includes('Перегруз на 0.5'));
const tiles=equipmentTiles(c,[sword,rope],false);assert.ok(tiles.includes('Занята двуручным оружием'));assert.ok(tiles.includes('&lt;Клинок&gt;'));
const resources=resourceTiles(c,s);assert.ok(resources.includes('Порция использована сегодня'));assert.ok(!resources.includes('data-resource-set'));assert.ok(resourceTiles(c,{...s,me:{role:'gm'}}).includes('data-resource-set'));
console.log('Interactive inventory: icons, four slots, carried stacks, weight, daily rations and player controls passed.');
