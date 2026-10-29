export const itemArt=[['sword','Меч'],['dagger','Кинжал'],['axe','Топор'],['mace','Булава'],['spear','Копьё'],['bow','Лук'],['crossbow','Арбалет'],['staff','Посох'],['shield','Щит'],['helmet','Шлем'],['chainmail','Кольчуга'],['leather','Кожаный доспех'],['pack','Сумка'],['rope','Верёвка'],['torch','Факел'],['food','Провизия'],['water','Вода'],['arrows','Стрелы'],['coins','Монеты'],['gem','Артефакт'],['scroll','Свиток'],['potion','Зелье'],['tools','Инструменты'],['bedroll','Спальный мешок']];
export const escapeItem=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const itemCrops=[[16,17,230,225],[307,52,184,188],[538,8,226,236],[798,20,211,219],[1031,19,239,225],[1299,16,223,226],[12,287,239,197],[282,253,228,266],[524,263,224,227],[791,269,210,231],[1032,283,238,203],[1301,263,215,242],[13,518,237,230],[280,541,218,202],[541,491,196,266],[777,552,234,190],[1052,518,211,240],[1301,514,216,244],[8,812,246,176],[308,764,171,237],[524,804,242,173],[812,767,167,234],[1028,779,235,234],[1285,802,241,177]];
export function itemImage(i={}){
 if(itemArt.some(([id])=>id===i.art))return i.art;
 const profile={sword:'sword',greatsword:'sword',dagger:'dagger',axe:'axe',mace:'mace',spear:'spear',halberd:'spear',bow:'bow',longbow:'bow',crossbow:'crossbow',staff:'staff'}[i.combatProfile];if(profile)return profile;
 if(i.kind==='shield')return 'shield';if(i.kind==='armor')return i.armorSlot==='helmet'?'helmet':/кож|leather/i.test(i.name)?'leather':'chainmail';
 const name=String(i.name||i.catalogId||'').toLowerCase();
 for(const [pattern,art] of [['кинжал|нож|dagger','dagger'],['меч|sword','sword'],['топор|секир|axe','axe'],['копь|алебард|spear','spear'],['арбал|crossbow','crossbow'],['лук|bow','bow'],['посох|staff','staff'],['шлем|helm','helmet'],['щит|shield','shield'],['верёв|верев|rope','rope'],['факел|torch','torch'],['стрел|колчан|arrows','arrows'],['вода|бурдюк|water','water'],['ед[аы]|паёк|паек|прови|рацион|food','food'],['монет|кошел|coin','coins'],['зель|эликс|potion','potion'],['свит|книг|scroll','scroll'],['инструм|молот|клещ|tool','tools'],['одеял|спаль|bedroll','bedroll']])if(new RegExp(pattern).test(name))return art;
 return i.kind==='artifact'?'gem':'pack';
}
export function itemPicture(item,extra=''){
 const art=typeof item==='string'?item:itemImage(item),index=Math.max(0,itemArt.findIndex(([id])=>id===art)),[x,y,w,h]=itemCrops[index];
 return `<svg class="item-picture ${extra}" viewBox="${x} ${y} ${w} ${h}" width="80" height="80" aria-hidden="true" focusable="false"><image href="/assets/inventory-atlas-v1.png" width="1536" height="1024"/></svg>`;
}
export const artOptions=value=>'<option value="">Подобрать по предмету</option>'+itemArt.map(([id,label])=>`<option value="${id}" ${id===value?'selected':''}>${label}</option>`).join('');
