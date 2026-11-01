import artData from './inventory-art-data.json' with {type:'json'};

// One manifest supplies browser images and the server's art whitelist.
// Choosing an illustration never changes the item's rules or equipment profile.
export const itemArtData=artData;
export const itemArt=artData.items.map(({id,label})=>[id,label]);
export const itemCrops=artData.items.map(({crop})=>crop);
export const catalogArt=Object.fromEntries(Object.entries(artData.catalog).map(([id,item])=>[id,item.art]));
const byArt=new Map(artData.items.map(item=>[item.id,item]));
let nextClipId=0;
const normalize=value=>String(value??'').toLowerCase().replace(/ё/g,'е').replace(/[^\p{L}\p{N}]+/gu,' ').trim();
const namedCatalog=new Map(Object.values(artData.catalog).map(item=>[normalize(item.name),item.art]));
const catalogPhrases=[...namedCatalog].sort(([a],[b])=>b.length-a.length);
export const escapeItem=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

// Specific phrases precede generic families. Unicode letter boundaries prevent
// «мел» from matching «мельница», and «карта» from matching «картина».
const hints=[
 ['(?:метательн\\p{L}*|throwing) (?:нож\\p{L}*|кинжал\\p{L}*|knife)','throwingknife'],
 ['(?:столов\\p{L}*|dining|table) (?:нож\\p{L}*|knife)','foodknife'],
 ['(?:метательн\\p{L}*|throwing) (?:копь\\p{L}*|spear)|javelin','throwingspear'],
 ['(?:двуручн\\p{L}*|two handed|great) (?:меч\\p{L}*|sword)|greatsword','greatsword'],
 ['(?:коротк\\p{L}*|short) (?:меч\\p{L}*|sword)|shortsword','shortsword'],
 ['(?:длинн\\p{L}*|long) (?:меч\\p{L}*|sword)|longsword','longsword'],
 ['(?:коротк\\p{L}*|short) (?:копь\\p{L}*|spear)','shortspear'],
 ['(?:длинн\\p{L}*|long) (?:лук\\p{L}*|bow)|longbow','longbow'],
 ['(?:тяжел\\p{L}*|heavy) (?:арбалет\\p{L}*|crossbow)','heavycrossbow'],
 ['(?:ручн\\p{L}*|метательн\\p{L}*|hand|throwing) (?:топор\\p{L}*|axe)|hatchet','handaxe'],
 ['(?:мал\\p{L}*|small) (?:щит\\p{L}*|shield)|buckler','smallshield'],
 ['(?:больш\\p{L}*|large) (?:щит\\p{L}*|shield)','largeshield'],
 ['(?:закрыт\\p{L}*|closed) (?:шлем\\p{L}*|helm\\p{L}*)','closedhelm'],
 ['(?:укреплен\\p{L}*|studded) (?:кожан\\p{L}*|leather)','leather'],
 ['кожан\\p{L}* (?:доспех\\p{L}*|брон\\p{L}*)|leather armor','leatherarmor'],
 ['(?:магическ\\p{L}*|чародейск\\p{L}*|волшебн\\p{L}*|magic|wizard) (?:посох\\p{L}*|staff)','staff'],
 ['(?:добротн\\p{L}*|tailored) (?:плащ\\p{L}*|cloak)','tailoredcloak'],
 ['(?:больш\\p{L}*|large) (?:палатк\\p{L}*|tent)','largetent'],
 ['(?:спальн\\p{L}*|sleeping) (?:мешок|bag)|bedroll','bedroll'],
 ['фальшион\\p{L}*|falchion','falchion'],['скимитар\\p{L}*|сабл\\p{L}*|scimitar|sabre','scimitar'],
 ['моргенштерн\\p{L}*|morningstar|morning star','morningstar'],['кистен\\p{L}*|боев\\p{L}* цеп\\p{L}*|flail','flail'],
 ['боев\\p{L}* молот\\p{L}*|warhammer|war hammer','warhammer'],['дубин\\p{L}*|палиц\\p{L}*|club','club'],
 ['пращ\\p{L}*|sling','sling'],['алебард\\p{L}*|halberd','halberd'],['булав\\p{L}*|mace','plainmace'],
 ['свиток|свитк\\p{L}*|книг\\p{L}*|scroll|book','scroll'],['зель\\p{L}*|эликсир\\p{L}*|potion','potion'],
 ['подзорн\\p{L}* труб\\p{L}*|spyglass','spyglass'],['карт[аыуе]|map','map'],['мел|chalk','chalk'],
 ['колчан\\p{L}*|quiver','quiver'],['яд|яда|яды|poison','poison'],
 ['палатк\\p{L}*|tent','smalltent'],['плащ\\p{L}*|cloak','cloak'],['одеял\\p{L}*|blanket','blanket'],
 ['мешок|мешк\\p{L}*|sack','sack'],['чернил\\p{L}*|ink','ink'],['пергамент\\p{L}*|parchment','parchment'],
 ['огнив\\p{L}*|flint','flint'],['отмыч\\p{L}*|lockpick\\p{L}*','lockpicks'],['бинт\\p{L}*|bandage\\p{L}*','bandages'],
 ['кинжал\\p{L}*|dagger','dagger'],['нож|ножа|ножи|knife','knife'],['меч\\p{L}*|sword','sword'],
 ['топор\\p{L}*|секир\\p{L}*|axe','axe'],['копь\\p{L}*|spear','spear'],['арбалет\\p{L}*|crossbow','crossbow'],
 ['лук|лука|bow','bow'],['посох\\p{L}*|staff|quarterstaff','quarterstaff'],['шлем\\p{L}*|helm\\p{L}*','helmet'],
 ['щит\\p{L}*|shield','shield'],['кольчуг\\p{L}*|chainmail','chainmail'],['веревк\\p{L}*|rope','rope'],
 ['факел\\p{L}*|torch','torch'],['стрел[аы]|arrows','arrows'],['вод[аыуе]|бурдюк\\p{L}*|water','water'],
 ['ед[аы]|паек|пайк\\p{L}*|провизи\\p{L}*|рацион\\p{L}*|food|rations','food'],
 ['монет\\p{L}*|кошел\\p{L}*|coin\\p{L}*','coins'],['инструмент\\p{L}*|молоток|клещи|tool\\p{L}*','tools']
].map(([pattern,art])=>[new RegExp('(?:^|[^\\p{L}])(?:'+pattern+')(?=$|[^\\p{L}])','iu'),art]);

export function itemImage(i={}){
 if(byArt.has(i.art))return i.art;
 const catalogId=i.catalogId||i.id;
 if(Object.hasOwn(catalogArt,catalogId))return catalogArt[catalogId];
 const name=normalize(i.name);
 if(namedCatalog.has(name))return namedCatalog.get(name);
 // This also handles a canonical catalog object or an English catalog ID name.
 if(Object.hasOwn(catalogArt,name.replaceAll(' ','')))return catalogArt[name.replaceAll(' ','')];
 const phrase=catalogPhrases.find(([label])=>(' '+name+' ').includes(' '+label+' '));
 if(phrase&&phrase[0].includes(' '))return phrase[1];
 for(const [pattern,art] of hints)if(pattern.test(name))return art;
 if(phrase)return phrase[1];
 const profile={sword:'sword',greatsword:'greatsword',dagger:'dagger',axe:'axe',mace:'plainmace',spear:'spear',halberd:'halberd',bow:'bow',longbow:'longbow',crossbow:'crossbow',staff:'quarterstaff'}[i.combatProfile];
 if(profile)return profile;
 if(i.kind==='shield')return 'shield';
 if(i.kind==='armor')return i.armorSlot==='helmet'?'helmet':'chainmail';
 return i.kind==='artifact'?'gem':'pack';
}

export function itemPicture(item,extra=''){
 const art=typeof item==='string'?item:itemImage(item),entry=byArt.get(art)||byArt.get('pack'),atlas=artData.atlases[entry.atlas];
 const clipId='inventory-art-clip-'+(++nextClipId);
 return '<svg class="item-picture '+escapeItem(extra)+'" viewBox="'+entry.crop.join(' ')+'" width="80" height="80" aria-hidden="true" focusable="false">'+(entry.clip?'<defs><clipPath id="'+clipId+'" clipPathUnits="userSpaceOnUse"><path d="'+entry.clip+'"/></clipPath></defs>':'')+'<image href="'+atlas.src+'" width="'+atlas.width+'" height="'+atlas.height+'"'+(entry.clip?' clip-path="url(#'+clipId+')"':'')+'/></svg>';
}
export const artOptions=value=>'<option value="">Подобрать по предмету</option>'+Object.entries(artData.groups).map(([group,label])=>'<optgroup label="'+escapeItem(label)+'">'+artData.items.filter(i=>i.group===group).map(i=>'<option value="'+i.id+'" '+(i.id===value?'selected':'')+'>'+escapeItem(i.label)+'</option>').join('')+'</optgroup>').join('');
